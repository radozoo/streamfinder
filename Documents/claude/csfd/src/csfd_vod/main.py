"""Main pipeline orchestration."""

import uuid
import argparse
from typing import Optional

from csfd_vod.config import load_config_from_env, load_selectors
from csfd_vod.logger import setup_logging, get_logger
from csfd_vod.extraction.scraper import VODScraper
from csfd_vod.extraction.rate_limiter import RateLimiter
from csfd_vod.transformation.parser import VODTitleParser
from csfd_vod.loading.postgres_loader import PostgresLoader
from csfd_vod.cache import HTMLCache


logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Stage helpers
# ---------------------------------------------------------------------------

def _make_scraper(config, selectors) -> VODScraper:
    rate_limiter = RateLimiter(
        delay_ms=config.scrape.rate_limit_delay_ms,
        jitter_ms=config.scrape.rate_limit_jitter_ms,
    )
    return VODScraper(
        selectors=selectors,
        rate_limiter=rate_limiter,
        user_agents=config.scrape.user_agents,
    )


def _load_to_db(parsed_titles, config, run_id):
    loader = PostgresLoader(config.database.connection_string)
    try:
        loader.create_schema()
        stats = loader.load_titles(parsed_titles, run_id=run_id)
        loader.close()
        return stats
    except Exception as e:
        loader.close()
        raise


# ---------------------------------------------------------------------------
# Command: scrape — download HTML to cache
# ---------------------------------------------------------------------------

def cmd_scrape(args) -> dict:
    """Stage 1 + Stage 2 (download only): fetch all title pages and save HTML to cache."""
    run_id = str(uuid.uuid4())
    logger.info("cmd_scrape_start", run_id=run_id)

    config = load_config_from_env()
    selectors = load_selectors(config.selectors_path)

    vod_page_url = args.url or selectors.get("vod_page", {}).get("url", "https://www.csfd.cz/vod/")

    scraper = _make_scraper(config, selectors)
    cache = HTMLCache(config.cache_dir)

    # Stage 1: get URL list
    logger.info("stage_scrape_start", run_id=run_id)
    title_urls = scraper.scrape_vod_list(vod_page_url)
    logger.info("stage_scrape_complete", run_id=run_id, count=len(title_urls))

    if not title_urls:
        logger.error("stage_scrape_failed", run_id=run_id, reason="no_titles_found")
        return {"success": False, "run_id": run_id, "stage": "scrape"}

    # Stage 2: download HTML → cache
    saved = 0
    skipped = 0

    for i, url in enumerate(title_urls):
        if i % 10 == 0:
            logger.info("stage_download_progress", run_id=run_id, count=i, total=len(title_urls))

        if cache.has(url):
            logger.info("cache_hit", url=url)
            skipped += 1
            continue

        html = scraper.scrape_title_details(url)
        if html:
            cache.save(url, html)
            saved += 1
        else:
            logger.warning("download_failed", url=url)

    logger.info("cmd_scrape_complete", run_id=run_id, saved=saved, skipped=skipped, total=len(title_urls))
    return {"success": True, "run_id": run_id, "saved": saved, "skipped": skipped, "total": len(title_urls)}


# ---------------------------------------------------------------------------
# Command: parse — parse cached HTML and load to DB
# ---------------------------------------------------------------------------

def cmd_parse(args) -> dict:
    """Stage 2 (from cache) + Stage 3: parse cached HTML and load to DB."""
    run_id = str(uuid.uuid4())
    logger.info("cmd_parse_start", run_id=run_id, dry_run=args.dry_run)

    config = load_config_from_env()
    selectors = load_selectors(config.selectors_path)

    cache = HTMLCache(config.cache_dir)
    parser = VODTitleParser(selectors=selectors)

    urls = cache.all_urls()
    if not urls:
        logger.error("cmd_parse_failed", run_id=run_id, reason="cache_empty")
        return {"success": False, "run_id": run_id, "reason": "cache_empty — run `csfd scrape` first"}

    logger.info("stage_parse_start", run_id=run_id, count=len(urls))
    parsed_titles = []

    for i, url in enumerate(urls):
        if i % 10 == 0:
            logger.info("stage_parse_progress", run_id=run_id, count=i, total=len(urls))

        html = cache.get(url)
        if not html:
            logger.warning("cache_read_failed", url=url)
            continue

        title = parser.parse(html, url)
        if title:
            parsed_titles.append(title)

    logger.info("stage_parse_complete", run_id=run_id, parsed=len(parsed_titles), failed=len(urls) - len(parsed_titles))

    if not parsed_titles:
        logger.error("cmd_parse_failed", run_id=run_id, reason="no_titles_parsed")
        return {"success": False, "run_id": run_id, "stage": "parse"}

    if args.dry_run:
        logger.info("dry_run_complete", run_id=run_id, parsed=len(parsed_titles))
        return {"success": True, "run_id": run_id, "stage": "dry_run", "parse_count": len(parsed_titles)}

    # Stage 3: load to DB
    logger.info("stage_load_start", run_id=run_id, count=len(parsed_titles))
    try:
        stats = _load_to_db(parsed_titles, config, run_id)
        logger.info("stage_load_complete", run_id=run_id, stats=stats)
        return {"success": True, "run_id": run_id, "stage": "complete", "parse_count": len(parsed_titles), "load_stats": stats}
    except Exception as e:
        logger.error("stage_load_failed", run_id=run_id, error=str(e))
        return {"success": False, "run_id": run_id, "stage": "load", "error": str(e)}


