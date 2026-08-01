---
id: "2026-08-01-votes-count-thousands-separator"
date: "2026-08-01"
project: "csfd/streamfinder"
scope:
  - "src/csfd_vod/transformation/parser.py"
  - "csfd_vod.fact_titles.votes_count (PostgreSQL)"
  - "streamfinder/src/routes/+page.ts"
guard: "check_data_quality.py::check_no_truncation_ceiling"
tags:
  - data-quality
  - scraping
  - silent-truncation
  - unicode
  - ranking
---

# Every popular title's vote count was truncated to its first thousands group

## Symptom

Found by `scripts/shape_sweep.py`, not by a bug report. The numeric section
showed:

```
votes_count    n=43490  min=1  median=22  max=999
```

A maximum of exactly **999** across 43 490 titles is not a distribution, it is a
ceiling. No catalog of 50 000 films has its most-rated title sitting at 999 votes.

Confirmed against the cached HTML:

```
raw   : 'Hodnocení (131 654) golfista POMO …'   (U+00A0 between 131 and 654)
stored: 131
```

Forrest Gump has **131 654** ratings. We had **131**.

## Root Cause

```python
re.search(r"Hodnocen[íi]\D*(\d+)", votes_text)
```

ČSFD groups thousands with a **non-breaking space** (`U+00A0`). `\d+` stops at the
first non-digit, so it captured only the leading group. Any title with 1 000 or
more ratings was silently divided down to its first one to three digits; titles
under 1 000 were parsed correctly, which is exactly why the field looked healthy
in every spot check.

## Blast radius

`votes_count` is not a display field — it drives ranking:

- **Artové filmy** rail: "obscurity" is a decade-cohort percentile of `votes_count`.
  Famous films were scoring as obscure, because famous films are precisely the ones
  whose counts got truncated.
- **Skryté klenoty** rail: same inversion.
- `TMDBEnricher._load_pending`: `ORDER BY votes_count DESC` — enrichment priority
  was ordered by a mangled key.

### A wrong diagnosis this corrects

Earlier in the same session, Kmotr (72) and Forrest Gump (131) turning up in the
art-films rail was explained away as "a data artifact — probably a secondary or
reissue catalog entry with its own low vote count", and written off as a known
limitation. That was wrong. There was one entry, and the number was simply
truncated. The anomaly was real evidence and it got rationalised instead of
investigated.

## Fix

```python
votes_match = re.search(r"Hodnocen[íi]\D*([\d \s.,]*\d)", votes_text)
if votes_match:
    data["votes_count"] = int(re.sub(r"\D", "", votes_match.group(1)))
```

Match the separators as part of the number, then keep only digits. Verified
against nbsp, plain space, dot and comma grouping, and against text that
continues after the number.

## Why it went unnoticed

- Nothing errored; `131` is a perfectly valid vote count.
- There was **no test at all** for `votes_count` — the field was never asserted.
- Both `check_completeness.py` and manual review look at whether values exist and
  are in range. `131` is in range. Only the *shape of the distribution across the
  whole catalog* gives it away, and nothing was looking at that.

## Prevention

- [ ] A scraped number that can exceed 999 is parsed with its thousands separators
- [ ] Every parsed field has at least one test asserting a realistic value
- [ ] Distributions, not just individual values, are reviewed after a catalog sweep
- [ ] `check_data_quality.py` fails when a maximum sits just below a power of ten
