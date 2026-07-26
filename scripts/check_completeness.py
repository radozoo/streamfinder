#!/usr/bin/env python3
"""Post-harvest completeness guard for the Streamfinder catalog.

Two independent checks run in the pipeline:

  1. In-harvest invariant (scraper.scrape_vod_all_urls): every month is harvested
     to CSFD's own declared last page. Truncation is reported as `incomplete_months`.

  2. This script — a canary test against the FINAL exported catalog. It asserts:
       - a curated set of known-VOD titles each appear in titles_index.json (a
         missing one means a month or code path silently dropped it — the exact
         failure that lost True Detective and Twin Peaks);
       - a loose minimum work count;
       - no title renders twice (the ČSFD slug-drift duplicate bug, §11).
     Any failure exits non-zero so it can gate a deploy.

Canaries are matched by their CSFD root id (the first /film/{id} segment), which is
stable across re-parses. Add a new canary whenever a real gap is found, so the same
hole can never reopen unnoticed.

Usage:  python3 scripts/check_completeness.py
        python3 scripts/check_completeness.py --index path/to/titles_index.json
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# CSFD root id -> human label. Each MUST be present in the catalog.
CANARIES = {
    328992: "Temný případ (True Detective) — HBO Max",
    70049: "Městečko Twin Peaks — Prime Video / SkyShowtime",
    1667978: "Star Wars: Maul - Pán stínů — Disney+",
    1000137: "Yellowjackets",
    930640: "Neporazitelný",
    1361414: "Čmuchalové",
    224291: "Dexter (2006) — Prime Video / SkyShowtime (undated catalog title)",
}

# A complete catalog is in the thousands of works; a tiny number means the export
# or a pipeline stage broke. Loose lower bound, tightened only if it ever trips.
MIN_TOPLEVEL_WORKS = 5000

DEFAULT_INDEX = Path("streamfinder/static/data/titles_index.json")


def _duplicate_problems(titles: list) -> list[str]:
    """Detect titles that would render more than once — the ČSFD slug-drift bug.

    ČSFD renames slugs over time, so the same work/episode can get a second row
    under a new url_id (see docs csfd-scraping-rules §11). The DB dedupe and the
    exporter guard should prevent that; this asserts it on the SHIPPED artifact so
    a regression fails the deploy gate instead of quietly doubling titles on the
    site. Episodes carry no csfd_id in the index, so we key on render identity:
      - one card per title id (structural),
      - one top-level work per root_id,
      - one episode per (root_id, season_no, episode_no).
    """
    problems = []

    dup_ids = [k for k, v in Counter(t.get("id") for t in titles).items() if v > 1]
    if dup_ids:
        problems.append(f"{len(dup_ids)} duplicate title id(s): e.g. {dup_ids[:3]}")

    tl_roots = Counter(
        t.get("root_id") for t in titles
        if t.get("is_toplevel") is not False and t.get("root_id") is not None
    )
    dup_tl = [k for k, v in tl_roots.items() if v > 1]
    if dup_tl:
        problems.append(f"{len(dup_tl)} root_id(s) with >1 top-level work (slug drift): e.g. {dup_tl[:3]}")

    ep_keys = Counter(
        (t.get("root_id"), t.get("season_no"), t.get("episode_no")) for t in titles
        if t.get("is_toplevel") is False and t.get("episode_no") is not None
    )
    dup_ep = [k for k, v in ep_keys.items() if v > 1]
    if dup_ep:
        problems.append(f"{len(dup_ep)} duplicate episode(s) (slug drift): e.g. {dup_ep[:3]}")

    return problems


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

    dup_problems = _duplicate_problems(titles)
    if dup_problems:
        for p in dup_problems:
            print(f"FAIL: {p}")
        ok = False
    else:
        print("ok  : no duplicate titles (slug-drift guard)")

    if ok:
        print("\nALL COMPLETENESS CHECKS PASSED")
        return 0
    print("\nCOMPLETENESS CHECK FAILED — a known VOD title is missing from the catalog")
    return 1


if __name__ == "__main__":
    sys.exit(main())
