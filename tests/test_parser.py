"""Tests for VOD title parser and list parser."""

import json
import pytest
from datetime import date

from csfd_vod.transformation.parser import VODTitleParser
from csfd_vod.transformation.list_parser import VODListParser
from csfd_vod.transformation.models import VODTitle


SELECTORS = {
    "title_page": {
        "title_selector": ".film-header h1",
        "genre_selector": ".genres a",
    }
}

SAMPLE_HTML = """
<html>
<head><title>Test Title</title></head>
<body>
    <div class="film-header-name">
        <h1 class="film-header">The Matrix</h1>
        <ul class="film-names"><li>Matrix</li></ul>
        <span class="type">(film)</span>
    </div>
    <div class="film-header"><h1>The Matrix</h1></div>
    <div class="origin">USA <span class="bullet"></span>
        <span>(1999) <span class="bullet"></span></span>2 h 16 min
    </div>
    <!-- Real CSFD markup: linked genres, <span class="bullet"> separators, and
         secondary genres as BARE TEXT (no /zanry/ page). See rules §4. -->
    <div class="genres"><a href="/zaner/1/">Science Fiction</a><span class="bullet">/</span><a href="/zaner/2/">Action</a><span class="bullet">/</span>Mysteriózní</div>
    <div>
        <h4>Režie:</h4>
        <a href="/tvurce/1/">Lana Wachowski</a>,
        <a href="/tvurce/2/">Lilly Wachowski</a>
    </div>
    <div>
        <h4>Scénář:</h4>
        <a href="/tvurce/1/">Lana Wachowski</a>
    </div>
    <div>
        <h4>Kamera:</h4>
        <a href="/tvurce/5/">Bill Pope</a>
    </div>
    <div>
        <h4>Hudba:</h4>
        <a href="/tvurce/6/">Don Davis</a>
    </div>
    <div>
        <h4>Hrají:</h4>
        <a href="/tvurce/3/">Keanu Reeves</a>,
        <a href="/tvurce/4/">Laurence Fishburne</a>
    </div>
    <div class="plot-full">Hacker Neo discovers the truth about the Matrix.</div>
    <div class="film-rating-average">87%</div>
    <!-- CSFD groups thousands with a NON-BREAKING SPACE (U+00A0). -->
    <div class="more-modal-ratings-fanclub">Hodnocení (131 654) golfista POMO</div>
    <div class="box-tags">
        <a href="/stitky/1/">sci-fi</a>
        <a href="/stitky/2/">akce</a>
    </div>
    <img src="/film/posters/12345.jpg" alt="poster" />
    <div class="film-vod-list">
        <h3><a href="/vod/">VOD</a></h3>
        <div class="box-film-vod-services">
            <a href="/vod/netflix/">Netflix</a>
            <a href="/vod/vice/">více</a>
        </div>
    </div>
    <div class="updated-box-content-padding">Na VOD od 1.1.2020Netflix</div>
    <article class="article-review">
        <a class="user-title-name" href="/uzivatel/1/">Jan Novak</a>
        <p>Tento film je absolutne skvelý a vrelo ho odporucam vsetkym fanusikom sci-fi.</p>
        <span class="stars stars-5"></span>
    </article>
</body>
</html>
"""

SAMPLE_HTML_CHILD_URL = """
<html>
<body>
    <div class="film-header"><h1>Pilot</h1></div>
    <div class="origin">USA, (2020), 45 min</div>
    <div class="genres"><a href="/zaner/1/">Drama</a></div>
    <div class="film-rating-average">? %</div>
</body>
</html>
"""

SAMPLE_LIST_HTML = """
<html>
<body>
    <div class="update-box-sub-header update-box-sub-header-date">
        <h2 class="date-title">V nabídce od 5. 4. 2026</h2>
    </div>
    <article class="article">
        <div class="article-img"><a href="/film/12345-the-matrix/prehled/">poster</a></div>
        <div class="film-title-info">
            <span class="info">1999</span>
        </div>
        <p>Distributor: Netflix</p>
    </article>
    <article class="article">
        <div class="article-img"><a href="/film/99999/11111-pilot/prehled/">poster</a></div>
        <div class="film-title-info">
            <span class="info">2020</span>
            <span class="info">epizoda</span>
        </div>
        <p>Distributor: HBO Max</p>
    </article>
</body>
</html>
"""


@pytest.fixture
def parser():
    """Create a parser with test selectors."""
    return VODTitleParser(SELECTORS)


@pytest.fixture
def list_parser():
    return VODListParser()


# ---------------------------------------------------------------------------
# Detail page parser tests
# ---------------------------------------------------------------------------

def test_parser_extracts_title(parser):
    url = "https://www.csfd.cz/film/1-the-matrix/prehled/"
    result = parser.parse(SAMPLE_HTML, url)
    assert result is not None
    assert isinstance(result, VODTitle)
    assert result.title == "The Matrix"


def test_parser_extracts_basic_fields(parser):
    url = "https://www.csfd.cz/film/1-the-matrix/prehled/"
    result = parser.parse(SAMPLE_HTML, url)
    assert result.year == 1999
    assert result.countries == "USA"
    assert result.director == "Lana Wachowski, Lilly Wachowski"
    assert result.actors == "Keanu Reeves, Laurence Fishburne"
    assert result.vod_platforms == "Netflix"
    # Bare-text genre included: dropping those loses a genre on ~34% of titles.
    assert result.genres == "Science Fiction / Action / Mysteriózní"