# ---------------------------------------------------------------------------
# Command: run — full pipeline without cache (production use)
# ---------------------------------------------------------------------------

def run_pipeline(vod_page_url: Optional[str] = None, dry_run: bool = False) -> dict:
    """Execute the full VOD scraping pipeline (scrape → parse → load) without cache."""
    run_id = str(uuid.uuid4())
    logger.info("pipeline_start", run_id=run_id, dry_run=dry_run)

    try:
        config = load_config_from_env()
        selectors = load_selectors(config.selectors_path)

        if vod_page_url is None:
            vod_page_url = selectors.get("vod_page", {}).get("url", "https://www.csfd.cz/vod/")

        scraper = _make_scraper(config, selectors)
        parser = VODTitleParser(selectors=selectors)

        # Stage 1: Scrape
        logger.info("stage_scrape_start", run_id=run_id)
        title_urls = scraper.scrape_vod_list(vod_page_url)
        logger.info("stage_scrape_complete", run_id=run_id, count=len(title_urls))

        if not title_urls:
            logger.error("stage_scrape_failed", run_id=run_id, reason="no_titles_found")
            return {"success": False, "run_id": run_id, "stage": "scrape"}

        # Stage 2: Parse
        logger.info("stage_parse_start", run_id=run_id, count=len(title_urls))
        parsed_titles = []

        for i, url in enumerate(title_urls):
            if i % 100 == 0:
                logger.info("stage_parse_progress", run_id=run_id, count=i, total=len(title_urls))

            html_content = scraper.scrape_title_details(url)
            if html_content:
                title = parser.parse(html_content, url)
                if title:
                    parsed_titles.append(title)

        logger.info("stage_parse_complete", run_id=run_id, parsed=len(parsed_titles), failed=len(title_urls) - len(parsed_titles))

        if not parsed_titles:
            logger.error("stage_parse_failed", run_id=run_id, reason="no_titles_parsed")
            return {"success": False, "run_id": run_id, "stage": "parse"}

        # Stage 3: Load
        if not dry_run:
            logger.info("stage_load_start", run_id=run_id, count=len(parsed_titles))
            try:
                load_stats = _load_to_db(parsed_titles, config, run_id)
                logger.info("stage_load_complete", run_id=run_id, stats=load_stats)
                return {
                    "success": True,
                    "run_id": run_id,
                    "stage": "complete",
                    "scrape_count": len(title_urls),
                    "parse_count": len(parsed_titles),
                    "load_stats": load_stats,
                }
            except Exception as e:
                logger.error("stage_load_failed", run_id=run_id, error=str(e))
                return {"success": False, "run_id": run_id, "stage": "load", "error": str(e)}
        else:
            logger.info("dry_run_complete", run_id=run_id, parsed=len(parsed_titles))
            return {
                "success": True,
                "run_id": run_id,
                "stage": "dry_run",
                "scrape_count": len(title_urls),
                "parse_count": len(parsed_titles),
                "dry_run": True,
            }

    except Exception as e:
        logger.error("pipeline_failed", run_id=run_id, error=str(e))
        return {"success": False, "run_id": run_id, "error": str(e)}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """CLI entry point with subcommands: scrape, parse, run."""
    parser = argparse.ArgumentParser(description="CSFD VOD Scraping Pipeline")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- scrape --
    p_scrape = subparsers.add_parser("scrape", help="Download HTML pages to cache (no parsing)")
    p_scrape.add_argument("--url", default=None, help="Override VOD listing URL")

    # -- parse --
    p_parse = subparsers.add_parser("parse", help="Parse cached HTML and load to database")
    p_parse.add_argument("--dry-run", action="store_true", help="Parse but don't write to database")

    # -- run --
    p_run = subparsers.add_parser("run", help="Full pipeline without cache (scrape + parse + load)")
    p_run.add_argument("--url", default=None, help="Override VOD listing URL")
    p_run.add_argument("--dry-run", action="store_true", help="Scrape and parse but don't load to database")

    args = parser.parse_args()
    setup_logging(args.log_level)

    if args.command == "scrape":
        result = cmd_scrape(args)
    elif args.command == "parse":
        result = cmd_parse(args)
    elif args.command == "run":
        result = run_pipeline(vod_page_url=args.url, dry_run=args.dry_run)

    if result.get("success"):
        logger.info("command_success", command=args.command, result=result)
    else:
        logger.error("command_failure", command=args.command, result=result)


if __name__ == "__main__":
    main()
