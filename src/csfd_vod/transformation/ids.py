"""ČSFD's identity, read off a URL.

A ČSFD URL is a chain of "/{id}-slug/" segments: the first is the top-level work,
the last is the entity the page is about.

    /film/{ROOT}-slug/{CHILD}-slug/prehled/   → an episode or season under a serial
    /film/{ID}-slug/prehled/                  → a top-level work (root_id == csfd_id)

Two things make this less obvious than it looks, and both have already cost us data:

  * A plain ``/film/(\\d+)`` sees only the FIRST segment, so every episode collapses
    onto its serial. That is the difference between "Hourglass" and "The Walking
    Dead: Dead City".
  * The slug is optional. A title whose name has no alphanumerics slugifies to
    nothing, giving a bare "/film/17338/" — the film "$". Requiring "-slug" left
    those rows with no hierarchy ids at all.

Kept in one place because the parser and the VOD-event loader must agree on what a
URL identifies; the slug in it is NOT part of that identity (ČSFD renames slugs —
see docs/csfd-scraping-rules.md §11).
"""

from __future__ import annotations

import re

_SEGMENT_IDS = re.compile(r"/(\d+)(?:-[^/]*)?(?=/)")


def segment_ids(url: str) -> list[int]:
    """Every "/{id}-slug/" id in `url`, outermost first."""
    return [int(i) for i in _SEGMENT_IDS.findall(url or "")]


def csfd_id(url: str) -> int | None:
    """The id of the entity the page is about — the LAST segment."""
    ids = segment_ids(url)
    return ids[-1] if ids else None


def root_id(url: str) -> int | None:
    """The id of the top-level work — the FIRST segment."""
    ids = segment_ids(url)
    return ids[0] if ids else None
