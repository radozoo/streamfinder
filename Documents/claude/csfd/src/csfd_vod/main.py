"""Main pipeline orchestration."""

import uuid
from typing import Optional
import argparse

from csfd_vod.config import load_config_from_env, load_selectors
from csfd_vod.logger import setup_logging, get_logger
from csfd_vod.extraction.scraper import VODScraper
from csfd_vod.extraction.rate_limiter import RateLimiter
from csfd_vod.transformation.parser import VODTitleParser
from csfd_vod.loading.postgres_loader import PostgresLoader


logger = get_logger(__name__)


def run_pipeline(vod_page_url: Optional[str] = None, dry_run: bool = False) -> dict:
    """
    Execute the full VOD scraping pipeline.

    Args:
        vod_page_url: URL of the VOD page to scrape
        dry_run: If True, scrape and parse but don't load to database

    Returns:
        Pipeline execution summary
    """
    run_id = str(uuid.uuid4())
    logger.info("pipeline_start", run_id=run_id, dry_run=dry_run)

    try:
        # Load configuration
        config = load_config_from_env()
        selectors = load_selectors(config.selectors_path)

        # Use URL from selectors config if not provided
        if vod_page_url is None:
            vod_page_url = selectors.get("vod_page", {}).get("url", "https://www.csfd.cz/vod/")

        # Initialize components
        rate_limiter = RateLimiter(
            delay_ms=config.scrape.rate_limit_delay_ms,
            jitter_ms=config.scrape.rate_limit_jitter_ms,
        )
        scraper = VODScraper(
            selectors=selectors,
            rate_limiter=rate_limiter,
            user_agents=config.scrape.user_agents,
        )
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

            html_content = scraper.session.get(url).text
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

            loader = PostgresLoader(config.database.connection_string)

            try:
                # Create schema first (idempotent)
                loader.create_schema()

                # Load titles
                load_stats = loader.load_titles(parsed_titles, run_id=run_id)
                loader.close()

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


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="CSFD VOD Scraping Pipeline")
    parser.add_argument(
        "--url",
        default=None,
        help="URL of VOD page to scrape (default: from config/selectors.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and parse but don't load to database",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()

    setup_logging(args.log_level)
    result = run_pipeline(vod_page_url=args.url, dry_run=args.dry_run)

    if result["success"]:
        logger.info("pipeline_success", result=result)
    else:
        logger.error("pipeline_failure", result=result)


if __name__ == "__main__":
    main()
