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
       - no title renders twice (the ČSFD slug-drift duplicate bug, §11);
       - every facet pill counts the results it actually opens;
       - a set of English-name search queries each reach their title (§13 — ČSFD
         lists the country-of-origin name first, so "Squid Game" used to find
         nothing while the index stored "Ojingeo geim").
     Any failure exits non-zero so it can gate a deploy.

Canaries are matched by their CSFD root id (the first /film/{id} segment), which is
stable across re-parses. Add a new canary whenever a real gap is found, so the same
hole can never reopen unnoticed.

Usage:  python3 scripts/check_completeness.py
        python3 scripts/check_completeness.py --index path/to/titles_index.json
"""
import argparse
import json
import re
import sys
import unicodedata
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

# CSFD root id -> a query a user would plausibly type, which MUST find that work.
#
# These are all titles whose ENGLISH name is not the one ČSFD lists first: title_en
# holds the country-of-origin name ("Ojingeo geim", "Sen to Čihiro no kamikakuši"),
# so searching the English name found nothing until the parser started keeping every
# alternative name. The gate is the shipped index, because the site looks perfectly
# healthy while its search quietly cannot reach a third of the catalog.
SEARCH_CANARIES = {
    772224: "squid game",        # Hra na oliheň
    42136: "spirited away",      # Cesta do fantazie
    505790: "parasite",          # Parazit
    306731: "the intouchables",  # Nedotknutelní (title_en = "Intouchables")
}

# A complete catalog is in the thousands of works; a tiny number means the export
# or a pipeline stage broke. Loose lower bound, tightened only if it ever trips.
MIN_TOPLEVEL_WORKS = 5000

DEFAULT_INDEX = Path("streamfinder/static/data/titles_index.json")
DEFAULT_LIST_INDEX = Path("cache/list_index.json")
DEFAULT_VOD_URLS = Path("cache/vod_urls.json")

# Same shape the harvester keeps: a film/serial/season/episode overview page.
OVERVIEW_RE = re.compile(r"^https://www\.csfd\.cz/film/\d+[^/]*/(?:\d+[^/]*/)?prehled/$")


def _url_id(url: str):
    """The entity's own ČSFD id — the LAST /{id}-slug/ segment. Mirrors ids.py."""
    seg = SEGMENT_ID_RE.findall(url or "")
    return int(seg[-1]) if seg else None

# Each "/{id}-slug/" segment of a ČSFD URL is an id, and the LAST one is the entity
# itself. Mirrors transformation/ids.py — a plain "/film/(\d+)" would see only the
# first segment and collapse every episode onto its serial.
SEGMENT_ID_RE = re.compile(r"/(\d+)(?:-[^/]*)?(?=/)")


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


def _fold(value: str) -> str:
    """The frontend's search folding: strip diacritics, lowercase."""
    return "".join(
        c for c in unicodedata.normalize("NFD", value or "") if not unicodedata.combining(c)
    ).lower()


def _search_problems(titles: list) -> list[str]:
    """Each SEARCH_CANARIES query must reach its work through the shipped index."""
    by_root = {
        t.get("root_id"): t for t in titles if t.get("is_toplevel") is not False
    }
    problems = []
    for root_id, query in sorted(SEARCH_CANARIES.items()):
        t = by_root.get(root_id)
        if t is None:
            problems.append(f"search canary [{root_id}] has no top-level row at all")
            continue
        haystack = _fold(" ".join([t.get("title") or "", t.get("title_en") or "", *(t.get("alt") or [])]))
        if _fold(query) not in haystack:
            problems.append(f"'{query}' does not find [{root_id}] {t.get('title')}")
    return problems


def _facet_problems(titles: list, dimensions_path: Path) -> list[str]:
    """Every facet pill must count the results it opens.

    The filters match against titles_index.json; the pill's number came from the
    dimension tables instead. Those two drifted apart the moment a title's platforms
    started being merged between a serial and its episodes on the way into the index —
    "Lepší.TV 3 758" opened 6 377 titles, and 52 of 69 platforms were off. Asserted on
    the shipped artifact, because nothing about the site looks wrong when it happens.
    """
    if not dimensions_path.exists():
        return [f"dimensions not found: {dimensions_path}"]
    dims = json.loads(dimensions_path.read_text(encoding="utf-8"))
    problems = []
    for field in ("genres", "countries", "platforms"):
        actual = Counter(v for t in titles for v in (t.get(field) or []))
        for entry in dims.get(field, []):
            got = actual.get(entry["name"], 0)
            if got != entry["count"]:
                problems.append(
                    f"{field}: pill '{entry['name']}' says {entry['count']} but the index holds {got}")
    return problems[:5] + ([f"...and {len(problems) - 5} more"] if len(problems) > 5 else [])


