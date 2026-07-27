"""Main pipeline orchestration."""

import json
import re
import uuid
import argparse
from pathlib import Path
from typing import Optional

from csfd_vod.config import load_config_from_env, load_selectors
from csfd_vod.logger import setup_logging, get_logger
from csfd_vod.extraction.scraper import VODScraper
from csfd_vod.extraction.rate_limiter import RateLimiter
from csfd_vod.transformation.parser import VODTitleParser
from csfd_vod.transformation.list_parser import VODListParser
from csfd_vod.loading.postgres_loader import PostgresLoader
from csfd_vod.cache import HTMLCache
from csfd_vod.export.exporter import DataExporter
from csfd_vod.export.dashboard_generator import DashboardGenerator
from csfd_vod.export.streamfinder_exporter import StreamfinderExporter
from csfd_vod.enrichment import TMDBEnricher


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
# Command: harvest — collect all VOD title URLs via monthly iteration
# ---------------------------------------------------------------------------

def cmd_harvest(args) -> dict:
    """Iterate all months from --from-year to today, collect unique VOD title URLs."""
    run_id = str(uuid.uuid4())
    logger.info("cmd_harvest_start", run_id=run_id, from_year=args.from_year)

    config = load_config_from_env()
    selectors = load_selectors(config.selectors_path)
    scraper = _make_scraper(config, selectors)

    list_html_dir = Path(config.cache_dir) / "vod_lists"
    urls = scraper.scrape_vod_all_urls(from_year=args.from_year, list_html_dir=list_html_dir)

    vod_urls_path = Path(config.cache_dir) / "vod_urls.json"
    vod_urls_path.parent.mkdir(parents=True, exist_ok=True)
    vod_urls_path.write_text(json.dumps(urls, indent=2, ensure_ascii=False), encoding="utf-8")

    # Completeness guard: every month must have been harvested to CSFD's own last
    # page. Any shortfall means a month was silently truncated (the class of bug
    # that dropped Twin Peaks) — surface it loudly instead of shipping a gap.
    incomplete = getattr(scraper, "incomplete_months", [])
    complete = not incomplete
    if not complete:
        logger.error("cmd_harvest_incomplete", run_id=run_id, incomplete_months=incomplete)

    logger.info(
        "cmd_harvest_complete",
        run_id=run_id, count=len(urls), path=str(vod_urls_path),
        complete=complete, incomplete_months=len(incomplete),
    )
    return {
        "success": True,
        "run_id": run_id,
        "count": len(urls),
        "path": str(vod_urls_path),
        "complete": complete,
        "incomplete_months": incomplete,
    }


# ---------------------------------------------------------------------------
# Command: harvest-platforms — recover undated catalog titles per VOD platform
# ---------------------------------------------------------------------------

