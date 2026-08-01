#!/usr/bin/env python3
"""Show the edges of the exported catalog, for a human to scan.

This is not a gate and it never fails. check_data_quality.py asserts the rules we
already know; this exists to surface the ones we don't — the defects nobody has
thought to write a rule for yet.

The method is deliberate: **enumerate, do not judge.** "Find anything wrong" is
not a completable task and it misses things quietly. "Show me the longest, the
shortest, the emptiest, the rarest" is completable, and the defects fall out of
the extremes on their own. Every catalog bug found so far was sitting in the top
few rows of one of these lists:

    shortest titles      -> "VI", "Ma", "#2", "$"          (unusable as labels)
    unusual characters   -> bidi isolates in 22 titles
    rarest platforms     -> "Peacock / Hulu" (two services in one link)
    rarest genres        -> vocabulary drift

Read it after each catalog sweep. Sixty seconds of looking is the whole point;
anything that makes you say "huh" is the finding.

Usage:  python3 scripts/shape_sweep.py
        python3 scripts/shape_sweep.py --top 15
        python3 scripts/shape_sweep.py --section text
"""
import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

DEFAULT_INDEX = Path("streamfinder/static/data/titles_index.json")

TEXT_FIELDS = ("title", "title_en", "slug")
LIST_FIELDS = ("genres", "platforms", "countries", "tags")
NUMERIC_FIELDS = ("rating", "year", "votes_count", "runtime_min", "season_no", "episode_no")

# Characters we expect: letters (any language), digits, whitespace and ordinary
# punctuation. Anything else is worth a look — not necessarily wrong. Emoji, CJK,
# and control characters all land here.
EXPECTED_PUNCT = set(" .,:;!?'\"()[]{}/\\-–—_&+*%#@$€£~^|<>=°·…„“”‘’«»")


def _unusual_chars(s: str) -> set[str]:
    return {
        ch for ch in s
        if not ch.isalnum() and ch not in EXPECTED_PUNCT and not ch.isspace()
    }


def _rule(title: str) -> None:
    print(f"\n{'─' * 72}\n{title}\n{'─' * 72}")


def section_coverage(titles: list, _top: int) -> None:
    """How often each field is actually populated.

    A field that quietly drops to mostly-empty is a broken pipeline stage, and it
    is invisible in any single record.
    """
    _rule("COVERAGE — how often is each field populated?")
    keys = sorted({k for t in titles for k in t})
    total = len(titles)
    rows = []
    for k in keys:
        filled = sum(
            1 for t in titles
            if t.get(k) not in (None, "", [], {})
        )
        rows.append((filled / total, k, filled))
    for pct, k, filled in sorted(rows):
        bar = "█" * int(pct * 24)
        print(f"  {k:<18} {pct:6.1%} {bar:<24} {filled:>6}/{total}")


def section_shapes(titles: list, top: int) -> None:
    """The distinct render-shapes a card can take, by how common they are.

    Every shape is a layout the UI must handle. A shape with a low count is the
    one nobody designed for and nobody looked at.
    """
    _rule("ROW SHAPES — what combinations actually occur?")

    def shape(t: dict) -> str:
        return " ".join([
            "child" if t.get("is_toplevel") is False else "work ",
            "poster" if t.get("poster") else "NOposter",
            "rating" if t.get("rating") is not None
            else ("inherit" if t.get("inherited_rating") is not None else "NOrating"),
            "genres" if t.get("genres") else "NOgenres",
            "platf" if t.get("platforms") else "NOplatf",
            "year" if t.get("year") else "NOyear",
        ])

    counts = Counter(shape(t) for t in titles)
    example = {}
    for t in titles:
        example.setdefault(shape(t), t)
    for sh, n in counts.most_common():
        ex = example[sh]
        print(f"  {n:>6}  {sh}")
        print(f"          e.g. [{ex.get('id')}] {ex.get('title')!r}")


