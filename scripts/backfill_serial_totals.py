#!/usr/bin/env python3
"""Backfill season_total / episode_total for serials from cached HTML.

The serial page header states the authoritative totals ("Série (2) Epizody (18)").
Most serials were listed on /vod as a whole, so their child-derived counts are empty;
this fills the totals used for the Katalóg card shape without a full re-parse.

The parser now extracts these on every run — this script only bootstraps existing rows.

Usage:  python scripts/backfill_serial_totals.py
"""
import re
import sys

from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text

from csfd_vod.config import load_config_from_env
from csfd_vod.cache import HTMLCache
from csfd_vod.logger import get_logger

logger = get_logger(__name__)

_SERIE_RE = re.compile(r"Série\s*\((\d+)\)")
_EPIZODY_RE = re.compile(r"Epizody\s*\((\d+)\)")


def extract_totals(html: str) -> tuple[int | None, int | None]:
    soup = BeautifulSoup(html, "html.parser")
    for h in soup.select("h3"):
        ht = h.get_text(" ", strip=True)
        if "Epizody" in ht or "Série" in ht:
            ms = _SERIE_RE.search(ht)
            me = _EPIZODY_RE.search(ht)
            if ms or me:
                return (int(ms.group(1)) if ms else None, int(me.group(1)) if me else None)
    return (None, None)


def main() -> int:
    config = load_config_from_env()
    cache = HTMLCache(config.cache_dir)
    engine = create_engine(config.database.connection_string)

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT title_id, url_id FROM csfd_vod.fact_titles
            WHERE title_type IN ('seriál', 'pořad', 'tv seriál')
              AND root_id = csfd_id
        """)).fetchall()

    logger.info("serials_to_scan", count=len(rows))
    updated = missing = 0
    with engine.begin() as conn:
        for i, (title_id, url) in enumerate(rows):
            html = cache.get(url)
            if not html:
                missing += 1
                continue
            season_total, episode_total = extract_totals(html)
            if season_total is None and episode_total is None:
                continue
            conn.execute(
                text("UPDATE csfd_vod.fact_titles SET season_total = :s, episode_total = :e WHERE title_id = :id"),
                {"s": season_total, "e": episode_total, "id": title_id},
            )
            updated += 1
            if i % 500 == 0:
                logger.info("progress", done=i, total=len(rows), updated=updated)

    logger.info("backfill_totals_complete", scanned=len(rows), updated=updated, cache_miss=missing)
    print(f"scanned={len(rows)} updated={updated} cache_miss={missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
