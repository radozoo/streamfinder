"""Deciding what `parse` actually has to re-read.

A normal refresh changes almost nothing. The 6 Aug run downloaded 1 new page and
re-scraped 200 hot ones, then spent ~24 minutes re-parsing all 51,075 cached pages
and another 3 minutes re-loading every row — to write 201 titles' worth of changes.

So parse can work from the cache's own mtimes: a page whose file has not been
touched since the last successful load cannot produce a different row. Two things
make that unsafe, and both are checked here rather than left to whoever remembers:

  1. **The parser changed.** Then every page can produce a different row even though
     no file moved. Guarded by fingerprinting the code that turns HTML into rows —
     the transformation package, the loader, and the selectors file. Any change
     forces a full pass.

  2. **A list page changed.** /vod listing pages carry vod_date, distributor, type
     and platform for titles whose own detail page was never re-downloaded — this is
     the normal case for a running serial. Those titles must be re-parsed too, so a
     changed list page pulls in every title it mentions.

State lives next to the cache it describes, and is written only after a load
succeeds. A crashed run therefore re-does its work rather than skipping it.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Iterable, Optional

STATE_FILENAME = "parse_state.json"

# Everything whose behaviour decides what a cached page turns into. A change in any
# of these invalidates every previously parsed row, not just the pages that moved.
_FINGERPRINT_GLOBS = (
    "src/csfd_vod/transformation/*.py",
    "src/csfd_vod/loading/*.py",
)


def code_fingerprint(selectors_path: str | Path, repo_root: str | Path = ".") -> str:
    """A digest of the code and config that decide what a cached page parses into."""
    root = Path(repo_root)
    parts: list[bytes] = []
    paths: list[Path] = []
    for pattern in _FINGERPRINT_GLOBS:
        paths.extend(sorted(root.glob(pattern)))
    sel = Path(selectors_path)
    if sel.exists():
        paths.append(sel)
    for path in paths:
        try:
            parts.append(path.name.encode())
            parts.append(path.read_bytes())
        except OSError:
            # Unreadable input means we cannot prove nothing changed.
            parts.append(b"<unreadable>")
    return hashlib.sha256(b"".join(parts)).hexdigest()


class ParseState:
    """The 'what did we last parse, and with what code' marker."""

    def __init__(self, cache_dir: str | Path):
        self.path = Path(cache_dir) / STATE_FILENAME

    def read(self) -> Optional[dict]:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, dict) or "last_parse_at" not in data:
            return None
        return data

    def write(self, fingerprint: str, parsed_at: float) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "last_parse_at": parsed_at,
                    "fingerprint": fingerprint,
                    "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def plan_parse(
    *,
    cache,
    urls: Iterable[str],
    list_pages: Iterable[Path],
    cache_dir: str | Path,
    selectors_path: str | Path,
    repo_root: str | Path = ".",
    force_full: bool = False,
) -> dict:
    """Decide which URLs this run has to parse.

    Returns {"full": bool, "reason": str, "urls": [...], "skipped": int,
             "fingerprint": str, "started_at": float}.

    `started_at` is captured BEFORE any parsing, and is what should be stored as the
    new watermark — using the finish time would silently drop a page written while
    the run was in flight.
    """
    started_at = time.time()
    fingerprint = code_fingerprint(selectors_path, repo_root)
    urls = list(urls)

    state = ParseState(cache_dir).read()
    if force_full:
        reason = "--full requested"
    elif state is None:
        reason = "no previous parse recorded"
    elif state.get("fingerprint") != fingerprint:
        reason = "parser, loader or selectors changed"
    else:
        reason = ""

    if reason:
        return {
            "full": True, "reason": reason, "urls": urls, "skipped": 0,
            "fingerprint": fingerprint, "started_at": started_at,
        }

    watermark = float(state["last_parse_at"])

    def touched(path: Path) -> bool:
        try:
            return path.stat().st_mtime > watermark
        except OSError:
            return True  # cannot prove it is unchanged

    changed = [u for u in urls if touched(cache._html_path(u))]

    # A changed list page carries fresh vod_date/platform for titles whose own page
    # was never re-downloaded — the normal case for a running serial.
    stale_lists = [p for p in list_pages if touched(p)]
    from_lists: set[str] = set()
    if stale_lists:
        from csfd_vod.transformation.list_parser import VODListParser

        known = set(urls)
        parser = VODListParser()
        for page in stale_lists:
            try:
                for entry in parser.parse(page.read_text(encoding="utf-8"), source=page.name):
                    film_url = entry.get("film_url")
                    if film_url in known:
                        from_lists.add(film_url)
            except Exception:
                # An unreadable list page must not silently narrow the work.
                return {
                    "full": True, "reason": f"list page unreadable: {page.name}",
                    "urls": urls, "skipped": 0,
                    "fingerprint": fingerprint, "started_at": started_at,
                }

    selected = set(changed) | from_lists
    ordered = [u for u in urls if u in selected]
    return {
        "full": False,
        "reason": f"{len(changed)} page(s) changed, {len(from_lists)} pulled in by "
                  f"{len(stale_lists)} changed list page(s)",
        "urls": ordered,
        "skipped": len(urls) - len(ordered),
        "fingerprint": fingerprint,
        "started_at": started_at,
    }