def cmd_harvest_platforms(args) -> dict:
    """Harvest each platform's /vod/{slug}/ browse listing.

    The monthly harvest (cmd_harvest) only sees titles with a DATED VOD arrival.
    Older catalog titles that are streamable but never got a dated event (e.g.
    Dexter, Game of Thrones) are invisible to it. This complementary source lists
    everything CURRENTLY on a platform, dated or not, using the same real (clamped,
    non-phantom) pagination as the monthly listing — verified empirically.

    Unions newly found URLs into the master vod_urls.json (never removes existing
    entries) so a later `scrape`/`parse` picks them up. Run `parse` + `streamfinder`
    + scripts/check_completeness.py afterwards, same as after any harvest.
    """
    run_id = str(uuid.uuid4())
    platforms = args.platforms.split(",") if args.platforms else VODScraper.MAJOR_VOD_PLATFORMS
    logger.info("cmd_harvest_platforms_start", run_id=run_id, platforms=platforms)

    config = load_config_from_env()
    selectors = load_selectors(config.selectors_path)
    scraper = _make_scraper(config, selectors)
    list_html_dir = Path(config.cache_dir) / "vod_lists"

    per_platform = {}
    all_urls: set = set()
    for slug in platforms:
        urls = scraper.scrape_vod_platform_all_urls(slug, list_html_dir=list_html_dir)
        per_platform[slug] = len(urls)
        all_urls.update(urls)
        logger.info("cmd_harvest_platforms_progress", run_id=run_id, platform=slug, count=len(urls))

    incomplete = getattr(scraper, "incomplete_platforms", [])
    complete = not incomplete
    if not complete:
        logger.error("cmd_harvest_platforms_incomplete", run_id=run_id, incomplete_platforms=incomplete)

    vod_urls_path = Path(config.cache_dir) / "vod_urls.json"
    existing = json.loads(vod_urls_path.read_text(encoding="utf-8")) if vod_urls_path.exists() else []
    new_urls = sorted(all_urls - set(existing))
    merged = sorted(set(existing) | all_urls)
    vod_urls_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info(
        "cmd_harvest_platforms_complete",
        run_id=run_id, per_platform=per_platform, new_urls=len(new_urls),
        master_total=len(merged), complete=complete,
    )
    return {
        "success": True,
        "run_id": run_id,
        "per_platform": per_platform,
        "new_urls": len(new_urls),
        "master_total": len(merged),
        "complete": complete,
        "incomplete_platforms": incomplete,
    }


# ---------------------------------------------------------------------------
# Command: scrape — download HTML to cache
# ---------------------------------------------------------------------------