def section_text(titles: list, top: int) -> None:
    """Longest, shortest and strangest values in each text field."""
    for field in TEXT_FIELDS:
        vals = [(t[field], t) for t in titles if isinstance(t.get(field), str) and t[field]]
        if not vals:
            continue
        _rule(f"TEXT — {field}  ({len(vals)} non-empty)")

        print(f"  longest {top}:")
        for v, t in sorted(vals, key=lambda x: -len(x[0]))[:top]:
            print(f"    {len(v):>4}  [{t.get('id')}] {v!r}")

        print(f"\n  shortest {top}:")
        for v, t in sorted(vals, key=lambda x: len(x[0]))[:top]:
            print(f"    {len(v):>4}  [{t.get('id')}] {v!r}")

        odd = [(sorted(_unusual_chars(v)), v, t) for v, t in vals if _unusual_chars(v)]
        if odd:
            print(f"\n  unusual characters ({len(odd)} values):")
            by_char = Counter(c for chars, _, _ in odd for c in chars)
            for ch, n in by_char.most_common(top):
                name = unicodedata.name(ch, "?")
                print(f"    {n:>5}x  U+{ord(ch):04X}  {name}")
            for chars, v, t in odd[:3]:
                print(f"          e.g. [{t.get('id')}] {v!r}")


def section_vocab(titles: list, top: int) -> None:
    """Rarest values in each categorical field — where junk hides.

    A vocabulary's long tail is where a mis-parse ends up: one title with a
    genre nobody else has is far more likely to be a bug than a real category.
    """
    for field in LIST_FIELDS:
        counts = Counter(v for t in titles for v in (t.get(field) or []))
        if not counts:
            continue
        _rule(f"VOCABULARY — {field}  ({len(counts)} distinct)")
        print(f"  most common:")
        for v, n in counts.most_common(5):
            print(f"    {n:>6}  {v!r}")
        print(f"\n  rarest {top}:")
        for v, n in counts.most_common()[: -top - 1 : -1]:
            print(f"    {n:>6}  {v!r}")


def section_numeric(titles: list, top: int) -> None:
    """Range and tails of each numeric field."""
    _rule("NUMERIC — ranges and tails")
    for field in NUMERIC_FIELDS:
        vals = sorted(
            (t[field], t.get("id")) for t in titles
            if isinstance(t.get(field), (int, float))
        )
        if not vals:
            continue
        nums = [v for v, _ in vals]
        mid = nums[len(nums) // 2]
        print(f"\n  {field:<14} n={len(nums):<6} min={nums[0]}  median={mid}  max={nums[-1]}")
        print(f"    lowest : {[f'{v} [{i}]' for v, i in vals[:5]]}")
        print(f"    highest: {[f'{v} [{i}]' for v, i in vals[-5:]]}")


def section_dates(titles: list, top: int) -> None:
    """vod_date spread — a bulk of identical or impossible dates is a parse bug."""
    dates = [t["vod_date"] for t in titles if t.get("vod_date")]
    if not dates:
        return
    _rule(f"DATES — vod_date  ({len(dates)} dated)")
    malformed = [d for d in dates if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)]
    if malformed:
        print(f"  malformed: {Counter(malformed).most_common(top)}")
    print(f"  earliest: {min(dates)}   latest: {max(dates)}")
    print(f"\n  busiest {top} days (a spike can mean a whole feed got one date):")
    for d, n in Counter(dates).most_common(top):
        print(f"    {n:>5}  {d}")


SECTIONS = {
    "coverage": section_coverage,
    "shapes": section_shapes,
    "text": section_text,
    "vocab": section_vocab,
    "numeric": section_numeric,
    "dates": section_dates,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    ap.add_argument("--top", type=int, default=10, help="rows per list (default 10)")
    ap.add_argument("--section", choices=sorted(SECTIONS), action="append",
                    help="limit to a section (repeatable); default is all")
    args = ap.parse_args()

    titles = json.loads(args.index.read_text(encoding="utf-8"))
    print(f"Shape sweep — {len(titles)} titles from {args.index}")

    for name in (args.section or SECTIONS):
        SECTIONS[name](titles, args.top)

    print(f"\n{'─' * 72}")
    print("Nothing here is an error. Anything that makes you say \"huh\" is the finding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