def _calendar_problems(titles: list, list_index_path: Path) -> list[str]:
    """Every dated release in the cached listings must reach the calendar.

    The Kalendár groups titles by date, but `vod_date` is one field and ČSFD lists a
    running serial again every week and a film again on each new platform. Whichever
    date won, the rest were invisible: 3,977 (day, title) releases missing across
    1,137 days, 258 of the last 365. Nothing looked broken — the days were simply
    quieter than ČSFD's own listing.

    So the gate is the invariant, not a handful of names: every (csfd_id, date) the
    listing index knows about, for a title the export actually ships, must be one the
    index can render on that day. A canary list can only catch the holes someone
    already found.
    """
    if not list_index_path.exists():
        return [f"list index not found: {list_index_path} — run `csfd parse` first"]
    index = json.loads(list_index_path.read_text(encoding="utf-8"))

    shipped: dict[int, set] = {}
    for t in titles:
        csfd_id = t.get("csfd_id")
        if csfd_id is None:
            continue
        events = t.get("vod_events")
        dates = {d for d, _ in events} if events else ({t["vod_date"]} if t.get("vod_date") else set())
        shipped.setdefault(csfd_id, set()).update(dates)

    missing = set()
    for page in index.get("pages", {}).values():
        for entry in page.get("entries", []):
            date = entry.get("vod_date")
            if not date:
                continue
            seg_ids = SEGMENT_ID_RE.findall(entry.get("film_url", ""))
            if not seg_ids:
                continue
            csfd_id = int(seg_ids[-1])
            if csfd_id not in shipped:
                continue  # a title we have not scraped yet — a different gap
            if date not in shipped[csfd_id]:
                # A (title, date) pair, not a listing row — the same release is listed
                # on more than one page and must not be counted twice.
                missing.add((csfd_id, date))
    problems = [f"[{cid}] released {d} but the calendar cannot show it"
                for cid, d in sorted(missing, key=lambda m: (m[1], m[0]))]
    return problems[:5] + ([f"...and {len(problems) - 5} more"] if len(problems) > 5 else [])


def _url_list_problems(list_index_path: Path, vod_urls_path: Path) -> list[str]:
    """Every title the listings name must be on the list of titles to scrape.

    `vod_urls.json` is written from what a harvest saw during that run, so a URL that
    fell out between the fetch and the file was gone for good — and a URL missing
    there is never scraped, never parsed and never in the catalog, no matter how many
    times the pipeline runs. 791 had leaked out by 2026-09-07, 166 of them titles the
    catalog did not have at all. Checked against the listing index rather than the
    HTML, because the index is already the parsed truth about what those pages said.

    Compared by **csfd_id, not by URL**: ČSFD serves the same title under several
    slugs (`greyhound-bitva-` and `-bitka-o-atlantik`), identity is the id (§11), and
    `dedupe_titles.py` deliberately prunes the losing slug from vod_urls.json. A
    URL-level comparison would fail on every title it had just correctly cleaned up.
    """
    if not list_index_path.exists() or not vod_urls_path.exists():
        return []  # nothing cached yet — not this check's business
    index = json.loads(list_index_path.read_text(encoding="utf-8"))
    known = {_url_id(u) for u in json.loads(vod_urls_path.read_text(encoding="utf-8"))}

    missing = {}
    for page in index.get("pages", {}).values():
        for entry in page.get("entries", []):
            url = entry.get("film_url")
            if url and OVERVIEW_RE.match(url) and (cid := _url_id(url)) not in known:
                missing.setdefault(cid, url)
    problems = [f"listed on ČSFD but not in vod_urls.json: {u}" for u in sorted(missing.values())]
    return problems[:5] + ([f"...and {len(problems) - 5} more"] if len(problems) > 5 else [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    ap.add_argument("--list-index", type=Path, default=DEFAULT_LIST_INDEX)
    ap.add_argument("--vod-urls", type=Path, default=DEFAULT_VOD_URLS)
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

    search_problems = _search_problems(titles)
    if search_problems:
        for p in search_problems:
            print(f"FAIL: {p}")
        ok = False
    else:
        print("ok  : every search canary finds its title by its English name")

    facet_problems = _facet_problems(titles, args.index.parent / "dimensions.json")
    if facet_problems:
        for p in facet_problems:
            print(f"FAIL: {p}")
        ok = False
    else:
        print("ok  : every facet count matches the index it filters")

    url_problems = _url_list_problems(args.list_index, args.vod_urls)
    if url_problems:
        for p in url_problems:
            print(f"FAIL: {p}")
        ok = False
    else:
        print("ok  : every title the listings name is in vod_urls.json")

    cal_problems = _calendar_problems(titles, args.list_index)
    if cal_problems:
        for p in cal_problems:
            print(f"FAIL: {p}")
        ok = False
    else:
        print("ok  : every dated release in the listings can reach the calendar")

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
