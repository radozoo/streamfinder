---
id: "2026-08-01-orphaned-episode-roots"
date: "2026-08-01"
project: "csfd/streamfinder"
scope:
  - "scripts/backfill_missing_roots.py"
  - "csfd_vod.fact_titles.root_id (PostgreSQL)"
  - "src/csfd_vod/export/streamfinder_exporter.py"
guard: "check_data_quality.py::check_root_references"
tags:
  - data-quality
  - referential-integrity
  - hierarchy
  - catalog-completeness
---

# 549 serials existed only as episodes, never as works

## Symptom

Cards in the Kalendár showed raw text where a serial name belonged:

```
Young Rock- Season 1
Loajalita- Série 3
```

Investigating that text led to the real problem: **549 serials had no top-level
row at all** — among them South Park, Chicago Fire, Zákon a pořádek and Bobovy
burgery. 1 796 episode/season rows pointed at a parent that did not exist.

Because the Katalóg lists works (not release events), those serials were simply
**absent from the catalog** — not mis-rendered, missing.

## Root Cause

ČSFD's `/vod` feed is a stream of *release events*. For a long-running show it
lists "episode 11 of season 27 arrived", never the serial's own page. The harvest
therefore collected thousands of child URLs whose root was never itself a VOD
event, so it was never queued for scraping.

`root_id` was parsed correctly from the URL the whole time (`971818` for Young
Rock). There was just no row with `csfd_id = 971818` for it to point at, so the
exporter emitted `root_title_id: null` and the card had no serial name to show —
falling back to the season row's own ČSFD title, `"Young Rock- Season 1"`.

## Fix

`scripts/backfill_missing_roots.py` already existed for exactly this shape. It
finds every `root_id` referenced by a child with no top-level row, reconstructs
the serial URL from the child's first URL segment, and downloads it into the HTML
cache. `parse` afterwards loads the new pages and refreshes the hierarchy fields.

The reason it had drifted this far is that nothing measured the gap — the script
had to be remembered and run by hand.

## Why it went unnoticed

`check_completeness.py` asserts that a curated list of canary titles is present
and that the catalog is above a floor count. Both passed: the catalog had 49 883
titles and every canary was there. Nothing asserted that a title's *references*
resolve, so a missing serial was invisible unless someone happened to look for
that specific show.

The failure is quiet in the worst way — the episodes are all present and dated,
so the catalog looks busy and complete.

## Prevention

- [ ] Every `is_toplevel: false` row resolves to a real `root_title_id` in the index
- [ ] The orphan budget in `check_data_quality.py` only ever ratchets down
- [ ] After a harvest that adds child URLs, run `backfill_missing_roots.py` before export
