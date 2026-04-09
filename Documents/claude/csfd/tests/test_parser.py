"""Tests for VOD title parser."""

import pytest
from csfd_vod.transformation.parser import VODTitleParser
from csfd_vod.transformation.models import VODTitle


SAMPLE_HTML = """
<html>
<head><title>Test Title</title></head>
<body>
    <h1 class="title">The Matrix</h1>
    <span class="year">(1999)</span>
    <span class="genre">Science Fiction</span>
    <span class="genre">Action</span>
    <a data-role="director">Lana Wachowski</a>
    <a data-role="actor">Keanu Reeves</a>
    <a data-role="actor">Laurence Fishburne</a>
    <span class="country">USA</span>
    <span class="vod-platform">Netflix</span>
</body>
</html>
"""

SELECTORS = {
    "title_page": {
        "title_selector": "h1.title",
        "year_selector": "span.year",
        "genre_selector": "span.genre",
        "director_selector": "a[data-role='director']",
        "actors_selector": "a[data-role='actor']",
        "country_selector": "span.country",
        "vod_selector": "span.vod-platform",
    }
}


@pytest.fixture
def parser():
    """Create a parser with test selectors."""
    return VODTitleParser(SELECTORS)


def test_parser_extracts_title(parser):
    """Test that parser extracts title correctly."""
    url = "https://csfd.cz/film/1/the-matrix/"
    result = parser.parse(SAMPLE_HTML, url)

    assert result is not None
    assert isinstance(result, VODTitle)
    assert result.title == "The Matrix"


def test_parser_extracts_year(parser):
    """Test that parser extracts year correctly."""
    url = "https://csfd.cz/film/1/the-matrix/"
    result = parser.parse(SAMPLE_HTML, url)

    assert result.year == 1999


def test_parser_handles_missing_title(parser):
    """Test that parser returns None when title is missing."""
    html = "<html><body><span class='year'>(1999)</span></body></html>"
    url = "https://csfd.cz/film/1/missing-title/"
    result = parser.parse(html, url)

    assert result is None


def test_vod_title_validation():
    """Test VODTitle model validation."""
    # Valid title
    valid_title = VODTitle(
        url_id="https://csfd.cz/film/1/test/",
        title="Test Title",
        link="https://csfd.cz/film/1/test/",
    )
    assert valid_title.title == "Test Title"

    # Invalid year (too old)
    with pytest.raises(ValueError):
        VODTitle(
            url_id="https://csfd.cz/film/1/test/",
            title="Test Title",
            year=1800,
            link="https://csfd.cz/film/1/test/",
        )

    # Invalid year (future)
    with pytest.raises(ValueError):
        VODTitle(
            url_id="https://csfd.cz/film/1/test/",
            title="Test Title",
            year=2050,
            link="https://csfd.cz/film/1/test/",
        )

    # Empty title
    with pytest.raises(ValueError):
        VODTitle(
            url_id="https://csfd.cz/film/1/test/",
            title="",
            link="https://csfd.cz/film/1/test/",
        )
