"""Not re-reading 728 MB of listing HTML to learn what it said last time.

`parse` merges metadata from the /vod listings into the titles it parsed —
vod_date, distributor, type and platform, which for a running serial are often the
only source, because its episode's own detail page carries no VOD box. That merge
has to consider *every* listing, including one downloaded in 2015, since that may
be where a title's date came from.

Considering every listing does not mean re-parsing every listing. Turning those
2,407 files into 67,858 entries costs 135 seconds of BeautifulSoup and 2 seconds of
disk; the entries themselves are 11 MB of JSON that loads in 0.05 s. A listing file
is immutable once written — the scraper only ever rewrites the months it refetches —
so a page whose mtime and size have not moved parses to exactly what it parsed
before. Cache that, and only the handful of pages a discover run touched get read.

Correctness rests on two things, both checked here rather than assumed:

  1. **The listing parser changed.** Then a page's stored entries are wrong even
     though the file never moved. Fingerprinting list_parser.py and the text helpers
     it uses discards the whole index when either changes.
  2. **A page could not be read.** It is left out of the index rather than stored as
     empty, so the next run retries instead of inheriting a silent hole.

The index is a pure function of the files on disk, so it is safe to write as soon as
it is built — unlike parse_state, which must wait for the database load to succeed.

Entries are held in their JSON form throughout, with `vod_date` an ISO string rather
than a `date`. One representation everywhere means a freshly parsed page and a
cached one are indistinguishable to the caller, and the 67,858 dates are converted
only for the few hundred titles that actually match.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Optional

from csfd_vod.logger import get_logger
from csfd_vod.transformation.ids import csfd_id
from csfd_vod.transformation.list_parser import VODListParser

logger = get_logger(__name__)

INDEX_FILENAME = "list_index.json"

# Markers of the bot-protection interstitial ČSFD serves instead of a listing. It is
# perfectly readable HTML that parses to zero entries, so neither the read guard nor
# the parse guard below catches it — it lands in the index as "this page lists
# nothing", and every title it really carried loses its date, distributor and
# platform. Belt to the scraper's braces: the fetch should never have cached it, but
# an index that trusts one is how a single bad fetch outlives the fetch.
_CHALLENGE_MARKERS = ("not a bot", "within.website")


def _is_challenge_page(html: str) -> bool:
    head = html[:4096].lower()
    return any(m in head for m in _CHALLENGE_MARKERS)

# What decides the entries a listing page parses into. Deliberately narrower than
# parse_state's fingerprint: a change to the title parser must not throw away 135
# seconds of listing work it cannot possibly have affected.
_FINGERPRINT_FILES = (
    "src/csfd_vod/transformation/list_parser.py",
    "src/csfd_vod/transformation/text.py",
)


def list_code_fingerprint(repo_root: str | Path = ".") -> str:
    """A digest of the code that decides what a listing page parses into."""
    root = Path(repo_root)
    parts: list[bytes] = []
    for rel in _FINGERPRINT_FILES:
        path = root / rel
        parts.append(rel.encode())
        try:
            parts.append(path.read_bytes())
        except OSError:
            # Unreadable input means we cannot prove nothing changed.
            parts.append(b"<unreadable>")
    return hashlib.sha256(b"".join(parts)).hexdigest()


def _serialise(entry: dict[str, Any]) -> dict[str, Any]:
    """The parser hands back a `date`; JSON does not have one."""
    vod_date = entry.get("vod_date")
    return {**entry, "vod_date": vod_date.isoformat() if vod_date else None}


class ListIndex:
    """Parsed /vod listing entries, kept per page so a run re-reads only what moved."""

    def __init__(
        self,
        cache_dir: str | Path,
        list_html_dir: str | Path,
        repo_root: str | Path = ".",
    ):
        self.path = Path(cache_dir) / INDEX_FILENAME
        self.list_html_dir = Path(list_html_dir)
        self.repo_root = repo_root

    def _read(self) -> Optional[dict]:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, dict) or not isinstance(data.get("pages"), dict):
            return None
        return data

    def _write(self, fingerprint: str, pages: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Compact, not indented: this file is 11 MB and nobody reads it by eye.
        self.path.write_text(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "pages": pages,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

    def load(self, *, force_full: bool = False) -> tuple[dict[str, list[dict]], dict]:
        """Entries for every listing page, in filename order.

        Returns (pages, stats). `pages` maps filename → entries, with `vod_date` an
        ISO string. Filename order is what the merge relies on to stay deterministic:
        the earliest listing that mentions a title is the one whose date wins.
        """
        files = sorted(self.list_html_dir.glob("*.html")) if self.list_html_dir.exists() else []
        fingerprint = list_code_fingerprint(self.repo_root)
        cached = self._read()

        if force_full:
            reason = "--full requested"
        elif cached is None:
            reason = "no index yet"
        elif cached.get("fingerprint") != fingerprint:
            reason = "listing parser changed"
        else:
            reason = ""
        stored: dict = {} if reason else cached.get("pages", {})

        parser = VODListParser()
        pages: dict[str, list[dict]] = {}
        fresh: dict[str, dict] = {}
        reparsed = 0
        unreadable = 0

        for path in files:
            try:
                stat = path.stat()
            except OSError:
                stat = None
            prev = stored.get(path.name)

            if stat and prev and prev.get("mtime") == stat.st_mtime and prev.get("size") == stat.st_size:
                entries = prev["entries"]
            else:
                try:
                    html = path.read_text(encoding="utf-8")
                except OSError as e:
                    # Not stored, so the next run tries again rather than inheriting
                    # this page's absence as a fact.
                    logger.warning("list_page_read_failed", path=str(path), error=str(e))
                    unreadable += 1
                    continue
                if _is_challenge_page(html):
                    # Left out of the index, exactly like an unreadable page, so the
                    # next run retries instead of inheriting an empty listing as fact.
                    logger.warning("list_page_challenge_skipped", path=str(path), bytes=len(html))
                    unreadable += 1
                    continue
                try:
                    entries = [_serialise(e) for e in parser.parse(html, source=path.name)]
                except Exception as e:
                    logger.warning("list_page_parse_error", path=str(path), error=str(e))
                    unreadable += 1
                    continue
                reparsed += 1

            pages[path.name] = entries
            if stat:
                fresh[path.name] = {
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                    "entries": entries,
                }

        self._write(fingerprint, fresh)

        stats = {
            "pages": len(pages),
            "reparsed": reparsed,
            "reused": len(pages) - reparsed,
            "unreadable": unreadable,
            "entries": sum(len(e) for e in pages.values()),
            "reason": reason or "incremental",
        }
        return pages, stats

# A film/serial/season/episode overview page — the only shape the harvest keeps on
# the scrape queue. Mirrors VODScraper._TITLE_OVERVIEW_RE.
_OVERVIEW_RE = re.compile(r"^https://www\.csfd\.cz/film/\d+[^/]*/(?:\d+[^/]*/)?prehled/$")


def overview_urls(pages: dict[str, list[dict]], known: set[str] | None = None) -> list[str]:
    """Title URLs the cached listings name that `known` does not already cover.

    `vod_urls.json` is written from what a harvest saw during that run, and a URL that
    fell out between the fetch and the file is gone for good — 791 had leaked out by
    2026-09-07, 166 of them titles the catalog did not have at all. This is what puts
    them back, and it reads the index for the same reason everything else here does:
    re-parsing the 728 MB of listing HTML to answer the question took 85 seconds on
    every scrape and every nightly run, against 0.05 s for the index that already
    holds the answer.

    **`known` is compared by csfd_id, not by URL, and that is the whole subtlety.**
    ČSFD serves the same title under more than one slug — Czech and Slovak names side
    by side (`612768-greyhound-bitva-o-atlantik` and `-bitka-o-atlantik`, `hluboka-`
    and `hlboka-voda`) — and identity is the id, never the slug (rules doc §11). A
    URL-only comparison called every one of those a missing title: the first run
    recovered 625 such variants, scraping them created 62 duplicate rows, and because
    `dedupe_titles.py` prunes the losing URL from vod_urls.json, the next reconcile
    would have added it straight back. Ping-pong, forever, one scrape per night.
    """
    known_ids = {csfd_id(u) for u in (known or ())}
    out: dict[int, str] = {}
    for entries in pages.values():
        for entry in entries:
            url = entry.get("film_url")
            if not url or not _OVERVIEW_RE.match(url):
                continue
            cid = csfd_id(url)
            if cid is None or cid in known_ids:
                continue
            out.setdefault(cid, url)   # one slug per id, whichever the index names first
    return sorted(out.values())