def cmd_scrape(args) -> dict:
    """Stage 1 + Stage 2 (download only): fetch all title pages and save HTML to cache."""
    run_id = str(uuid.uuid4())
    logger.info("cmd_scrape_start", run_id=run_id)

    config = load_config_from_env()
    selectors = load_selectors(config.selectors_path)

    scraper = _make_scraper(config, selectors)
    cache = HTMLCache(config.cache_dir)

    # Stage 1: get URL list — prefer harvested list, fall back to live scrape
    vod_urls_path = Path(config.cache_dir) / "vod_urls.json"
    if vod_urls_path.exists():
        title_urls = json.loads(vod_urls_path.read_text(encoding="utf-8"))
        logger.info("stage_scrape_start", run_id=run_id, url_source="vod_urls_json", count=len(title_urls))
    else:
        vod_page_url = args.url or selectors.get("vod_page", {}).get("url", "https://www.csfd.cz/vod/")
        logger.info("stage_scrape_start", run_id=run_id, url_source="live_scrape")
        title_urls = scraper.scrape_vod_list(vod_page_url)
        logger.info("stage_scrape_complete", run_id=run_id, count=len(title_urls))

    if not title_urls:
        logger.error("stage_scrape_failed", run_id=run_id, reason="no_titles_found")
        return {"success": False, "run_id": run_id, "stage": "scrape"}

    # Stage 2: download HTML → cache. Uncached URLs are prioritised top-level-first
    # (a work's own root page — the catalog-visible unit) over child episodes/seasons,
    # then bounded by --limit so a large backlog (e.g. a catalog sweep's new URLs)
    # can be worked off in resumable batches rather than one huge run. Skipping
    # already-cached URLs makes repeated runs pick up exactly where the last left off.
    _CHILD_RE = re.compile(r'^https://www\.csfd\.cz/film/\d+[^/]*/\d+[^/]*/prehled/$')
    to_fetch = [u for u in title_urls if not cache.has(u)]
    already_cached = len(title_urls) - len(to_fetch)
    to_fetch.sort(key=lambda u: bool(_CHILD_RE.match(u)))  # top-level (False) sorts first
    limit = getattr(args, "limit", None)
    batch = to_fetch[:limit] if limit else to_fetch
    remaining_after = max(0, len(to_fetch) - len(batch))

    saved = 0
    skipped = already_cached

    for i, url in enumerate(batch):
        if i % 10 == 0:
            logger.info("stage_download_progress", run_id=run_id, count=i, total=len(batch))

        html = scraper.scrape_title_details(url)
        if html:
            cache.save(url, html)
            saved += 1
        else:
            logger.warning("download_failed", url=url)

    logger.info(
        "cmd_scrape_complete", run_id=run_id, saved=saved, skipped=skipped,
        total=len(title_urls), remaining_after=remaining_after,
    )
    return {
        "success": True, "run_id": run_id, "saved": saved, "skipped": skipped,
        "total": len(title_urls), "remaining_after": remaining_after,
    }


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

    # Merge list-page metadata (vod_date, distributor, list_type) into parsed titles
    list_html_dir = Path(config.cache_dir) / "vod_lists"
    if list_html_dir.exists():
        list_parser = VODListParser()
        # Build url → title index for fast lookup
        title_by_url = {t.url_id: t for t in parsed_titles}
        list_pages = sorted(list_html_dir.glob("*.html"))
        logger.info("stage_list_parse_start", run_id=run_id, list_pages=len(list_pages))
        matched = 0
        for list_page in list_pages:
            try:
                html = list_page.read_text(encoding="utf-8")
                entries = list_parser.parse(html, source=list_page.name)
                for entry in entries:
                    film_url = entry.get("film_url")
                    if film_url and film_url in title_by_url:
                        t = title_by_url[film_url]
                        if not t.vod_date and entry.get("vod_date"):
                            t.vod_date = entry["vod_date"]
                        if not t.distributor and entry.get("distributor"):
                            t.distributor = entry["distributor"]
                        if not t.title_type and entry.get("list_type"):
                            t.title_type = entry["list_type"]
                        # Merge the platform from the /vod listing (union) — the
                        # authoritative source for serials/episodes with no detail VOD box.
                        if entry.get("platforms"):
                            existing = [p.strip() for p in (t.vod_platforms or "").split(",") if p.strip()]
                            for p in entry["platforms"]:
                                if p not in existing:
                                    existing.append(p)
                            t.vod_platforms = ", ".join(existing)
                        matched += 1
            except Exception as e:
                logger.warning("list_page_parse_error", path=str(list_page), error=str(e))
        logger.info("stage_list_parse_complete", run_id=run_id, matched=matched)

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
# Command: dashboard — export JSON files + generate HTML dashboard
# ---------------------------------------------------------------------------

def cmd_dashboard(args) -> dict:
    """Export pre-aggregated JSON files and generate HTML dashboard."""
    config = load_config_from_env()
    output_dir = Path(args.output_dir)
    data_dir = output_dir / "data"

    logger.info("cmd_dashboard_start", output_dir=str(output_dir))

    try:
        # Step 1: Export JSON files to dashboard/data/
        exporter = DataExporter(config.database.connection_string)
        export_stats = exporter.export(str(data_dir))
        logger.info("dashboard_data_exported", **export_stats)

        # Step 2: Generate HTML dashboard
        generator = DashboardGenerator()
        html_path = output_dir / "index.html"
        gen_stats = generator.generate(str(data_dir), str(html_path))
        logger.info("dashboard_html_generated", **gen_stats)

        return {
            "success": True,
            "output_dir": str(output_dir.absolute()),
            "html_path": str(html_path.absolute()),
            "files_written": export_stats["files_written"],
            "total_titles": export_stats["total_titles"],
        }

    except Exception as e:
        logger.error("cmd_dashboard_failed", error=str(e))
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Command: streamfinder — export JSON files for SvelteKit dashboard
# ---------------------------------------------------------------------------

def cmd_streamfinder(args) -> dict:
    """Export Streamfinder JSON data files (titles_index, per-title detail/, dimensions)."""
    config = load_config_from_env()
    exporter = StreamfinderExporter(config.database.connection_string)
    logger.info("cmd_streamfinder_start", output_dir=args.output_dir)
    return exporter.export(args.output_dir)


