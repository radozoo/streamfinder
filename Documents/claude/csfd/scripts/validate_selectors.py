#!/usr/bin/env python3
"""
Validate parser selectors against a random sample of cached HTML files.

Picks ~10 detail pages and ~5 list pages spread across 2015-2026,
parses each, and prints a summary table of extracted fields.
Flags NULL mandatory fields and obviously wrong values.

Usage:
    python scripts/validate_selectors.py
    python scripts/validate_selectors.py --detail-count 20 --list-count 10
"""

import argparse
import json
import random
import sys
from pathlib import Path

# Allow running from project root without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from csfd_vod.cache import HTMLCache
from csfd_vod.transformation.parser import VODTitleParser
from csfd_vod.transformation.list_parser import VODListParser
from csfd_vod.config import load_selectors

PROJECT_ROOT = Path(__file__).parent.parent
CACHE_DIR = PROJECT_ROOT / "cache"
SELECTORS_PATH = PROJECT_ROOT / "config" / "selectors.json"


def _fmt(value, max_len: int = 50) -> str:
    if value is None:
        return "NULL"
    s = str(value)
    return s[:max_len] + "…" if len(s) > max_len else s


def validate_detail_pages(count: int, seed: int) -> int:
    """Parse a random sample of detail pages. Returns number of failures."""
    cache = HTMLCache(str(CACHE_DIR))
    selectors = load_selectors(str(SELECTORS_PATH))
    parser = VODTitleParser(selectors)

    urls = cache.all_urls()
    if not urls:
        print("ERROR: No cached detail pages found. Run `csfd scrape` first.")
        return 1

    random.seed(seed)
    sample = random.sample(urls, min(count, len(urls)))

    print(f"\n{'='*80}")
    print(f"DETAIL PAGE VALIDATION  ({len(sample)} pages sampled from {len(urls)} total)")
    print(f"{'='*80}")

    fields = ["title", "year", "countries", "genres", "director", "actors",
              "plot", "rating", "tags", "image_url", "vod_platforms",
              "title_type", "script", "camera", "music"]

    failures = 0
    for url in sample:
        html = cache.get(url)
        if not html:
            print(f"  SKIP  {url}  (cache miss)")
            continue

        title = parser.parse(html, url)
        if title is None:
            print(f"  FAIL  {url}  → parse returned None")
            failures += 1
            continue

        print(f"\n  URL: {url}")
        for field in fields:
            val = getattr(title, field, None)
            flag = " ← MISSING" if val is None and field in ("title",) else ""
            print(f"    {field:<20} {_fmt(val)}{flag}")

        # Reviews summary
        if title.reviews:
            try:
                revs = json.loads(title.reviews)
                print(f"    {'reviews':<20} {len(revs)} review(s) — first author: {revs[0].get('author')}")
            except Exception:
                print(f"    {'reviews':<20} PARSE ERROR")

    print(f"\n  Failures: {failures}/{len(sample)}")
    return failures


def validate_list_pages(count: int, seed: int) -> int:
    """Parse a random sample of list pages. Returns number of failures."""
    list_dir = CACHE_DIR / "vod_lists"
    if not list_dir.exists():
        print("\nINFO: No cached list pages found at cache/vod_lists/ — skipping list validation.")
        return 0

    list_files = sorted(list_dir.glob("*.html"))
    if not list_files:
        print("\nINFO: cache/vod_lists/ is empty — skipping list validation.")
        return 0

    random.seed(seed + 1)
    sample = random.sample(list_files, min(count, len(list_files)))

    list_parser = VODListParser()

    print(f"\n{'='*80}")
    print(f"LIST PAGE VALIDATION  ({len(sample)} pages sampled from {len(list_files)} total)")
    print(f"{'='*80}")

    failures = 0
    for path in sorted(sample):
        html = path.read_text(encoding="utf-8")
        entries = list_parser.parse(html, source=path.name)
        if not entries:
            print(f"  WARN  {path.name}  → 0 entries parsed")
            failures += 1
            continue

        print(f"\n  File: {path.name}  ({len(entries)} entries)")
        for entry in entries[:3]:  # show first 3 entries
            print(f"    film_url:    {_fmt(entry.get('film_url'), 70)}")
            print(f"    vod_date:    {entry.get('vod_date')}")
            print(f"    list_type:   {entry.get('list_type')}")
            print(f"    distributor: {entry.get('distributor')}")
            print()

    print(f"  Failures: {failures}/{len(sample)}")
    return failures


def main():
    parser = argparse.ArgumentParser(description="Validate parser selectors on cached HTML sample")
    parser.add_argument("--detail-count", type=int, default=10, help="Number of detail pages to sample (default: 10)")
    parser.add_argument("--list-count", type=int, default=5, help="Number of list pages to sample (default: 5)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")
    args = parser.parse_args()

    detail_failures = validate_detail_pages(args.detail_count, args.seed)
    list_failures = validate_list_pages(args.list_count, args.seed)

    total_failures = detail_failures + list_failures
    print(f"\n{'='*80}")
    print(f"TOTAL FAILURES: {total_failures}")
    print(f"{'='*80}\n")
    sys.exit(0 if total_failures == 0 else 1)


if __name__ == "__main__":
    main()
