#!/usr/bin/env python3
"""Post-harvest completeness guard for the Streamfinder catalog.

Two independent checks run in the pipeline:

  1. In-harvest invariant (scraper.scrape_vod_all_urls): every month is harvested
     to CSFD's own declared last page. Truncation is reported as `incomplete_months`.

  2. This script — a canary test against the FINAL exported catalog. A curated set
     of titles that are known to be on Czech VOD must each appear in
     titles_index.json. If a canary is missing, a month (or a code path) silently
     dropped it — the exact failure that lost True Detective and Twin Peaks — and
     this exits non-zero so it can gate a deploy.

Canaries are matched by their CSFD root id (the first /film/{id} segment), which is
stable across re-parses. Add a new canary whenever a real gap is found, so the same
hole can never reopen unnoticed.

Usage:  python3 scripts/check_completeness.py
        python3 scripts/check_completeness.py --index path/to/titles_index.json
"""
import argparse
import json
import sys
from pathlib import Path

# CSFD root id -> human label. Each MUST be present in the catalog.
CANARIES = {
    328992: "Temný případ (True Detective) — HBO Max",
    70049: "Městečko Twin Peaks — Prime Video / SkyShowtime",
    1667978: "Star Wars: Maul - Pán stínů — Disney+",
    1000137: "Yellowjackets",
    930640: "Neporazitelný",
    1361414: "Čmuchalové",
}

# A complete catalog is in the thousands of works; a tiny number means the export
# or a pipeline stage broke. Loose lower bound, tightened only if it ever trips.
MIN_TOPLEVEL_WORKS = 5000

DEFAULT_INDEX = Path("streamfinder/static/data/titles_index.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    args = ap.parse_args()

    if not args.index.exists():
        print(f"FAIL: index not found: {args.index}", file=sys.stderr)
        return 2

    titles = json.loads(args.index.read_text(encoding="utf-8"))
    root_ids = {t.get("root_id") for t in titles}
    toplevel = [t for t in titles if t.get("is_toplevel") is not False]

    ok = True

    if len(toplevel) < MIN_TOPLEVEL_WORKS:
        print(f"FAIL: only {len(toplevel)} top-level works (< {MIN_TOPLEVEL_WORKS})")
        ok = False
    else:
        print(f"ok: {len(toplevel)} top-level works")

    for csfd_id, label in sorted(CANARIES.items()):
        present = csfd_id in root_ids
        print(f"{'ok  ' if present else 'FAIL'}: [{csfd_id}] {label}")
        ok = ok and present

    if ok:
        print("\nALL COMPLETENESS CHECKS PASSED")
        return 0
    print("\nCOMPLETENESS CHECK FAILED — a known VOD title is missing from the catalog")
    return 1


if __name__ == "__main__":
    sys.exit(main())
