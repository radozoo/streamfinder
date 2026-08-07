"""Folding /vod listing metadata into the titles a run parsed.

A title's own detail page is not the whole story. Serials and episodes frequently
have no VOD box at all, so the listing that announced them is the only place their
platform and availability date exist. The listing is also where `distributor` and
the ČSFD-assigned type come from.

The detail page wins wherever it has an answer — this only fills gaps — except for
platforms, which are unioned, because a title can appear in several listings on
different services and each one is true.

Lifted out of main.py so it can be tested directly, and so it sits inside
`transformation/`, which parse_state fingerprints: a change to these rules changes
what rows come out of a cached page, and must therefore force a re-parse. In
main.py it was invisible to that check.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping


def merge_list_metadata(titles: Iterable, pages: Mapping[str, list[dict[str, Any]]]) -> int:
    """Fill in listing-only fields on `titles`, in place. Returns entries matched.

    `pages` maps listing filename → entries, iterated in sorted filename order so
    that the earliest listing mentioning a title is the one whose date and
    distributor stick. `vod_date` may be an ISO string (the cached form) or a
    `date`; both are accepted so a caller need not care where the entries came from.
    """
    title_by_url = {t.url_id: t for t in titles}
    matched = 0

    for name in sorted(pages):
        for entry in pages[name]:
            film_url = entry.get("film_url")
            if not film_url or film_url not in title_by_url:
                continue
            t = title_by_url[film_url]

            if not t.vod_date and entry.get("vod_date"):
                t.vod_date = _as_date(entry["vod_date"])
            if not t.distributor and entry.get("distributor"):
                t.distributor = entry["distributor"]
            if not t.title_type and entry.get("list_type"):
                t.title_type = entry["list_type"]

            # Union rather than fill: the authoritative source for serials and
            # episodes whose detail page has no VOD box.
            if entry.get("platforms"):
                existing = [p.strip() for p in (t.vod_platforms or "").split(",") if p.strip()]
                for p in entry["platforms"]:
                    if p not in existing:
                        existing.append(p)
                t.vod_platforms = ", ".join(existing)

            matched += 1

    return matched


def _as_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
