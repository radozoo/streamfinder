"""What the incremental parse is allowed to skip.

The risk here is not that it re-parses too much — that is only slow. It is that it
skips a page that did change, and the catalog silently keeps a stale row that no
gate would notice, because the row is present and well-formed. These pin the cases
where skipping must NOT happen.
"""

import time

import pytest

from csfd_vod.parse_state import ParseState, code_fingerprint, plan_parse


class FakeCache:
    """Just enough HTMLCache to answer 'where does this URL live on disk'."""

    def __init__(self, root):
        self.root = root

    def _html_path(self, url):
        return self.root / f"{abs(hash(url)) % 10**8}.html"


@pytest.fixture
def repo(tmp_path):
    """A cache with three pages and a transformation package to fingerprint."""
    html = tmp_path / "cache" / "html"
    html.mkdir(parents=True)
    cache = FakeCache(html)
    urls = [f"https://www.csfd.cz/film/{i}-x/prehled/" for i in range(3)]
    for u in urls:
        cache._html_path(u).write_text("<html></html>", encoding="utf-8")

    src = tmp_path / "src" / "csfd_vod" / "transformation"
    src.mkdir(parents=True)
    (src / "parser.py").write_text("VERSION = 1", encoding="utf-8")
    (tmp_path / "src" / "csfd_vod" / "loading").mkdir(parents=True)
    selectors = tmp_path / "selectors.json"
    selectors.write_text("{}", encoding="utf-8")

    return {
        "root": tmp_path, "cache": cache, "urls": urls,
        "cache_dir": tmp_path / "cache", "selectors": selectors,
        "parser_py": src / "parser.py",
    }


def _plan(repo, **kw):
    return plan_parse(
        cache=repo["cache"], urls=repo["urls"], list_pages=kw.pop("list_pages", []),
        cache_dir=repo["cache_dir"], selectors_path=repo["selectors"],
        repo_root=repo["root"], **kw,
    )


def _mark_done(repo, plan):
    ParseState(repo["cache_dir"]).write(plan["fingerprint"], plan["started_at"])


def test_first_run_is_full(repo):
    plan = _plan(repo)
    assert plan["full"] is True
    assert plan["urls"] == repo["urls"]
    assert "no previous parse" in plan["reason"]


def test_second_run_skips_everything_untouched(repo):
    _mark_done(repo, _plan(repo))
    plan = _plan(repo)
    assert plan["full"] is False
    assert plan["urls"] == []
    assert plan["skipped"] == 3


def test_a_rewritten_page_comes_back(repo):
    _mark_done(repo, _plan(repo))
    time.sleep(0.01)
    changed = repo["urls"][1]
    repo["cache"]._html_path(changed).write_text("<html>new</html>", encoding="utf-8")
    plan = _plan(repo)
    assert plan["urls"] == [changed]


def test_a_changed_parser_forces_a_full_pass(repo):
    """The files did not move, but every row they produce may differ."""
    _mark_done(repo, _plan(repo))
    repo["parser_py"].write_text("VERSION = 2", encoding="utf-8")
    plan = _plan(repo)
    assert plan["full"] is True
    assert plan["urls"] == repo["urls"]
    assert "parser" in plan["reason"]


def test_changed_selectors_force_a_full_pass(repo):
    _mark_done(repo, _plan(repo))
    repo["selectors"].write_text('{"title": "h1"}', encoding="utf-8")
    assert _plan(repo)["full"] is True


def test_force_full_overrides_a_clean_watermark(repo):
    _mark_done(repo, _plan(repo))
    plan = _plan(repo, force_full=True)
    assert plan["full"] is True and plan["urls"] == repo["urls"]


def test_a_changed_list_page_pulls_in_its_titles(repo, monkeypatch):
    """A running serial gets a new vod_date from a listing, not from its own page."""
    _mark_done(repo, _plan(repo))
    time.sleep(0.01)
    listing = repo["cache_dir"] / "vod_lists"
    listing.mkdir()
    page = listing / "2026-08.html"
    page.write_text("<html></html>", encoding="utf-8")

    mentioned = repo["urls"][2]

    class FakeListParser:
        def parse(self, html, source=None):
            return [{"film_url": mentioned, "vod_date": "2026-08-06"}]

    import csfd_vod.transformation.list_parser as lp
    monkeypatch.setattr(lp, "VODListParser", FakeListParser)

    plan = _plan(repo, list_pages=[page])
    # None of the title pages moved — this URL is here only because the listing did.
    assert plan["urls"] == [mentioned]


def test_an_unreadable_list_page_falls_back_to_full(repo, monkeypatch):
    """Never let a broken input quietly narrow the work."""
    _mark_done(repo, _plan(repo))
    time.sleep(0.01)
    listing = repo["cache_dir"] / "vod_lists"
    listing.mkdir()
    page = listing / "broken.html"
    page.write_text("<html></html>", encoding="utf-8")

    class ExplodingParser:
        def parse(self, html, source=None):
            raise ValueError("boom")

    import csfd_vod.transformation.list_parser as lp
    monkeypatch.setattr(lp, "VODListParser", ExplodingParser)

    plan = _plan(repo, list_pages=[page])
    assert plan["full"] is True
    assert "unreadable" in plan["reason"]


def test_watermark_is_the_start_time_not_the_finish(repo):
    """A page written mid-run must be picked up next time, not assumed parsed."""
    plan = _plan(repo)
    assert plan["started_at"] <= time.time()
    _mark_done(repo, plan)

    # Simulate a page saved while that run was still parsing.
    late = repo["urls"][0]
    p = repo["cache"]._html_path(late)
    import os
    os.utime(p, (plan["started_at"] + 0.001, plan["started_at"] + 0.001))

    assert _plan(repo)["urls"] == [late]


def test_a_crashed_run_redoes_its_work(repo):
    """State is written only after a successful load."""
    _plan(repo)  # planned, then "crashed" — nothing recorded
    plan = _plan(repo)
    assert plan["full"] is True


def test_fingerprint_is_stable_across_calls(repo):
    a = code_fingerprint(repo["selectors"], repo["root"])
    b = code_fingerprint(repo["selectors"], repo["root"])
    assert a == b and len(a) == 64
