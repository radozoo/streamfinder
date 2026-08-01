#!/usr/bin/env python3
"""Delete cached pages that are not title pages, so `scrape` fetches them again.

The scraper used to return whatever the browser had even when the title element
never appeared — a 404, a bot-check interstitial, a truncated response. The caller
cached that as a success, and because `HTMLCache.has()` only asks whether a file
exists, the URL was never retried. 566 titles were missing from the catalog this
way, silently, for as long as the cache lived.

The scraper no longer caches those (see extraction/scraper.py), but pages already
cached have to be cleared by hand — that is this script.

Detection is deliberately crude and safe: a real ČSFD title page contains
`film-header` and is 150 KB+; every failed one measured was under 10 KB, with
nothing in between. Anything holding `film-header` is left alone regardless of size.

Most of these URLs reach the cache through the backfill scripts rather than
`vod_urls.json`, so a plain `csfd scrape` will NOT pick them up again — it only
iterates the harvested URL list. Their URLs survive in `cache/urls.json`, which
maps every URL to its hash, so --refetch re-downloads exactly what was purged.

Usage:  python3 scripts/purge_failed_cache.py             # report only
        python3 scripts/purge_failed_cache.py --apply     # delete them
        python3 scripts/purge_failed_cache.py --refetch   # re-download whatever is missing
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

MARKER = b"film-header"


def _refetch(cache_root: Path) -> int:
    """Re-download every URL in the index whose html file is gone."""
    from csfd_vod.cache import HTMLCache
    from csfd_vod.config import load_config_from_env, load_selectors
    from csfd_vod.extraction.rate_limiter import RateLimiter
    from csfd_vod.extraction.scraper import VODScraper

    index_path = cache_root / "urls.json"
    if not index_path.exists():
        print(f"FAIL: no cache index at {index_path}", file=sys.stderr)
        return 2

    index = json.loads(index_path.read_text(encoding="utf-8"))
    missing = [
        u for u in index
        if not (cache_root / "html" / f"{hashlib.md5(u.encode()).hexdigest()[:8]}.html").exists()
    ]
    print(f"URLs in index : {len(index):,}\nmissing html  : {len(missing):,}")
    if not missing:
        return 0

    config = load_config_from_env()
    selectors = load_selectors(config.selectors_path)
    scraper = VODScraper(selectors=selectors, rate_limiter=RateLimiter(config.rate_limit_delay))
    cache = HTMLCache(config.cache_dir)

    saved = failed = 0
    for i, url in enumerate(missing, 1):
        html = scraper.scrape_title_details(url)
        if html:
            cache.save(url, html)
            saved += 1
        else:
            failed += 1
        if i % 25 == 0:
            print(f"  {i}/{len(missing)}  saved={saved} failed={failed}")

    print(f"\nsaved={saved} failed={failed} — run `csfd parse` to load them")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", type=Path, default=Path("cache/html"))
    ap.add_argument("--apply", action="store_true", help="actually delete (default: report only)")
    ap.add_argument("--refetch", action="store_true",
                    help="re-download every indexed URL whose html file is missing")
    args = ap.parse_args()

    if args.refetch:
        return _refetch(args.cache_dir.parent)

    if not args.cache_dir.is_dir():
        print(f"FAIL: no cache directory at {args.cache_dir}", file=sys.stderr)
        return 2

    files = sorted(args.cache_dir.glob("*.html"))
    bad = [p for p in files if MARKER not in p.read_bytes()]

    print(f"cached pages : {len(files):,}")
    print(f"not a title page: {len(bad):,}")
    if bad:
        sizes = sorted(p.stat().st_size for p in bad)
        print(f"  size range   : {sizes[0]:,} B – {sizes[-1]:,} B")
        print(f"  e.g. {', '.join(p.name for p in bad[:5])}")

    if not bad:
        print("\nnothing to purge")
        return 0

    if not args.apply:
        print("\nDRY RUN — pass --apply to delete, then re-run `csfd scrape`")
        return 0

    for p in bad:
        p.unlink()
    print(f"\ndeleted {len(bad):,} — run `python3 -m csfd_vod.main scrape` to refetch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
