#!/usr/bin/env python3
"""Data-quality guard for the Streamfinder catalog.

Sibling of check_completeness.py. That script asks "is everything *there*?"
(known titles present, no duplicates). This one asks "are the *values* sane?" —
the class of bug that ships a perfectly-structured catalog full of unreadable
text, dangling references, or a platform listed twice under two spellings.

Every rule here exists because it already went wrong once. Each names the
solution doc that records the incident, so a failure can be read in context and
nobody has to re-derive why the rule is there. When a new data bug is found and
fixed, add a rule — that is what stops it from coming back (docs/solutions
frontmatter carries the reverse link in its `guard:` field).

Severities:
  FAIL — blocks the deploy. Zero-tolerance invariants, or budgets that must ratchet down.
  WARN — printed, does not block. Things a human should glance at, not a defect per se.

Usage:  python3 scripts/check_data_quality.py
        python3 scripts/check_data_quality.py --data-dir streamfinder/static/data
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

DEFAULT_DATA_DIR = Path("streamfinder/static/data")

# Text fields shown to a user. Anything invisible or stray in these lands on screen.
TEXT_FIELDS = ("title", "title_en", "slug")

# Bidi isolates/embeddings and zero-width marks. ČSFD wraps some episode names in
# U+2068/U+2069; invisible, but they break trimming, sorting and equality.
# See: 2026-08-01-csfd-bidi-isolates-in-titles
CONTROL_CHARS = re.compile(r"[​-‏  ‪-‮⁦-⁩﻿]")

# Dangling child -> serial references. Backfilled by scripts/backfill_missing_roots.py;
# a residue remains for serials whose ČSFD page is gone. Lower this as it shrinks,
# never raise it — that is the ratchet.
# See: 2026-08-01-orphaned-episode-roots
MAX_ORPHANED_CHILDREN = 0

# A shipped catalog never legitimately shrinks. Allow a little slack for ČSFD
# delistings; a real drop means a pipeline stage silently truncated.
# See: 2026-08-01-harvest-overwrote-url-manifest
MAX_SHRINK_RATIO = 0.02

# Platform pairs that LOOK like one service spelled twice but are genuinely separate,
# checked against ČSFD's own listings. Keeps the alias check honest instead of
# silencing it. Add a pair only after verifying the two really are distinct.
#   Apple TV   = the rental/purchase store;  Apple TV+ = the subscription service
#   YouTube    = free/ad-supported;  Movies = rentals;  Premium = subscription
CONFIRMED_DISTINCT = {
    frozenset({"Apple TV", "Apple TV+"}),
    frozenset({"YouTube", "YouTube Movies"}),
    frozenset({"YouTube", "YouTube Premium"}),
    frozenset({"YouTube Movies", "YouTube Premium"}),
}


def _fail(msgs: list[str], msg: str) -> None:
    msgs.append(msg)


def check_control_chars(titles: list) -> list[str]:
    """No invisible control/bidi characters in any user-visible text field."""
    bad = [
        (t.get("id"), f, t[f])
        for t in titles
        for f in TEXT_FIELDS
        if isinstance(t.get(f), str) and CONTROL_CHARS.search(t[f])
    ]
    if not bad:
        return []
    sample = ", ".join(f"[{i}] {f}={v!r}" for i, f, v in bad[:3])
    return [f"{len(bad)} field(s) contain invisible control chars: {sample}"]


def check_whitespace(titles: list) -> list[str]:
    """Text fields are trimmed and single-spaced — no newlines, tabs or double spaces."""
    bad = [
        (t.get("id"), f, t[f])
        for t in titles
        for f in TEXT_FIELDS
        if isinstance(t.get(f), str) and (t[f] != t[f].strip() or re.search(r"[\n\t]|  ", t[f]))
    ]
    if not bad:
        return []
    sample = ", ".join(f"[{i}] {f}={v!r}" for i, f, v in bad[:3])
    return [f"{len(bad)} field(s) have stray whitespace: {sample}"]


def check_root_references(titles: list) -> list[str]:
    """Every episode/season resolves to a serial that exists in the index.

    A dangling reference means the Katalóg is missing the work entirely and the
    card has no serial name to show — it falls back to raw text like
    "Young Rock- Season 1".
    """
    ids = {t.get("id") for t in titles}
    orphans = [
        t for t in titles
        if t.get("is_toplevel") is False and t.get("root_title_id") not in ids
    ]
    if len(orphans) <= MAX_ORPHANED_CHILDREN:
        return []
    roots = {t.get("root_id") for t in orphans}
    return [
        f"{len(orphans)} child rows across {len(roots)} serial(s) have no top-level work "
        f"(budget {MAX_ORPHANED_CHILDREN}) — run scripts/backfill_missing_roots.py"
    ]


def check_platform_aliases(titles: list, dimensions: dict) -> list[str]:
    """No platform listed under two spellings.

    ČSFD names the same service inconsistently ("HBO Max" vs "Max", "Voyo" vs
    "Oneplay"), which splits one platform into two filters. The exporter
    canonicalises via _PLATFORM_ALIASES; this asserts the result. Rather than a
    whitelist that would need editing whenever a real new service appears, it
    flags names that collapse onto each other once case and punctuation are removed.
    """
    names = [p["name"] for p in dimensions.get("platforms", [])]

    def key(n: str) -> str:
        return re.sub(r"[^a-z0-9]", "", n.lower())

    collisions: dict[str, list[str]] = {}
    for n in names:
        collisions.setdefault(key(n), []).append(n)
    dupes = [
        v for v in collisions.values()
        if len(v) > 1 and frozenset(v) not in CONFIRMED_DISTINCT
    ]

    # One name fully contained in another ("Max" inside "HBO Max") is the shape the
    # real duplicates took. Substring alone is noisy, so require a word boundary.
    contained = [
        (a, b) for a in names for b in names
        if a != b
        and re.search(rf"(^|\s){re.escape(a)}(\s|$)", b)
        and frozenset({a, b}) not in CONFIRMED_DISTINCT
    ]

    problems = []
    if dupes:
        problems.append(f"platform names differing only in case/punctuation: {dupes[:3]}")
    if contained:
        problems.append(
            f"platform name contained in another (possible duplicate service): {contained[:3]}"
        )
    return problems


def check_vocabularies(titles: list, dimensions: dict) -> list[str]:
    """Genres on titles all exist in the genre dimension (no vocabulary drift)."""
    known = {g["name"] for g in dimensions.get("genres", [])}
    used = {g for t in titles for g in (t.get("genres") or [])}
    unknown = used - known
    if not unknown:
        return []
    return [f"{len(unknown)} genre(s) on titles missing from dimensions: {sorted(unknown)[:5]}"]


def check_value_ranges(titles: list) -> list[str]:
    """Numeric and date fields fall inside their possible range."""
    next_year = date.today().year + 1
    problems = []

    bad_rating = [t.get("id") for t in titles
                  if t.get("rating") is not None and not 0 <= t["rating"] <= 100]
    if bad_rating:
        problems.append(f"{len(bad_rating)} rating(s) outside 0–100: e.g. {bad_rating[:3]}")

    bad_year = [t.get("id") for t in titles
                if t.get("year") is not None and not 1888 <= t["year"] <= next_year]
    if bad_year:
        problems.append(f"{len(bad_year)} year(s) outside 1888–{next_year}: e.g. {bad_year[:3]}")

    bad_date = [t.get("id") for t in titles
                if t.get("vod_date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", t["vod_date"])]
    if bad_date:
        problems.append(f"{len(bad_date)} unparseable vod_date(s): e.g. {bad_date[:3]}")

    return problems


def check_no_truncation_ceiling(titles: list) -> list[str]:
    """Popular titles must not pile up against a suspiciously round ceiling.

    ČSFD groups thousands with a non-breaking space, so a naive `(\\d+)` captured
    only the leading group: Forrest Gump's 131654 ratings were stored as 131 and
    the whole catalog's maximum sat at exactly 999. Nothing errored, and every
    feature ranking by popularity or obscurity was quietly wrong.

    In a catalog this size at least one title must exceed a few thousand votes.
    A maximum stuck just below a power of ten means digits are being dropped.
    See: 2026-08-01-votes-count-thousands-separator
    """
    votes = [t["votes_count"] for t in titles if isinstance(t.get("votes_count"), int)]
    if not votes:
        return []
    top = max(votes)
    for ceiling in (1_000, 10_000, 100_000):
        if 0.95 * ceiling <= top < ceiling:
            return [
                f"max votes_count is {top}, just under {ceiling:,} — digits are "
                f"probably being truncated at a thousands separator"
            ]
    return []


def check_detail_shards(titles: list, data_dir: Path) -> list[str]:
    """Every index entry has its detail file, and no detail file is orphaned.

    The index and the per-title shards are written by the same exporter run, so a
    mismatch means a partial write — which shows up as a 404 on the detail page.
    """
    detail_dir = data_dir / "detail"
    if not detail_dir.is_dir():
        return [f"detail/ directory missing at {detail_dir}"]

    on_disk = {p.stem for p in detail_dir.glob("*.json")}
    expected = {f"{t['id']}-{t['slug']}" for t in titles}

    problems = []
    missing = expected - on_disk
    orphaned = on_disk - expected
    if missing:
        problems.append(f"{len(missing)} index entries have no detail file: e.g. {sorted(missing)[:3]}")
    if orphaned:
        problems.append(f"{len(orphaned)} orphaned detail file(s): e.g. {sorted(orphaned)[:3]}")
    return problems


def check_no_shrink(titles: list, index_path: Path) -> tuple[list[str], list[str]]:
    """The catalog must not shrink against the last committed export.

    Silent data loss is the worst failure mode here because nothing errors — the
    harvest that rewrote vod_urls.json from 49113 URLs down to 1538 looked like a
    clean success. Returns (failures, warnings); a missing baseline is a warning.
    """
    try:
        prev_raw = subprocess.run(
            ["git", "show", f"HEAD:{index_path.as_posix()}"],
            capture_output=True, text=True, timeout=120, check=True,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return [], ["no committed baseline to compare against (first export?)"]

    prev = len(json.loads(prev_raw))
    now = len(titles)
    if prev and now < prev * (1 - MAX_SHRINK_RATIO):
        return [f"catalog shrank {prev} -> {now} titles (> {MAX_SHRINK_RATIO:.0%})"], []
    return [], [f"catalog size {prev} -> {now}"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = ap.parse_args()

    index_path = args.data_dir / "titles_index.json"
    dims_path = args.data_dir / "dimensions.json"
    for p in (index_path, dims_path):
        if not p.exists():
            print(f"FAIL: {p} not found", file=sys.stderr)
            return 2

    titles = json.loads(index_path.read_text(encoding="utf-8"))
    dimensions = json.loads(dims_path.read_text(encoding="utf-8"))

    shrink_fail, shrink_warn = check_no_shrink(titles, index_path)
    checks = [
        ("no invisible control chars", check_control_chars(titles)),
        ("text fields trimmed", check_whitespace(titles)),
        ("episodes resolve to a serial", check_root_references(titles)),
        ("no duplicate platform spellings", check_platform_aliases(titles, dimensions)),
        ("genres match dimensions", check_vocabularies(titles, dimensions)),
        ("values within range", check_value_ranges(titles)),
        ("no truncation ceiling", check_no_truncation_ceiling(titles)),
        ("detail shards match index", check_detail_shards(titles, args.data_dir)),
        ("catalog did not shrink", shrink_fail),
    ]

    ok = True
    for label, problems in checks:
        if problems:
            ok = False
            for p in problems:
                print(f"FAIL: {label} — {p}")
        else:
            print(f"ok  : {label}")

    for w in shrink_warn:
        print(f"warn: {w}")

    if ok:
        print(f"\nALL DATA-QUALITY CHECKS PASSED ({len(titles)} titles)")
        return 0
    print("\nDATA-QUALITY CHECK FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
