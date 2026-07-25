#!/usr/bin/env python3
"""Force-rescrape a hand-picked list of title pages whose DB rows are broken.

title_ids 6–15 were parsed by a very early parser version and ended up with
garbage titles ("Prehled", "1666380 Serie 2") and stray English genres. Their
HTML is no longer in the cache, so a normal re-parse can't fix them. This
downloads their pages fresh (overwriting any stale cache) so `csfd parse` can
re-derive title, genres and hierarchy correctly.

Usage:  python3 scripts/rescrape_broken_roots.py
"""
import sys

from csfd_vod.config import load_config_from_env, load_selectors
from csfd_vod.cache import HTMLCache
from csfd_vod.extraction.scraper import VODScraper
from csfd_vod.extraction.rate_limiter import RateLimiter
from csfd_vod.logger import get_logger

logger = get_logger(__name__)

URLS = [
    "https://www.csfd.cz/film/1667978-star-wars-maul-pan-stinu/prehled/",
    "https://www.csfd.cz/film/1564759-harry-hole/prehled/",
    "https://www.csfd.cz/film/1214949-daredevil-znovuzrozeni/1666380-serie-2/prehled/",
    "https://www.csfd.cz/film/930640-neporazitelny/prehled/",
    "https://www.csfd.cz/film/1361414-cmuchalove/prehled/",
    "https://www.csfd.cz/film/657621-banda/1303033-serie-4/prehled/",
    "https://www.csfd.cz/film/1544321-stane-se-neco-hrozne-spatneho/prehled/",
    "https://www.csfd.cz/film/657621-banda/922866-serie-3/prehled/",
    "https://www.csfd.cz/film/1166910-terapie-pravdou/prehled/",
    "https://www.csfd.cz/film/657621-banda/751271-serie-2/prehled/",
]


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

    saved = failed = 0
    for url in URLS:
        try:
            html = scraper.scrape_title_details(url)
            if html:
                cache.save(url, html)  # overwrite any stale entry
                saved += 1
                logger.info("rescraped", url=url, bytes=len(html))
            else:
                failed += 1
                logger.warning("scrape_returned_empty", url=url)
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.warning("scrape_failed", url=url, error=str(e))

    print(f"total={len(URLS)} saved={saved} failed={failed}")
    print("Next: run `csfd parse` to reload these pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
