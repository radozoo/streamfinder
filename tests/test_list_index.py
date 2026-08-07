"""What the cached listing index is allowed to reuse.

Reusing too little is only slow. Reusing too much is a title that quietly keeps a
wrong availability date or loses a platform — a well-formed row no gate would
question. These pin the cases where a cached page must NOT be trusted, and the
merge rules that decide which listing wins when several mention the same title.
"""

import json
import os
from datetime import date

import pytest

from csfd_vod.list_index import ListIndex, list_code_fingerprint
from csfd_vod.transformation.list_merge import merge_list_metadata


PAGE = """
<div class="update-box-sub-header"><span class="date-title">V nabídce od 5. 4. 2026</span></div>
<article class="article">
  <div class="article-img"><a href="/film/1-alfa/prehled/"></a></div>
  <div class="film-title-info"><span class="info">(2026)</span><span class="info">serial</span></div>
  <p>Distributor: Netflix</p>
  <a href="/vod/netflix/">Netflix</a>
</article>
"""


@pytest.fixture
def repo(tmp_path):
    """A cache dir, a listings dir with one page, and the code the index fingerprints."""
    lists = tmp_path / "cache" / "vod_lists"
    lists.mkdir(parents=True)
    (lists / "2026_04_p01.html").write_text(PAGE, encoding="utf-8")

    src = tmp_path / "src" / "csfd_vod" / "transformation"
    src.mkdir(parents=True)
    (src / "list_parser.py").write_text("VERSION = 1", encoding="utf-8")
    (src / "text.py").write_text("VERSION = 1", encoding="utf-8")

    return {"root": tmp_path, "cache_dir": tmp_path / "cache", "lists": lists}


def index(repo, **kw):
    return ListIndex(repo["cache_dir"], repo["lists"], repo_root=repo["root"], **kw)


class Title:
    """Just enough VODTitle for the merge to write into."""

    def __init__(self, url_id, **kw):
        self.url_id = url_id
        self.vod_date = kw.get("vod_date")
        self.distributor = kw.get("distributor")
        self.title_type = kw.get("title_type")
        self.vod_platforms = kw.get("vod_platforms")


# --- what the index may reuse ------------------------------------------------

def test_first_run_parses_everything(repo):
    pages, stats = index(repo).load()
    assert stats["reason"] == "no index yet"
    assert stats["reparsed"] == 1 and stats["reused"] == 0
    assert pages["2026_04_p01.html"][0]["film_url"].endswith("/film/1-alfa/prehled/")


def test_second_run_reparses_nothing(repo):
    first, _ = index(repo).load()
    second, stats = index(repo).load()
    assert stats["reparsed"] == 0 and stats["reused"] == 1
    assert second == first, "a cached page must round-trip to exactly what it parsed to"


def test_a_rewritten_page_is_read_again(repo, monkeypatch):
    index(repo).load()
    page = repo["lists"] / "2026_04_p01.html"
    page.write_text(PAGE.replace("1-alfa", "2-beta"), encoding="utf-8")
    pages, stats = index(repo).load()
    assert stats["reparsed"] == 1
    assert pages["2026_04_p01.html"][0]["film_url"].endswith("/film/2-beta/prehled/")


def test_a_page_rewritten_to_the_same_length_is_still_read_again(repo):
    """mtime is the signal; a same-size edit must not slip through on size alone.

    The new mtime is set explicitly rather than left to the clock, so the test pins
    the rule instead of the filesystem's timestamp resolution.
    """
    index(repo).load()
    page = repo["lists"] / "2026_04_p01.html"
    before = page.stat()
    page.write_text(PAGE.replace("1-alfa", "1-gama"), encoding="utf-8")
    os.utime(page, (before.st_atime, before.st_mtime + 10))
    assert page.stat().st_size == before.st_size
    pages, stats = index(repo).load()
    assert stats["reparsed"] == 1
    assert pages["2026_04_p01.html"][0]["film_url"].endswith("/film/1-gama/prehled/")


def test_a_changed_listing_parser_discards_the_whole_index(repo):
    index(repo).load()
    (repo["root"] / "src" / "csfd_vod" / "transformation" / "list_parser.py").write_text(
        "VERSION = 2", encoding="utf-8")
    _, stats = index(repo).load()
    assert stats["reason"] == "listing parser changed"
    assert stats["reparsed"] == 1


def test_a_changed_text_helper_discards_the_whole_index(repo):
    """split_services/clean_text decide platform names, so they count as the parser."""
    index(repo).load()
    (repo["root"] / "src" / "csfd_vod" / "transformation" / "text.py").write_text(
        "VERSION = 2", encoding="utf-8")
    _, stats = index(repo).load()
    assert stats["reason"] == "listing parser changed"


