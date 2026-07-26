#!/usr/bin/env python3
"""Scrape the top-level pages of works that the VOD lists reference but we never
scraped.

A harvest bug (premature month break, see scraper.scrape_vod_all_urls) truncated
each month at the first page with no *new* URLs, dropping the long tail — mostly
episodes of ongoing series. As a result ~1,300 works are absent from the catalog
entirely (e.g. True Detective / Temný případ).

We don't need to re-harvest: every one of those URLs is already in the cached VOD
list HTML. This scans those cached lists, reconstructs each work's ROOT overview
URL (the first `/film/{id}-slug/` segment), keeps only roots that are not yet a
top-level row in the DB, and downloads them into the HTML cache. Run `csfd parse`
afterwards to load them and refresh hierarchy fields.

Scraping the roots (not every episode) is enough to make the works appear in the
catalog with their season/episode totals (read from the serial header). Per-
episode release timelines would need the child pages too — a separate, larger job.

Idempotent: URLs already in the cache are skipped, so it is safe to re-run after
an interruption.

Usage:  python3 scripts/backfill_missing_works.py
"""
import glob
import re
import sys

from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text

from csfd_vod.config import load_config_from_env, load_selectors
from csfd_vod.cache import HTMLCache
from csfd_vod.extraction.scraper import VODScraper
from csfd_vod.extraction.rate_limiter import RateLimiter
from csfd_vod.logger import get_logger

logger = get_logger(__name__)

# Matches a title-overview URL; group(1) = first "{id}-slug" segment, group(2) = id.
_OVERVIEW_RE = re.compile(
    r"^https://www\.csfd\.cz/film/((\d+)[^/]*)/(?:\d+[^/]*/)?prehled/$"
)


def _norm(href: str) -> str:
    return href if href.startswith("http") else "https://www.csfd.cz" + href


def _derive_root_urls(list_html_dir: str) -> dict:
    """root_id -> reconstructed root overview URL, from the cached VOD lists."""
    root_url = {}
    for path in glob.glob(f"{list_html_dir}/*.html"):
        with open(path, encoding="utf-8") as fh:
            soup = BeautifulSoup(fh.read(), "html.parser")
        for a in soup.select("a[href*='/film/']"):
            m = _OVERVIEW_RE.match(_norm(a.get("href", "")))
            if not m:
                continue
            first_seg, root_id = m.group(1), int(m.group(2))
            root_url.setdefault(
                root_id, f"https://www.csfd.cz/film/{first_seg}/prehled/"
            )
    return root_url


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

    root_url = _derive_root_urls(f"{config.cache_dir}/vod_lists")

    engine = create_engine(config.database.connection_string)
    with engine.connect() as conn:
        db_roots = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT csfd_id FROM csfd_vod.fact_titles WHERE root_id = csfd_id"
                )
            )
        }

    targets = sorted(
        {url for rid, url in root_url.items() if rid not in db_roots}
    )
    logger.info(
        "missing_works_found",
        roots_in_lists=len(root_url),
        already_in_db=len(root_url) - len(targets),
        to_scrape=len(targets),
    )

    saved = skipped = failed = 0
    for i, url in enumerate(targets):
        if cache.has(url):
            skipped += 1
            continue
        if i % 25 == 0:
            logger.info("scrape_progress", done=i, total=len(targets), saved=saved)
        try:
            html = scraper.scrape_title_details(url)
            if html:
                cache.save(url, html)
                saved += 1
            else:
                failed += 1
                logger.warning("scrape_returned_empty", url=url)
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.warning("scrape_failed", url=url, error=str(e))

    logger.info(
        "backfill_complete",
        total=len(targets),
        saved=saved,
        skipped=skipped,
        failed=failed,
    )
    print(f"targets={len(targets)} saved={saved} skipped={skipped} failed={failed}")
    print("Next: run `csfd parse` to load them and refresh hierarchy fields.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
