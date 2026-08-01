---
id: "2026-08-01-card-subline-semantics"
date: "2026-08-01"
project: "csfd/streamfinder"
scope:
  - "streamfinder/src/lib/components/PosterCard.svelte"
guard: "streamfinder/src/lib/components/PosterCard.test.ts (sub-line group); discovery via scripts/shape_sweep.py"
tags:
  - ui-bugs
  - information-design
  - data-shape
---

# The one line under a card title meant two different things

## Symptom

Reported twice, from two directions:

1. *"Some titles show the season/episode instead of the genre"* — Ted Lasso,
   Trying and others showed `S4·E1 · Epizoda 1` where every other card showed
   `Drama · Thriller`.
2. After the first fix: *"weird texts show up"* — Silo showed `Paměť`, Sugar
   showed `Co máš ještě v rukáv…`.

The second report is the interesting one, because that data was **correct** —
those are the real Czech episode names from ČSFD.

## Root Cause

The sub-line had no single meaning. For a top-level work it was the genre; for an
episode it was the season/episode marker plus the episode's own name. One slot,
two contracts, so the eye could not learn what to expect there.

The first fix (keep the episode name, drop the redundant `S·E` marker, fall back
to genre for placeholder names) was still wrong, because it assumed episode names
are descriptive. An audit across all 15 694 child rows showed they are not:

| shape | count | example |
|---|---|---|
| leftover season suffix | 1 390 | `Young Rock- Season 1` |
| long enough to truncate mid-word | 174 | `Nevinnost vymizí, když zjistíte, co je…` |
| a bare clock time | 57 | Urgent → `21:00` |
| invisible control characters | 40 | `⁨Križovatka úspechu` |
| one or two characters | 11 | `VI`, `Ma`, `#2`, `Uf` |

Roughly 1 in 6 episode names is unusable as a card descriptor. A name like
`Paměť` is not defective — but sitting unlabelled where the genre normally is, it
reads as a stray fragment.

## Fix

One line, one meaning: **the sub-line is always the genre**, on every card.

The episode's position is already carried by the `S3·E5` badge on the poster, and
its name belongs on the detail page where it has room and a label. Nothing is
lost from the interface; the ambiguity is.

```svelte
let subLine = $derived(title.genres.slice(0, 2).join(' · ') || null);
```

## Why it went unnoticed

`svelte-check` reports type errors, and the types were fine — a string went into
a slot that expects a string. No test rendered a card and read the resulting text,
and the failure only becomes obvious when cards sit side by side and one of them
says `21:00` where its neighbours say `Drama`.

## Prevention

This one is **not assertable**. "Reads as a stray fragment" has no rule; `21:00`
is a legitimate string in a legitimate field. It is caught by looking, so the
process has to guarantee that someone looks:

- [ ] A slot in the UI has exactly one meaning, whatever the row's shape
- [ ] Before trusting a field as a label, check its extremes — longest, shortest, emptiest
- [ ] The shape sweep lists per-field outliers after each catalog sweep, for a human to scan