# ---------------------------------------------------------------------------
# Command: enrich — TMDB enrichment (poster_path, backdrop_path, trailer)
# ---------------------------------------------------------------------------

def cmd_enrich(args) -> dict:
    """Enrich titles with TMDB metadata (posters, backdrops, trailers)."""
    import os
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        logger.error("cmd_enrich_failed", error="TMDB_API_KEY env var not set")
        return {"success": False, "error": "TMDB_API_KEY not set"}

    config = load_config_from_env()
    enricher = TMDBEnricher(api_key=api_key, connection_string=config.database.connection_string)

    logger.info("cmd_enrich_start", limit=args.limit, force=args.force)
    stats = enricher.enrich(limit=args.limit, force=args.force)
    return {"success": True, **stats}


# ---------------------------------------------------------------------------
# Command: update — incremental refresh (discover + refresh + enrich + export)
# ---------------------------------------------------------------------------

def _months_back(n: int) -> tuple:
    """Return (year, month) n months before the current month."""
    from datetime import date
    today = date.today()
    idx = today.year * 12 + (today.month - 1) - n
    return idx // 12, idx % 12 + 1


def cmd_update(args) -> dict:
    """Incremental catalog refresh — the manually-run 'keep it fresh' command.

    Three streams (see docs/update-architecture.md):
      discover  re-harvest the last N months (forced fresh) → union into
                vod_urls.json → download only the new title pages. Picks up new
                releases and new episodes of running series.
      refresh   re-scrape a budget-capped set of 'hot' titles (young / unrated)
                so their rating and vote count mature. A re-scrape that comes back
                as a bot-protection challenge (parses to no title) is rejected and
                the good cached page is kept — never overwritten with junk.
      parse+load → enrich (missing only) → export the Streamfinder JSON.

    Deliberately does NOT commit or push — a human reviews and does that. Also
    does NOT reconcile delistings yet (that needs a complete harvest and per-month
    URL snapshots; see the design doc). Deploy gate stays scripts/check_completeness.py.
    """
    run_id = str(uuid.uuid4())
    config = load_config_from_env()
    selectors = load_selectors(config.selectors_path)
    scraper = _make_scraper(config, selectors)
    cache = HTMLCache(config.cache_dir)
    summary: dict = {"success": True, "run_id": run_id, "steps": {}}
    logger.info("cmd_update_start", run_id=run_id, discover_months=args.discover_months,
                refresh_budget=args.refresh_budget)

    # ── 1. discover ─────────────────────────────────────────────────────────
    if not args.skip_discover:
        cut_y, cut_m = _months_back(args.discover_months)
        list_html_dir = Path(config.cache_dir) / "vod_lists"
        recent = scraper.scrape_vod_all_urls(
            from_year=cut_y, from_month=cut_m,
            list_html_dir=list_html_dir, refetch_from=(cut_y, cut_m),
        )
        incomplete = getattr(scraper, "incomplete_months", [])
        if incomplete:
            logger.error("update_discover_incomplete", run_id=run_id, incomplete_months=incomplete)

        # Union new URLs into the master list (never shrink it — old months stay).
        vod_urls_path = Path(config.cache_dir) / "vod_urls.json"
        existing = json.loads(vod_urls_path.read_text(encoding="utf-8")) if vod_urls_path.exists() else []
        merged = sorted(set(existing) | set(recent))
        new_urls = sorted(set(recent) - set(existing))
        vod_urls_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

        # Download only pages we don't already have cached.
        downloaded = 0
        for url in recent:
            if cache.has(url):
                continue
            html = scraper.scrape_title_details(url)
            if html:
                cache.save(url, html)
                downloaded += 1
            else:
                logger.warning("update_discover_download_failed", url=url)
        summary["steps"]["discover"] = {
            "recent_urls": len(recent), "new_in_master": len(new_urls),
            "downloaded": downloaded, "complete": not incomplete,
            "incomplete_months": incomplete,
        }
        logger.info("cmd_update_discover_complete", run_id=run_id, **summary["steps"]["discover"])

    # ── 2. refresh ──────────────────────────────────────────────────────────
    if not args.skip_refresh:
        loader = PostgresLoader(config.database.connection_string)
        try:
            hot = loader.select_refresh_urls(args.refresh_max_age_days, args.refresh_budget)
        finally:
            loader.close()
        parser = VODTitleParser(selectors=selectors)
        refreshed, rejected = 0, 0
        for i, url in enumerate(hot):
            if i % 25 == 0:
                logger.info("update_refresh_progress", run_id=run_id, count=i, total=len(hot))
            html = scraper.scrape_title_details(url)
            # Reject a challenge/blocked page: it has no title header, so the parser
            # returns None. Keep the existing good cache rather than overwriting it.
            if html and parser.parse(html, url) is not None:
                cache.save(url, html)
                refreshed += 1
            else:
                rejected += 1
                logger.warning("update_refresh_rejected", url=url)
        summary["steps"]["refresh"] = {"selected": len(hot), "refreshed": refreshed, "rejected": rejected}
        logger.info("cmd_update_refresh_complete", run_id=run_id, **summary["steps"]["refresh"])

    # ── 3. parse + load (whole cache; idempotent, COALESCE-protected) ─────────
    if args.dry_run:
        logger.info("cmd_update_dry_run", run_id=run_id, summary=summary)
        summary["dry_run"] = True
        return summary
    parse_res = cmd_parse(argparse.Namespace(dry_run=False))
    summary["steps"]["parse"] = parse_res
    if not parse_res.get("success"):
        summary["success"] = False
        return summary

    # ── 3b. dedupe (self-heal ČSFD slug drift) ────────────────────────────────
    # ČSFD renames slugs over time (episode-5 → pamet), and since url_id carries
    # the slug the loader inserts a second row for the same csfd_id — a title that
    # would then render twice. Collapse rows sharing a csfd_id (keep the richest)
    # and drop non-overview junk, pruning their cache + vod_urls so a re-parse
    # can't resurrect them. See scripts/dedupe_titles.py / docs csfd-scraping-rules.
    from scripts.dedupe_titles import dedupe as _dedupe_titles
    dloader = PostgresLoader(config.database.connection_string)
    try:
        summary["steps"]["dedupe"] = _dedupe_titles(
            dloader, cache=cache, cache_dir=config.cache_dir, apply=True
        )
    finally:
        dloader.close()
    logger.info("cmd_update_dedupe_complete", run_id=run_id, **summary["steps"]["dedupe"])

    # ── 4. enrich (missing only) ──────────────────────────────────────────────
    if not args.skip_enrich:
        summary["steps"]["enrich"] = cmd_enrich(argparse.Namespace(limit=None, force=False))

    # ── 5. export Streamfinder JSON ───────────────────────────────────────────
    if not args.skip_export:
        summary["steps"]["export"] = cmd_streamfinder(
            argparse.Namespace(output_dir="streamfinder/static/data")
        )

    logger.info("cmd_update_complete", run_id=run_id, summary=summary)
    logger.info("cmd_update_next_step",
                hint="run `python3 scripts/check_completeness.py` as the deploy gate, "
                     "then review + commit + push the regenerated JSON")
    return summary


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

    # -- harvest --
    p_harvest = subparsers.add_parser("harvest", help="Collect all VOD title URLs by iterating months")
    p_harvest.add_argument("--from-year", type=int, default=2015, help="Start year for month iteration (default: 2015)")

    # -- harvest-platforms --
    p_hp = subparsers.add_parser(
        "harvest-platforms",
        help="Collect VOD title URLs from per-platform browse listings (recovers undated catalog titles)")
    p_hp.add_argument("--platforms", default=None,
                       help="Comma-separated platform slugs (default: the 8 major platforms)")

    # -- scrape --
    p_scrape = subparsers.add_parser("scrape", help="Download HTML pages to cache (no parsing)")
    p_scrape.add_argument("--url", default=None, help="Override VOD listing URL")
    p_scrape.add_argument("--limit", type=int, default=None,
                           help="Max NEW (uncached) pages to fetch this run, top-level works "
                                "prioritised over episodes/seasons (default: no limit)")

    # -- parse --
    p_parse = subparsers.add_parser("parse", help="Parse cached HTML and load to database")
    p_parse.add_argument("--dry-run", action="store_true", help="Parse but don't write to database")

    # -- run --
    p_run = subparsers.add_parser("run", help="Full pipeline without cache (scrape + parse + load)")
    p_run.add_argument("--url", default=None, help="Override VOD listing URL")
    p_run.add_argument("--dry-run", action="store_true", help="Scrape and parse but don't load to database")

    # -- dashboard --
    p_dashboard = subparsers.add_parser("dashboard", help="Export JSON data files + generate HTML dashboard")
    p_dashboard.add_argument(
        "--output-dir", default="dashboard", help="Output directory (default: dashboard/)"
    )

    # -- streamfinder --
    p_sf = subparsers.add_parser("streamfinder", help="Export JSON files for Streamfinder SvelteKit app")
    p_sf.add_argument("--output-dir", default="streamfinder/static/data", help="Output directory for JSON files")

    # -- enrich --
    p_enrich = subparsers.add_parser("enrich", help="Enrich titles with TMDB metadata (requires TMDB_API_KEY)")
    p_enrich.add_argument("--limit", type=int, default=None, help="Max titles to process (default: all pending)")
    p_enrich.add_argument("--force", action="store_true", help="Re-enrich already enriched titles")

    # -- update --
    p_update = subparsers.add_parser(
        "update", help="Incremental refresh: discover new + refresh hot titles + enrich + export")
    p_update.add_argument("--discover-months", type=int, default=2,
                          help="How many recent months to re-harvest for new releases (default: 2)")
    p_update.add_argument("--refresh-budget", type=int, default=200,
                          help="Max title pages to re-scrape for maturing ratings (default: 200)")
    p_update.add_argument("--refresh-max-age-days", type=int, default=180,
                          help="A title is 'hot' if on VOD within this many days, or still unrated (default: 180)")
    p_update.add_argument("--skip-discover", action="store_true", help="Skip the discover step")
    p_update.add_argument("--skip-refresh", action="store_true", help="Skip the refresh step")
    p_update.add_argument("--skip-enrich", action="store_true", help="Skip TMDB enrichment")
    p_update.add_argument("--skip-export", action="store_true", help="Skip the Streamfinder JSON export")
    p_update.add_argument("--dry-run", action="store_true",
                          help="Discover + refresh into cache, but don't parse/load/enrich/export")

    args = parser.parse_args()
    setup_logging(args.log_level)

    if args.command == "harvest":
        result = cmd_harvest(args)
    elif args.command == "harvest-platforms":
        result = cmd_harvest_platforms(args)
    elif args.command == "scrape":
        result = cmd_scrape(args)
    elif args.command == "parse":
        result = cmd_parse(args)
    elif args.command == "run":
        result = run_pipeline(vod_page_url=args.url, dry_run=args.dry_run)
    elif args.command == "dashboard":
        result = cmd_dashboard(args)
    elif args.command == "streamfinder":
        result = cmd_streamfinder(args)
    elif args.command == "enrich":
        result = cmd_enrich(args)
    elif args.command == "update":
        result = cmd_update(args)

    if result.get("success"):
        logger.info("command_success", command=args.command, result=result)
    else:
        logger.error("command_failure", command=args.command, result=result)


if __name__ == "__main__":
    main()
