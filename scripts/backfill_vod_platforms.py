#!/usr/bin/env python3
"""Backfill VOD platforms from the /vod list pages.

Serial and episode detail pages usually have no "where to watch" box, so ~1700
titles that appear on /vod ended up with no platform. The /vod listing itself
states the platform per entry ("/vod/netflix/"), which the list parser now
extracts — this script applies it to existing rows that are still missing one.

The parser + cmd_parse do this on every run now; this only bootstraps the DB.

Usage:  python scripts/backfill_vod_platforms.py
"""
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from csfd_vod.config import load_config_from_env
from csfd_vod.transformation.list_parser import VODListParser
from csfd_vod.logger import get_logger

logger = get_logger(__name__)


def build_url_platforms(cache_dir: str) -> dict[str, list[str]]:
    parser = VODListParser()
    url2plat: dict[str, list[str]] = {}
    for f in sorted(Path(cache_dir, "vod_lists").glob("*.html")):
        for entry in parser.parse(f.read_text(encoding="utf-8"), source=f.name):
            url = entry.get("film_url")
            plats = entry.get("platforms") or []
            if url and plats:
                bucket = url2plat.setdefault(url, [])
                for p in plats:
                    if p not in bucket:
                        bucket.append(p)
    return url2plat


def main() -> int:
    config = load_config_from_env()
    url2plat = build_url_platforms(config.cache_dir)
    logger.info("list_platforms_indexed", urls=len(url2plat))

    engine = create_engine(config.database.connection_string)
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT f.title_id, f.url_id FROM csfd_vod.fact_titles f
            WHERE f.vod_date IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM csfd_vod.dim_vods v
                  WHERE v.title_id = f.title_id AND v.vod_platform <> 'VOD'
              )
        """)).fetchall()

        filled = rows_inserted = 0
        for title_id, url in rows:
            plats = url2plat.get(url)
            if not plats:
                continue
            for p in plats:
                conn.execute(text("""
                    INSERT INTO csfd_vod.dim_vods (title_id, vod_platform, vod_url)
                    VALUES (:id, :p, NULL)
                    ON CONFLICT (title_id, vod_platform) DO NOTHING
                """), {"id": title_id, "p": p})
                rows_inserted += 1
            filled += 1

    logger.info("backfill_platforms_complete", candidates=len(rows), filled=filled, rows_inserted=rows_inserted)
    print(f"candidates={len(rows)} filled={filled} rows_inserted={rows_inserted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
