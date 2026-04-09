"""Integration tests for Phase 2: Dashboard Generation."""

import json
import tempfile
from pathlib import Path

import pytest

from csfd_vod.export.exporter import DataExporter
from csfd_vod.export.dashboard_generator import DashboardGenerator


@pytest.fixture
def sample_data_file():
    """Create a temporary JSON data file for testing."""
    data = {
        "metadata": {
            "export_timestamp": "2026-04-09T12:34:56Z",
            "total_titles": 250,
            "total_genres": 25,
            "total_directors": 80,
            "total_actors": 150,
            "total_countries": 18,
            "total_platforms": 10,
            "date_range": ["2015-01-01", "2026-04-09"],
        },
        "statistics": {
            "genres_by_count": [
                {"name": "Drama", "count": 75},
                {"name": "Comedy", "count": 45},
                {"name": "Thriller", "count": 40},
                {"name": "Action", "count": 35},
                {"name": "Horror", "count": 30},
                {"name": "Romance", "count": 25},
            ],
            "countries_by_count": [
                {"name": "USA", "count": 120},
                {"name": "United Kingdom", "count": 45},
                {"name": "France", "count": 35},
            ],
            "platforms_by_count": [
                {"name": "Netflix", "count": 180},
                {"name": "Amazon Prime", "count": 120},
                {"name": "HBO", "count": 100},
            ],
            "years_by_count": [
                {"year": 2025, "count": 40},
                {"year": 2024, "count": 38},
                {"year": 2023, "count": 36},
                {"year": 2022, "count": 34},
                {"year": 2021, "count": 32},
            ],
            "decade_distribution": [
                {"decade": "2020s", "count": 200},
                {"decade": "2010s", "count": 40},
                {"decade": "2000s", "count": 10},
            ],
        },
        "titles": [
            {
                "title_id": i,
                "url_id": f"http://csfd.cz/{i}",
                "title": f"Test Title {i}",
                "year": 2020 + (i % 6),
                "director": f"Director {i % 30}",
                "actors": f"Actor {i % 50}, Actor {(i+1) % 50}",
                "link": f"http://csfd.cz/{i}",
                "date_added": "2020-01-01",
                "date_scraped": "2026-04-09T00:00:00Z",
                "created_at": "2026-04-09T00:00:00Z",
                "updated_at": "2026-04-09T00:00:00Z",
                "genres": ["Drama", "Comedy"],
                "directors": [f"Director {i % 30}"],
                "actors_list": [f"Actor {i % 50}", f"Actor {(i+1) % 50}"],
                "countries": ["USA"],
                "platforms": ["Netflix"],
            }
            for i in range(1, 251)
        ],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


def test_integration_export_to_dashboard(sample_data_file):
    """Test full pipeline: load data and generate dashboard."""
    generator = DashboardGenerator()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Load sample data
        with open(sample_data_file, "r") as f:
            data = json.load(f)

        # Generate dashboard
        html_path = Path(tmpdir) / "index.html"
        result = generator.generate(data, str(html_path))

        assert result["success"] is True
        assert html_path.exists()
        assert result["titles_rendered"] == 250

        # Verify HTML contains expected content
        with open(html_path, "r") as f:
            html = f.read()

        assert "250" in html  # total_titles
        assert "Drama" in html
        assert "Netflix" in html
        assert "2026-04-09" in html


def test_integration_dashboard_renders_all_charts(sample_data_file):
    """Test that all chart types are rendered in dashboard."""
    generator = DashboardGenerator()

    with tempfile.TemporaryDirectory() as tmpdir:
        with open(sample_data_file, "r") as f:
            data = json.load(f)

        html_path = Path(tmpdir) / "index.html"
        generator.generate(data, str(html_path))

        with open(html_path, "r") as f:
            html = f.read()

        # Check for all expected chart containers
        assert "genres-chart" in html
        assert "countries-chart" in html
        assert "decade-chart" in html
        assert "platforms-chart" in html
        assert "years-chart" in html
        assert "summary-stats" in html


def test_integration_dashboard_with_minimal_data():
    """Test dashboard generation with minimal data."""
    generator = DashboardGenerator()

    minimal_data = {
        "metadata": {
            "export_timestamp": "2026-04-09T00:00:00Z",
            "total_titles": 1,
            "total_genres": 1,
            "total_directors": 1,
            "total_actors": 1,
            "total_countries": 1,
            "total_platforms": 1,
            "date_range": ["2020-01-01", "2020-01-01"],
        },
        "statistics": {
            "genres_by_count": [{"name": "Drama", "count": 1}],
            "countries_by_count": [{"name": "USA", "count": 1}],
            "platforms_by_count": [{"name": "Netflix", "count": 1}],
            "years_by_count": [{"year": 2020, "count": 1}],
            "decade_distribution": [{"decade": "2020s", "count": 1}],
        },
        "titles": [
            {
                "title_id": 1,
                "url_id": "http://csfd.cz/1",
                "title": "Single Title",
                "year": 2020,
                "director": "One Director",
                "actors": "One Actor",
                "link": "http://csfd.cz/1",
                "date_added": "2020-01-01",
                "date_scraped": "2026-04-09T00:00:00Z",
                "created_at": "2026-04-09T00:00:00Z",
                "updated_at": "2026-04-09T00:00:00Z",
                "genres": ["Drama"],
                "directors": ["One Director"],
                "actors_list": ["One Actor"],
                "countries": ["USA"],
                "platforms": ["Netflix"],
            }
        ],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = Path(tmpdir) / "index.html"
        result = generator.generate(minimal_data, str(html_path))

        assert result["success"] is True
        assert result["titles_rendered"] == 1


def test_integration_dashboard_file_size():
    """Test that dashboard file is reasonably sized."""
    generator = DashboardGenerator()

    data = {
        "metadata": {
            "export_timestamp": "2026-04-09T00:00:00Z",
            "total_titles": 100,
            "total_genres": 20,
            "total_directors": 50,
            "total_actors": 100,
            "total_countries": 15,
            "total_platforms": 8,
            "date_range": ["2020-01-01", "2026-04-09"],
        },
        "statistics": {
            "genres_by_count": [{"name": "Drama", "count": 50}],
            "countries_by_count": [{"name": "USA", "count": 100}],
            "platforms_by_count": [{"name": "Netflix", "count": 80}],
            "years_by_count": [{"year": 2025, "count": 50}],
            "decade_distribution": [{"decade": "2020s", "count": 100}],
        },
        "titles": [{"title_id": i, "title": f"Title {i}"} for i in range(1, 101)],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = Path(tmpdir) / "index.html"
        result = generator.generate(data, str(html_path))

        file_size_kb = result["file_size_kb"]
        # Dashboard should be at least 10 KB (template + data) but reasonable size
        assert 10 < file_size_kb < 1000, f"Unexpected file size: {file_size_kb} KB"


def test_integration_dashboard_json_parsing():
    """Test that dashboard HTML contains properly formatted JSON."""
    generator = DashboardGenerator()

    test_data = {
        "metadata": {
            "export_timestamp": "2026-04-09T12:34:56Z",
            "total_titles": 42,
            "total_genres": 5,
            "total_directors": 10,
            "total_actors": 15,
            "total_countries": 3,
            "total_platforms": 2,
            "date_range": ["2020-01-01", "2026-04-09"],
        },
        "statistics": {
            "genres_by_count": [],
            "countries_by_count": [],
            "platforms_by_count": [],
            "years_by_count": [],
            "decade_distribution": [],
        },
        "titles": [],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = Path(tmpdir) / "index.html"
        generator.generate(test_data, str(html_path))

        with open(html_path, "r") as f:
            html = f.read()

        # Extract and parse the embedded JSON
        start = html.find("const DATA = ") + len("const DATA = ")
        end = html.find(";", start)
        json_str = html[start:end]

        parsed = json.loads(json_str)
        assert parsed["metadata"]["total_titles"] == 42
        assert parsed["metadata"]["total_genres"] == 5
