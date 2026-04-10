"""Tests for DataExporter helper logic and DashboardGenerator."""

import json
import tempfile
from collections import Counter
from pathlib import Path

import pytest

from csfd_vod.export.exporter import DataExporter
from csfd_vod.export.dashboard_generator import DashboardGenerator, _JSON_FILES


# ---------------------------------------------------------------------------
# DataExporter unit tests (pure Python helpers, no DB)
# ---------------------------------------------------------------------------

@pytest.fixture
def exporter():
    # Connection string unused in pure-logic tests
    return DataExporter.__new__(DataExporter)


SAMPLE_TITLES = [
    {"title_id": 1, "title": "Matrix", "title_en": "The Matrix", "year": 1999,
     "rating": 87, "plot": "...", "image_url": "/img/1.jpg", "title_type": "film",
     "parent_url": None, "vod_date": "2020-01-15", "distributor": "Netflix",
     "premiere_detail": None, "reviews": None, "scraped_at": None, "date_added": None,
     "link": "https://csfd.cz/film/1/"},
    {"title_id": 2, "title": "Dune", "title_en": None, "year": 2021,
     "rating": 75, "plot": "...", "image_url": "/img/2.jpg", "title_type": "film",
     "parent_url": None, "vod_date": "2022-03-01", "distributor": "HBO Max",
     "premiere_detail": None, "reviews": None, "scraped_at": None, "date_added": None,
     "link": "https://csfd.cz/film/2/"},
    {"title_id": 3, "title": "Breaking Bad", "title_en": None, "year": 2008,
     "rating": None, "plot": "...", "image_url": None, "title_type": "seriál",
     "parent_url": None, "vod_date": "2021-06-01", "distributor": "Netflix",
     "premiere_detail": None, "reviews": None, "scraped_at": None, "date_added": None,
     "link": "https://csfd.cz/film/3/"},
]

SAMPLE_GENRES_MAP = {
    1: ["Sci-fi", "Akcia"],
    2: ["Sci-fi", "Drama"],
    3: ["Drama", "Krimi"],
}

SAMPLE_PLATFORMS_MAP = {
    1: ["Netflix"],
    2: ["HBO Max"],
    3: ["Netflix"],
}


def test_build_summary(exporter):
    summary = exporter._build_summary(
        SAMPLE_TITLES,
        SAMPLE_GENRES_MAP,
        {1: ["Keanu Reeves"], 2: ["Timothée Chalamet"]},
        {1: ["Lana Wachowski"], 2: ["Denis Villeneuve"]},
        {1: ["USA"], 2: ["USA"], 3: ["USA"]},
        SAMPLE_PLATFORMS_MAP,
    )
    assert summary["total_titles"] == 3
    assert summary["total_films"] == 2
    assert summary["total_serials"] == 1
    assert summary["total_genres"] == 4   # Sci-fi, Akcia, Drama, Krimi → 4 unique
    assert summary["avg_rating"] == 81.0  # (87 + 75) / 2
    assert "export_timestamp" in summary
    assert "title_type_counts" in summary


def test_build_summary_no_ratings(exporter):
    no_rating = [{**t, "rating": None} for t in SAMPLE_TITLES]
    summary = exporter._build_summary(no_rating, {}, {}, {}, {}, {})
    assert summary["avg_rating"] is None


def test_rating_distribution(exporter):
    dist = exporter._rating_distribution(SAMPLE_TITLES)
    assert isinstance(dist, list)
    assert len(dist) == 10  # 10 buckets: 0-10, 10-20, ..., 90-100

    buckets = {d["bucket"]: d["count"] for d in dist}
    assert buckets["80-90"] == 1   # rating 87
    assert buckets["70-80"] == 1   # rating 75
    assert buckets["0-10"] == 0


def test_rating_distribution_boundary(exporter):
    """Rating = 100 should land in the 90-100 bucket, not overflow."""
    titles = [{"rating": 100}, {"rating": 90}, {"rating": 0}]
    dist = {d["bucket"]: d["count"] for d in exporter._rating_distribution(titles)}
    assert dist["90-100"] == 2
    assert dist["0-10"] == 1


def test_top_titles_sorted_by_rating(exporter):
    top = exporter._top_titles(SAMPLE_TITLES, SAMPLE_GENRES_MAP, SAMPLE_PLATFORMS_MAP, limit=10)
    assert top[0]["rating"] == 87
    assert top[1]["rating"] == 75
    # Unrated (None) excluded
    assert all(t["rating"] is not None for t in top)


