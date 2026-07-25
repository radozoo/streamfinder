#!/usr/bin/env python3
"""Scrape the top-level serial pages we only know via their episodes.

ČSFD /vod lists ongoing series episode-by-episode, so for many active shows we
harvested the episodes but never the serial's own page. That leaves the Katalóg
(top-level works) incomplete and the Kalendár's "jump to series" without a target.

This finds every root_id referenced by a child (episode/season) that has no
top-level row, reconstructs the serial URL from the child's first URL segment,
downloads it into the HTML cache, and stops. Run `csfd parse` afterwards to load
the new pages and refresh hierarchy fields across the board.

Idempotent: pages already in the cache are skipped.

Usage:  python scripts/backfill_missing_roots.py
"""
import sys

from sqlalchemy import create_engine, text

from csfd_vod.config import load_config_from_env, load_selectors
from csfd_vod.cache import HTMLCache
from csfd_vod.extraction.scraper import VODScraper
from csfd_vod.extraction.rate_limiter import RateLimiter
from csfd_vod.logger import get_logger

logger = get_logger(__name__)

MISSING_ROOTS_SQL = text("""
    SELECT DISTINCT ON (child.root_id)
        child.root_id,
        'https://www.csfd.cz/film/'
            || split_part(split_part(child.url_id, '/film/', 2), '/', 1)
            || '/prehled/' AS root_url
    FROM csfd_vod.fact_titles child
    WHERE child.root_id <> child.csfd_id
      AND NOT EXISTS (
          SELECT 1 FROM csfd_vod.fact_titles top
          WHERE top.csfd_id = child.root_id
            AND top.root_id = top.csfd_id
      )
    ORDER BY child.root_id
""")


def main() -> int:
    config = load_config_from_env()
    selectors = load_selectors(config.selectors_path)
    cache = HTMLCache(config.cache_dir)
    scraper = VODScraper(
        selectors=selectors,
        rate_limiter=RateLimiter(
            delay_ms=config.scrape.rate_limit_delay_ms,
            jitter_ms=config.scrape.rate_limit_jitter_ms,
        ),
        user_agents=config.scrape.user_agents,
    )

    engine = create_engine(config.database.connection_string)
    with engine.connect() as conn:
        roots = [(r.root_id, r.root_url) for r in conn.execute(MISSING_ROOTS_SQL)]

    logger.info("missing_roots_found", count=len(roots))
    saved = skipped = failed = 0
    for i, (root_id, url) in enumerate(roots):
        if cache.has(url):
            skipped += 1
            continue
        if i % 10 == 0:
            logger.info("scrape_progress", done=i, total=len(roots), saved=saved)
        try:
            html = scraper.scrape_title_details(url)
            if html:
                cache.save(url, html)
                saved += 1
            else:
                failed += 1
                logger.warning("scrape_returned_empty", root_id=root_id, url=url)
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.warning("scrape_failed", root_id=root_id, url=url, error=str(e))

    logger.info("backfill_complete", total=len(roots), saved=saved, skipped=skipped, failed=failed)
    print(f"roots={len(roots)} saved={saved} skipped={skipped} failed={failed}")
    print("Next: run `csfd parse` to load them and refresh hierarchy fields.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
