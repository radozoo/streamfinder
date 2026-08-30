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

Report mode doubles as a pre-deploy gate (it runs from check_all.py) and fails on
either half of the problem: pages cached that are not title pages, and indexed URLs
whose page is gone — the state left behind by --apply until --refetch has run.

Usage:  python3 scripts/purge_failed_cache.py             # report / gate
        python3 scripts/purge_failed_cache.py --apply     # delete them
        python3 scripts/purge_failed_cache.py --refetch   # re-download whatever is missing
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

MARKER = b"film-header"

# The same interstitial, in the OTHER cache. A poisoned listing page is worse than a
# poisoned title page: the title page merely fails to parse, but a listing that reads
# as "zero entries" strips vod_date, distributor and platform from every title it
# carried — and for a serial episode the listing is the only source of those.
#
# Matched on the challenge markers rather than on size, deliberately. A month's last
# page is legitimately tiny (39 bytes, no articles) and is how the harvest recognises
# the end of a month; deleting those would have it refetch the same emptiness forever.
CHALLENGE_MARKERS = (b"not a bot", b"within.website")


def _challenge_pages(list_dir: Path) -> list[Path]:
    if not list_dir.is_dir():
        return []
    out = []
    for p in sorted(list_dir.glob("*.html")):
        head = p.read_bytes()[:4096].lower()
        if any(m in head for m in CHALLENGE_MARKERS):
            out.append(p)
    return out

# A real title page is 150 KB+; every silent failure measured was under 10 KB, with
# nothing between. Reading only the small ones keeps the gate to a few hundred files
# instead of ~7 GB, and the margin is wide enough that the shape would have to change
# completely before a genuine page slipped through unread.
SUSPECT_MAX_BYTES = 50_000


def _cached_path(cache_root: Path, url: str) -> Path:
    return cache_root / "html" / f"{hashlib.md5(url.encode()).hexdigest()[:8]}.html"


def _missing_from_index(cache_root: Path) -> list[str]:
    """URLs the cache index knows about whose html file is not on disk."""
    index_path = cache_root / "urls.json"
    if not index_path.exists():
        return []
    index = json.loads(index_path.read_text(encoding="utf-8"))
    return [u for u in index if not _cached_path(cache_root, u).exists()]


def _refetch(cache_root: Path) -> int:
    """Re-download every URL in the index whose html file is gone."""
    from csfd_vod.cache import HTMLCache
    from csfd_vod.config import load_config_from_env, load_selectors
    from csfd_vod.extraction.rate_limiter import RateLimiter
    from csfd_vod.extraction.scraper import VODScraper

    if not (cache_root / "urls.json").exists():
        print(f"FAIL: no cache index at {cache_root / 'urls.json'}", file=sys.stderr)
        return 2

    missing = _missing_from_index(cache_root)
    print(f"missing html  : {len(missing):,}")
    if not missing:
        return 0

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
    suspect = [p for p in files if p.stat().st_size <= SUSPECT_MAX_BYTES]
    bad = [p for p in suspect if MARKER not in p.read_bytes()]
    missing = _missing_from_index(args.cache_dir.parent)
    bad_lists = _challenge_pages(args.cache_dir.parent / "vod_lists")

    print(f"cached pages    : {len(files):,}")
    print(f"not a title page: {len(bad):,}")
    if bad:
        sizes = sorted(p.stat().st_size for p in bad)
        print(f"  size range    : {sizes[0]:,} B – {sizes[-1]:,} B")
        print(f"  e.g. {', '.join(p.name for p in bad[:5])}")
    print(f"indexed but gone: {len(missing):,}")
    print(f"challenge lists : {len(bad_lists):,}")
    if bad_lists:
        print(f"  e.g. {', '.join(p.name for p in bad_lists[:5])}")

    if not bad and not missing and not bad_lists:
        print("\nOK: every indexed URL has a page, and every page is a title page")
        return 0

    if not args.apply:
        if bad:
            print("\nFAIL: pages are being cached that are not title pages —"
                  " scrapes are failing silently again."
                  "\n      See docs/solutions/data-quality/cached-error-pages-as-success.md"
                  "\n      Purge with --apply, then --refetch.")
        if missing:
            print(f"\nFAIL: {len(missing):,} indexed URLs have no cached page —"
                  " they will never reach the catalog."
                  "\n      Re-download with --refetch.")
        if bad_lists:
            print(f"\nFAIL: {len(bad_lists):,} listing pages are bot-protection"
                  " challenges. Each one blanks the date, distributor and platform"
                  "\n      of every title it should have carried."
                  "\n      Purge with --apply; the next harvest refetches them.")
        return 1

    for p in bad:
        p.unlink()
    for p in bad_lists:
        p.unlink()
    print(f"\ndeleted {len(bad):,} title page(s) and {len(bad_lists):,} listing page(s)"
          " — run `python3 -m csfd_vod.main scrape` to refetch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
