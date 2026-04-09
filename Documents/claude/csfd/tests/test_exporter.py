"""Tests for data exporter module."""

import json
import tempfile
from pathlib import Path

import pytest

from csfd_vod.export.exporter import DataExporter
from csfd_vod.export.dashboard_generator import DashboardGenerator


@pytest.fixture
def sample_export_data():
    """Sample exported data for testing."""
    return {
        "metadata": {
            "export_timestamp": "2026-04-09T12:34:56Z",
            "total_titles": 100,
            "total_genres": 20,
            "total_directors": 50,
            "total_actors": 75,
            "total_countries": 15,
            "total_platforms": 8,
            "date_range": ["2020-01-01", "2026-04-09"],
        },
        "statistics": {
            "genres_by_count": [
                {"name": "Drama", "count": 45},
                {"name": "Comedy", "count": 30},
            ],
            "countries_by_count": [
                {"name": "United States", "count": 60},
                {"name": "United Kingdom", "count": 20},
            ],
            "platforms_by_count": [
                {"name": "Netflix", "count": 50},
                {"name": "Prime", "count": 40},
            ],
            "years_by_count": [
                {"year": 2020, "count": 30},
                {"year": 2019, "count": 25},
            ],
            "decade_distribution": [
                {"decade": "2020s", "count": 50},
                {"decade": "2010s", "count": 40},
            ],
        },
        "titles": [
            {
                "title_id": 1,
                "url_id": "http://example.com/1",
                "title": "Test Title 1",
                "year": 2020,
                "director": "Test Director",
                "actors": "Test Actor 1, Test Actor 2",
                "link": "http://example.com/1",
                "date_added": "2020-01-01",
                "date_scraped": "2026-04-09T00:00:00",
                "created_at": "2026-04-09T00:00:00",
                "updated_at": "2026-04-09T00:00:00",
                "genres": ["Drama", "Comedy"],
                "directors": ["Test Director"],
                "actors_list": ["Test Actor 1", "Test Actor 2"],
                "countries": ["United States"],
                "platforms": ["Netflix"],
            }
        ],
    }


def test_dashboard_generator_creates_html(sample_export_data):
    """Test dashboard generator creates valid HTML file."""
    generator = DashboardGenerator()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "dashboard.html"

        result = generator.generate(sample_export_data, str(output_path))

        assert result["success"] is True
        assert output_path.exists()
        assert result["file_size_kb"] > 0
        assert result["titles_rendered"] == 100


def test_dashboard_html_contains_data(sample_export_data):
    """Test generated dashboard HTML contains the data."""
    generator = DashboardGenerator()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "dashboard.html"
        generator.generate(sample_export_data, str(output_path))

        with open(output_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Check for key content
        assert "CSFD VOD Dashboard" in html_content
        assert "100" in html_content  # total_titles
        assert "Drama" in html_content  # genre name
        assert "Netflix" in html_content  # platform name
        assert "Plotly" in html_content  # chart library


def test_dashboard_html_is_valid_html(sample_export_data):
    """Test generated dashboard is valid HTML."""
    generator = DashboardGenerator()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "dashboard.html"
        generator.generate(sample_export_data, str(output_path))

        with open(output_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Check for basic HTML structure
        assert "<!DOCTYPE html>" in html_content
        assert "<html" in html_content
        assert "<head>" in html_content
        assert "<body>" in html_content
        assert "</html>" in html_content


def test_dashboard_generator_creates_directory(sample_export_data):
    """Test dashboard generator creates output directory if needed."""
    generator = DashboardGenerator()

    with tempfile.TemporaryDirectory() as tmpdir:
        nested_path = Path(tmpdir) / "deep" / "nested" / "directory" / "dashboard.html"

        result = generator.generate(sample_export_data, str(nested_path))

        assert result["success"] is True
        assert nested_path.exists()


def test_dashboard_with_empty_statistics(sample_export_data):
    """Test dashboard generator handles empty statistics."""
    sample_export_data["statistics"]["genres_by_count"] = []
    sample_export_data["statistics"]["platforms_by_count"] = []

    generator = DashboardGenerator()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "dashboard.html"

        result = generator.generate(sample_export_data, str(output_path))

        assert result["success"] is True
        assert output_path.exists()


def test_export_data_structure(sample_export_data):
    """Test exported data has correct structure."""
    assert "metadata" in sample_export_data
    assert "statistics" in sample_export_data
    assert "titles" in sample_export_data

    metadata = sample_export_data["metadata"]
    assert "export_timestamp" in metadata
    assert "total_titles" in metadata
    assert "total_genres" in metadata

    stats = sample_export_data["statistics"]
    assert "genres_by_count" in stats
    assert "countries_by_count" in stats
    assert "platforms_by_count" in stats


def test_dashboard_data_embedded_as_json(sample_export_data):
    """Test that data is properly embedded in HTML as JSON."""
    generator = DashboardGenerator()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "dashboard.html"
        generator.generate(sample_export_data, str(output_path))

        with open(output_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Extract JSON from HTML
        start_marker = "const DATA = "
        start_idx = html_content.find(start_marker)
        assert start_idx >= 0, "Data not found in HTML"

        # Find the closing semicolon
        end_idx = html_content.find(";", start_idx)
        json_str = html_content[start_idx + len(start_marker) : end_idx]

        # Try to parse the JSON
        extracted_data = json.loads(json_str)
        assert extracted_data["metadata"]["total_titles"] == 100
        assert len(extracted_data["titles"]) == 1
