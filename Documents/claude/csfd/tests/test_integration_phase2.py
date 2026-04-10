"""Integration tests for dashboard pipeline: DataExporter helpers + DashboardGenerator."""

import json
import tempfile
from pathlib import Path

import pytest

from csfd_vod.export.dashboard_generator import DashboardGenerator, _JSON_FILES


# ---------------------------------------------------------------------------
# Shared fixture: a data dir with all JSON files populated
# ---------------------------------------------------------------------------

@pytest.fixture
def full_data_dir(tmp_path):
    """Write a complete set of JSON files mimicking DataExporter output."""
    summary = {
        "export_timestamp": "2026-04-11T12:00:00Z",
        "total_titles": 250,
        "total_films": 150,
        "total_serials": 80,
        "total_genres": 25,
        "total_directors": 80,
        "total_actors": 150,
        "total_countries": 18,
        "total_platforms": 10,
        "avg_rating": 72.5,
        "title_type_counts": [
            {"name": "film", "count": 150},
            {"name": "seriál", "count": 80},
            {"name": "pořad", "count": 20},
        ],
    }
    genres = [{"name": "Drama", "count": 75}, {"name": "Sci-fi", "count": 45},
              {"name": "Thriller", "count": 40}, {"name": "Akcia", "count": 35}]
    directors = [{"name": "Christopher Nolan", "count": 5}, {"name": "Denis Villeneuve", "count": 4}]
    actors = [{"name": "Keanu Reeves", "count": 8}, {"name": "Tom Hanks", "count": 6}]
    countries = [{"name": "USA", "count": 120}, {"name": "Veľká Británia", "count": 45}]
    platforms = [{"name": "Netflix", "count": 180}, {"name": "HBO Max", "count": 120}]
    tags = [{"name": "sci-fi", "count": 30}, {"name": "thriller", "count": 25}]
    rating_distribution = [{"bucket": f"{i}-{i+10}", "count": 10 + i} for i in range(0, 100, 10)]
    vod_by_month = [{"month": f"2026-{m:02d}", "count": 20 + m} for m in range(1, 13)]
    top_titles = [
        {
            "title": f"Top Film {i}", "title_en": f"Top Film {i} EN",
            "year": 2020 + (i % 6), "rating": 90 - i, "vod_date": f"2026-0{(i%9)+1}-01",
            "distributor": "Netflix", "image_url": None,
            "title_type": "film", "link": f"https://csfd.cz/film/{i}/",
            "genres": ["Drama"], "platforms": ["Netflix"],
        }
        for i in range(20)
    ]

    data_map = {
        "summary": summary, "genres": genres, "directors": directors,
        "actors": actors, "countries": countries, "platforms": platforms,
        "tags": tags, "rating_distribution": rating_distribution,
        "vod_by_month": vod_by_month, "top_titles": top_titles,
    }
    for name in _JSON_FILES:
        (tmp_path / f"{name}.json").write_text(
            json.dumps(data_map[name], ensure_ascii=False), encoding="utf-8"
        )
    return tmp_path


# ---------------------------------------------------------------------------
# DashboardGenerator integration tests
# ---------------------------------------------------------------------------

def test_integration_export_to_dashboard(full_data_dir, tmp_path):
    """Full pipeline: read JSON files → generate HTML dashboard."""
    gen = DashboardGenerator()
    html_path = tmp_path / "index.html"
    result = gen.generate(str(full_data_dir), str(html_path))

    assert result["success"] is True
    assert html_path.exists()
    assert result["total_titles"] == 250
    assert result["file_size_kb"] > 0


def test_integration_dashboard_renders_all_charts(full_data_dir, tmp_path):
    """All chart container IDs should be present in generated HTML."""
    gen = DashboardGenerator()
    html_path = tmp_path / "index.html"
    gen.generate(str(full_data_dir), str(html_path))
    html = html_path.read_text(encoding="utf-8")

    for chart_id in ["chart-genres", "chart-platforms", "chart-directors",
                     "chart-actors", "chart-countries", "chart-rating",
                     "chart-vod-months", "top-titles-table"]:
        assert chart_id in html, f"Missing chart container: {chart_id}"


def test_integration_dashboard_with_minimal_data(tmp_path):
    """Dashboard should render even with a single title and minimal data."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    for name in _JSON_FILES:
        val = {} if name == "summary" else []
        (data_dir / f"{name}.json").write_text(json.dumps(val), encoding="utf-8")

    # Write a real summary
    (data_dir / "summary.json").write_text(json.dumps({
        "export_timestamp": "2026-04-11T00:00:00Z",
        "total_titles": 1, "total_films": 1, "total_serials": 0,
        "total_genres": 1, "total_directors": 1, "total_actors": 1,
        "total_countries": 1, "total_platforms": 1, "avg_rating": 80.0,
        "title_type_counts": [{"name": "film", "count": 1}],
    }), encoding="utf-8")

    html_path = tmp_path / "index.html"
    result = DashboardGenerator().generate(str(data_dir), str(html_path))
    assert result["success"] is True
    assert result["total_titles"] == 1


def test_integration_dashboard_file_size(full_data_dir, tmp_path):
    """Generated HTML should be between 10 KB and 5 MB."""
    html_path = tmp_path / "index.html"
    result = DashboardGenerator().generate(str(full_data_dir), str(html_path))
    assert 10 < result["file_size_kb"] < 5000, f"Unexpected size: {result['file_size_kb']} KB"


def test_integration_dashboard_json_parsing(full_data_dir, tmp_path):
    """Embedded JSON in HTML must be parseable and contain correct data."""
    html_path = tmp_path / "index.html"
    DashboardGenerator().generate(str(full_data_dir), str(html_path))
    html = html_path.read_text(encoding="utf-8")

    marker = "const D = "
    start = html.find(marker) + len(marker)
    end = html.find(";\n", start)
    parsed = json.loads(html[start:end])

    assert parsed["summary"]["total_titles"] == 250
    assert parsed["genres"][0]["name"] == "Drama"
    assert any(p["name"] == "Netflix" for p in parsed["platforms"])
    assert len(parsed["top_titles"]) == 20