def test_parser_extracts_new_fields(parser):
    url = "https://www.csfd.cz/film/1-the-matrix/prehled/"
    result = parser.parse(SAMPLE_HTML, url)
    assert result.script == "Lana Wachowski"
    assert result.camera == "Bill Pope"
    assert result.music == "Don Davis"
    assert result.plot == "Hacker Neo discovers the truth about the Matrix."
    assert result.rating == 87
    assert result.tags == "sci-fi, akce"
    assert result.premiere_detail is not None and "Na VOD od" in result.premiere_detail
    assert result.title_type == "film"
    assert result.scraped_at is not None


def test_parser_extracts_reviews(parser):
    url = "https://www.csfd.cz/film/1-the-matrix/prehled/"
    result = parser.parse(SAMPLE_HTML, url)
    assert result.reviews is not None
    reviews = json.loads(result.reviews)
    assert len(reviews) == 1
    assert reviews[0]["author"] == "Jan Novak"
    assert reviews[0]["stars"] == 5
    assert reviews[0]["text"] is not None


def test_parser_rating_null_for_question_mark(parser):
    url = "https://www.csfd.cz/film/99999/11111-pilot/prehled/"
    result = parser.parse(SAMPLE_HTML_CHILD_URL, url)
    assert result is not None
    assert result.rating is None


def test_parser_child_url_sets_hierarchy_and_type(parser):
    """A two-segment URL is a child: first id is the serial, last is the episode.

    Supersedes the old parent_url assertion — hierarchy moved to root_id/csfd_id
    and parent_url is deprecated (see docs/csfd-scraping-rules §3).
    """
    url = "https://www.csfd.cz/film/99999/11111-pilot/prehled/"
    result = parser.parse(SAMPLE_HTML_CHILD_URL, url)
    assert result.root_id == 99999
    assert result.csfd_id == 11111
    assert result.title_type == "epizoda"


def test_parser_votes_count_keeps_thousands_groups(parser):
    """Votes above 999 must survive the non-breaking-space thousands separator.

    A plain (\\d+) stopped at the first group, storing 131654 as 131 — silently
    truncating every popular title and skewing anything ranked by popularity.
    """
    url = "https://www.csfd.cz/film/1-the-matrix/prehled/"
    result = parser.parse(SAMPLE_HTML, url)
    assert result.votes_count == 131654


def test_parser_slugless_url_still_gets_hierarchy(parser):
    """A title whose name has no alphanumerics ("$") has an empty slug."""
    url = "https://www.csfd.cz/film/17338/prehled/"
    result = parser.parse(SAMPLE_HTML, url)
    assert result.root_id == 17338
    assert result.csfd_id == 17338


def test_parser_handles_missing_title(parser):
    html = "<html><body><span class='year'>(1999)</span></body></html>"
    url = "https://www.csfd.cz/film/1-missing/prehled/"
    result = parser.parse(html, url)
    assert result is None


# ---------------------------------------------------------------------------
# VODTitle model validation tests
# ---------------------------------------------------------------------------

def test_vod_title_validation():
    valid_title = VODTitle(
        url_id="https://www.csfd.cz/film/1/prehled/",
        title="Test Title",
        link="https://www.csfd.cz/film/1/prehled/",
    )
    assert valid_title.title == "Test Title"

    with pytest.raises(ValueError):
        VODTitle(url_id="https://www.csfd.cz/film/1/", title="T", year=1800, link="x")

    with pytest.raises(ValueError):
        VODTitle(url_id="https://www.csfd.cz/film/1/", title="T", year=2050, link="x")

    with pytest.raises(ValueError):
        VODTitle(url_id="https://www.csfd.cz/film/1/", title="", link="x")

    with pytest.raises(ValueError):
        VODTitle(url_id="https://www.csfd.cz/film/1/", title="T", rating=101, link="x")


def test_vod_title_new_fields():
    title = VODTitle(
        url_id="https://www.csfd.cz/film/1/prehled/",
        title="Test",
        link="https://www.csfd.cz/film/1/prehled/",
        rating=75,
        title_type="serial",
        vod_date=date(2024, 1, 15),
        distributor="Netflix",
    )
    assert title.rating == 75
    assert title.title_type == "serial"
    assert title.vod_date == date(2024, 1, 15)
    assert title.distributor == "Netflix"


# ---------------------------------------------------------------------------
# List page parser tests
# ---------------------------------------------------------------------------

def test_list_parser_extracts_entries(list_parser):
    results = list_parser.parse(SAMPLE_LIST_HTML)
    assert len(results) == 2


def test_list_parser_extracts_vod_date(list_parser):
    results = list_parser.parse(SAMPLE_LIST_HTML)
    assert results[0]["vod_date"] == date(2026, 4, 5)
    assert results[1]["vod_date"] == date(2026, 4, 5)


def test_list_parser_extracts_film_url(list_parser):
    results = list_parser.parse(SAMPLE_LIST_HTML)
    assert results[0]["film_url"] == "https://www.csfd.cz/film/12345-the-matrix/prehled/"
    assert results[1]["film_url"] == "https://www.csfd.cz/film/99999/11111-pilot/prehled/"


def test_list_parser_extracts_distributor(list_parser):
    results = list_parser.parse(SAMPLE_LIST_HTML)
    assert results[0]["distributor"] == "Netflix"
    assert results[1]["distributor"] == "HBO Max"


def test_list_parser_extracts_episode_type(list_parser):
    results = list_parser.parse(SAMPLE_LIST_HTML)
    assert results[1]["list_type"] == "epizoda"