def test_top_titles_includes_genres_and_platforms(exporter):
    top = exporter._top_titles(SAMPLE_TITLES, SAMPLE_GENRES_MAP, SAMPLE_PLATFORMS_MAP, limit=10)
    matrix = next(t for t in top if t["title"] == "Matrix")
    assert "Sci-fi" in matrix["genres"]
    assert "Netflix" in matrix["platforms"]


def test_top_titles_limit(exporter):
    top = exporter._top_titles(SAMPLE_TITLES, SAMPLE_GENRES_MAP, SAMPLE_PLATFORMS_MAP, limit=1)
    assert len(top) == 1
    assert top[0]["title"] == "Matrix"


# ---------------------------------------------------------------------------
# DashboardGenerator tests
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_data_dir(tmp_path):
    """Write minimal valid JSON files into a temp data dir."""
    data = {
        "summary": {
            "export_timestamp": "2026-04-11T12:00:00Z",
            "total_titles": 3,
            "total_films": 2,
            "total_serials": 1,
            "total_genres": 4,
            "total_directors": 2,
            "total_actors": 3,
            "total_countries": 1,
            "total_platforms": 2,
            "avg_rating": 81.0,
            "title_type_counts": [{"name": "film", "count": 2}],
        },
        "genres":    [{"name": "Drama", "count": 2}, {"name": "Sci-fi", "count": 2}],
        "directors": [{"name": "Lana Wachowski", "count": 1}],
        "actors":    [{"name": "Keanu Reeves", "count": 1}],
        "countries": [{"name": "USA", "count": 3}],
        "platforms": [{"name": "Netflix", "count": 2}, {"name": "HBO Max", "count": 1}],
        "tags":      [{"name": "sci-fi", "count": 1}],
        "rating_distribution": [{"bucket": f"{i}-{i+10}", "count": 0} for i in range(0, 100, 10)],
        "vod_by_month": [{"month": "2026-01", "count": 3}],
        "top_titles": [
            {"title": "Matrix", "title_en": "The Matrix", "year": 1999,
             "rating": 87, "vod_date": "2020-01-15", "distributor": "Netflix",
             "image_url": None, "title_type": "film", "link": "https://csfd.cz/film/1/",
             "genres": ["Sci-fi"], "platforms": ["Netflix"]},
        ],
    }
    for name in _JSON_FILES:
        (tmp_path / f"{name}.json").write_text(
            json.dumps(data[name], ensure_ascii=False), encoding="utf-8"
        )
    return tmp_path


def test_dashboard_generator_creates_html(sample_data_dir, tmp_path):
    gen = DashboardGenerator()
    output = tmp_path / "index.html"
    result = gen.generate(str(sample_data_dir), str(output))

    assert result["success"] is True
    assert output.exists()
    assert result["file_size_kb"] > 0
    assert result["total_titles"] == 3


def test_dashboard_html_structure(sample_data_dir, tmp_path):
    gen = DashboardGenerator()
    output = tmp_path / "index.html"
    gen.generate(str(sample_data_dir), str(output))
    html = output.read_text(encoding="utf-8")

    assert "<!DOCTYPE html>" in html
    assert "CSFD VOD Dashboard" in html
    assert "Plotly" in html
    assert "const D = " in html


def test_dashboard_html_contains_data(sample_data_dir, tmp_path):
    gen = DashboardGenerator()
    output = tmp_path / "index.html"
    gen.generate(str(sample_data_dir), str(output))
    html = output.read_text(encoding="utf-8")

    # Key values from sample data must be embedded
    assert "Drama" in html
    assert "Netflix" in html
    assert "Matrix" in html


def test_dashboard_data_is_valid_json(sample_data_dir, tmp_path):
    gen = DashboardGenerator()
    output = tmp_path / "index.html"
    gen.generate(str(sample_data_dir), str(output))
    html = output.read_text(encoding="utf-8")

    marker = "const D = "
    start = html.find(marker) + len(marker)
    # Find the semicolon that ends the JS statement
    end = html.find(";\n", start)
    embedded = json.loads(html[start:end])
    assert embedded["summary"]["total_titles"] == 3
    assert embedded["genres"][0]["name"] == "Drama"


def test_dashboard_handles_missing_json_files(tmp_path):
    """DashboardGenerator should not crash if some JSON files are absent."""
    empty_dir = tmp_path / "empty_data"
    empty_dir.mkdir()
    output = tmp_path / "index.html"
    gen = DashboardGenerator()
    result = gen.generate(str(empty_dir), str(output))
    assert result["success"] is True
    assert output.exists()


def test_dashboard_creates_nested_output_dir(sample_data_dir, tmp_path):
    output = tmp_path / "deep" / "nested" / "index.html"
    gen = DashboardGenerator()
    result = gen.generate(str(sample_data_dir), str(output))
    assert result["success"] is True
    assert output.exists()