def test_a_changed_title_parser_does_not_discard_the_index(repo):
    """The title parser cannot affect a listing — throwing away 135s of work for it is waste."""
    index(repo).load()
    (repo["root"] / "src" / "csfd_vod" / "transformation" / "parser.py").write_text(
        "VERSION = 99", encoding="utf-8")
    _, stats = index(repo).load()
    assert stats["reparsed"] == 0


def test_force_full_overrides_a_clean_index(repo):
    index(repo).load()
    _, stats = index(repo).load(force_full=True)
    assert stats["reason"] == "--full requested" and stats["reparsed"] == 1


def test_a_corrupt_index_file_is_rebuilt_not_trusted(repo):
    index(repo).load()
    (repo["cache_dir"] / "list_index.json").write_text("{not json", encoding="utf-8")
    _, stats = index(repo).load()
    assert stats["reparsed"] == 1


def test_an_unreadable_page_is_not_cached_as_empty(repo, monkeypatch):
    """Storing a failure as 'this page said nothing' would bake the hole in forever."""
    from csfd_vod.transformation import list_parser as lp

    def explode(self, html, source=""):
        raise ValueError("boom")

    monkeypatch.setattr(lp.VODListParser, "parse", explode)
    pages, stats = index(repo).load()
    assert stats["unreadable"] == 1 and pages == {}

    monkeypatch.undo()
    pages, stats = index(repo).load()
    assert stats["reparsed"] == 1, "the failed page must be retried, not inherited"
    assert pages["2026_04_p01.html"]


def test_a_deleted_page_leaves_the_index(repo):
    index(repo).load()
    (repo["lists"] / "2026_04_p01.html").unlink()
    pages, _ = index(repo).load()
    assert pages == {}
    stored = json.loads((repo["cache_dir"] / "list_index.json").read_text())
    assert stored["pages"] == {}


# --- what the merge does with those entries ----------------------------------

def test_the_detail_page_wins_over_the_listing(repo):
    pages, _ = index(repo).load()
    t = Title("https://www.csfd.cz/film/1-alfa/prehled/",
              vod_date=date(2020, 1, 1), distributor="HBO", title_type="film")
    merge_list_metadata([t], pages)
    assert (t.vod_date, t.distributor, t.title_type) == (date(2020, 1, 1), "HBO", "film")


def test_the_listing_fills_what_the_detail_page_lacks(repo):
    pages, _ = index(repo).load()
    t = Title("https://www.csfd.cz/film/1-alfa/prehled/")
    merge_list_metadata([t], pages)
    assert t.vod_date == date(2026, 4, 5)
    assert t.distributor == "Netflix" and t.title_type == "serial"


def test_a_cached_iso_date_arrives_as_a_date_not_a_string(repo):
    """The model column is a date; a string here reaches SQL and is a different bug."""
    pages, _ = index(repo).load()
    assert isinstance(pages["2026_04_p01.html"][0]["vod_date"], str)
    t = Title("https://www.csfd.cz/film/1-alfa/prehled/")
    merge_list_metadata([t], pages)
    assert isinstance(t.vod_date, date)


def test_platforms_are_unioned_across_listings(repo):
    """A title on two services is on both — filling instead of unioning would drop one."""
    (repo["lists"] / "2026_05_p01.html").write_text(
        PAGE.replace("netflix", "max").replace(">Netflix<", ">Max<"), encoding="utf-8")
    pages, _ = index(repo).load()
    t = Title("https://www.csfd.cz/film/1-alfa/prehled/", vod_platforms="Netflix")
    merge_list_metadata([t], pages)
    assert [p.strip() for p in t.vod_platforms.split(",")] == ["Netflix", "Max"]


def test_the_earliest_listing_sets_the_date(repo):
    """Two listings, two dates: the merge must be order-stable, not last-write-wins."""
    (repo["lists"] / "2026_09_p01.html").write_text(
        PAGE.replace("5. 4. 2026", "9. 9. 2026"), encoding="utf-8")
    pages, _ = index(repo).load()
    t = Title("https://www.csfd.cz/film/1-alfa/prehled/")
    merge_list_metadata([t], pages)
    assert t.vod_date == date(2026, 4, 5)


def test_a_title_no_listing_mentions_is_untouched(repo):
    pages, _ = index(repo).load()
    t = Title("https://www.csfd.cz/film/999-nikde/prehled/")
    assert merge_list_metadata([t], pages) == 0
    assert t.vod_date is None and t.vod_platforms is None


def test_fingerprint_is_stable_across_calls(repo):
    assert list_code_fingerprint(repo["root"]) == list_code_fingerprint(repo["root"])
