"""Tests for VOD title parser."""

import pytest
from csfd_vod.transformation.parser import VODTitleParser
from csfd_vod.transformation.models import VODTitle


SAMPLE_HTML = """
<html>
<head><title>Test Title</title></head>
<body>
    <div class="film-header"><h1>The Matrix</h1></div>
    <div class="origin">USA <span class="bullet"></span>
        <span>(1999) <span class="bullet"></span></span>2 h 16 min
    </div>
    <div class="genres"><a href="/zaner/1/">Science Fiction</a> / <a href="/zaner/2/">Action</a></div>
    <div>
        <h4>Režie:</h4>
        <a href="/tvurce/1-lana-wachowski/prehled/">Lana Wachowski</a>,
        <a href="/tvurce/2-lilly-wachowski/prehled/">Lilly Wachowski</a>
    </div>
    <div>
        <h4>Hrají:</h4>
        <a href="/tvurce/3-keanu-reeves/prehled/">Keanu Reeves</a>,
        <a href="/tvurce/4-laurence-fishburne/prehled/">Laurence Fishburne</a>
    </div>
    <div class="film-vod-list">
        <a href="/vod/netflix/">Netflix</a>
    </div>
</body>
</html>
"""

SELECTORS = {
    "title_page": {
        "title_selector": ".film-header h1",
        "genre_selector": ".genres a",
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
    """Test that parser extracts year from .origin div."""
    url = "https://csfd.cz/film/1/the-matrix/"
    result = parser.parse(SAMPLE_HTML, url)

    assert result.year == 1999
    assert result.countries == "USA"
    assert result.director == "Lana Wachowski, Lilly Wachowski"
    assert result.actors == "Keanu Reeves, Laurence Fishburne"
    assert result.vod_platforms == "Netflix"


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
