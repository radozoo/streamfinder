---
name: csfd-scraping
description: Working on the CSFD → Streamfinder data pipeline — harvesting the csfd.cz /vod listing, scraping title pages, parsing/loading to Postgres, or exporting the catalog. Load before changing the scraper, parser, loader or exporter, or when debugging missing / duplicate / wrong catalog data. CSFD is full of non-obvious traps; this encodes them.
---

# CSFD VOD pipeline

Stages (run from repo root, interpreter is `python3`):

```
harvest    python3 -m csfd_vod.main harvest --from-year 2015   # collect /vod URLs → cache/vod_urls.json
harvest-platforms  python3 -m csfd_vod.main harvest-platforms  # + undated catalog titles (see below)
scrape     python3 -m csfd_vod.main scrape                     # download title pages → cache/html/
parse      python3 -m csfd_vod.main parse                      # parse ALL cached HTML → Postgres (idempotent)
enrich     python3 -m csfd_vod.main enrich                     # TMDB posters/trailers (needs TMDB_API_KEY)
streamfinder  python3 -m csfd_vod.main streamfinder            # export streamfinder/static/data/*.json
update     python3 -m csfd_vod.main update                     # incremental refresh (see below)
```

DB is `postgresql:///csfd_vod`. `.env` holds `TMDB_API_KEY` and is gitignored —
**never commit it**. Backfill helpers live in `scripts/` (`backfill_missing_works.py`,
`backfill_missing_roots.py`, `rescrape_broken_roots.py`).

## Before you ship a pipeline change — checklist

1. **Frontend:** `cd streamfinder && npm run check && npm run build` (0 errors).
2. **Catalog canary:** `python3 scripts/check_completeness.py` — known-VOD titles
   (True Detective, Twin Peaks, …) + a minimum work count + **no duplicate titles**
   (the slug-drift guard) must pass. It exits non-zero; treat that as a deploy gate.
3. **After a harvest:** check the returned `complete` / `incomplete_months`.
4. **Found a new gap?** Add a canary to `check_completeness.py` and a rule to
   `docs/csfd-scraping-rules.md`, so the same hole can't reopen unnoticed.
5. **Re-parse is safe** — the loader rebuilds each title's dimensions (idempotent),
   so `parse` after any parser change won't leave stale rows.

## Gotchas that WILL bite you

Full detail + code pointers in **`docs/csfd-scraping-rules.md`**. The short list:

- **Bot protection.** csfd.cz blocks plain HTTP and `WebFetch` (Anubis/BotStopper).
  Use the Playwright scraper. `WebSearch` is fine only to find a URL.
- **Phantom paginator.** The listing's page 1 always links to a far page (e.g. 20)
  no matter the real count. Never trust it as the last page. The real end is a page
  whose items **repeat the previous page** (CSFD *clamps* out-of-range pages).
- **Global-`seen` truncation.** Never stop a month on "no *new* URLs" — `seen` is
  global across months, so a mid-month page of re-releases would truncate the rest.
  This bug hid True Detective and Twin Peaks. Stop only on clamp/empty.
- **Genres:** collect BOTH `<a>` links and **bare-text** nodes in `.genres`
  (Mysteriózní, Rodinný, Stand-up… have no `/zanry/` page). `.genres a` alone drops
  them on ~34% of titles.
- **VOD platforms:** select `.film-vod-list .box-film-vod-services a` only — plain
  `.film-vod-list a` also grabs the `/vod/` heading (bogus "VOD" platform) and the
  "více" toggle. Distributor fallback for services without a `/vod/` page.
- **Loader idempotency:** dimensions are delete-then-insert; `ON CONFLICT DO NOTHING`
  alone lets stale values survive a re-parse.
- **Not everything that looks like junk is junk:** `"Director X"` is a real director.
  Verify against the scraped page before deleting suspicious-looking data.
- **Two harvest sources.** The monthly `/vod/?year=&month=` feed only sees a
  title's dated VOD *arrival* — an old catalog title with no dated event (Dexter,
  Game of Thrones) is invisible to it. `harvest-platforms` covers this via each
  platform's `/vod/{slug}/` browse listing, which DOES clamp like the monthly feed
  (unlike the base `/vod/` browse or its query facets, which never terminate —
  don't try to harvest those exhaustively). See rules doc §1b.
- **Hierarchy:** `root_id` = first `/film/{id}` segment, `csfd_id` = last;
  `is_toplevel = root_id == csfd_id`. Katalóg = works, Kalendár = release events.
- **Slug drift → duplicates.** ČSFD renames slugs over time (`…-episode-5/` →
  `…-pamet/`, `…-the-miniature-wife/` → `…-miniaturni-manzelka/`) while the id
  stays. Since `url_id` carries the slug, a rename INSERTs a *second* row for the
  same `csfd_id` → the title renders twice. Identity is `csfd_id`, not `url_id`.
  `scripts/dedupe_titles.py` cleans it (DB + cache + vod_urls), `update` self-heals
  after load, and the exporter dedupes by `csfd_id` as a net. See rules doc §11.

## Keeping the catalog fresh over time

Re-scraping the whole catalog on a schedule is not viable (bot protection + cost).
`python3 -m csfd_vod.main update` does an incremental refresh: **discover** (forced
re-harvest of the last N months → union new URLs → download only the new pages;
catches new releases *and* new episodes of running series), **refresh** (budget-capped
re-scrape of hot titles — young or still unrated — via `select_refresh_urls`), then
parse → enrich (missing only) → export. Flags: `--discover-months`, `--refresh-budget`,
`--refresh-max-age-days`, `--skip-*`, `--dry-run`. It **never commits/pushes** — a human
runs `check_completeness.py` and does that. Two safety properties baked in:
**bad-page overwrite protection** (loader COALESCEs volatile fields, and refresh
rejects a challenge page that parses to no title — a bad page can only ADD, never
erase a good rating/poster) and evergreen soaps fall out of refresh naturally
(old + well-voted). **Deferred:** delisting reconciliation (needs a `complete`
harvest + per-month URL snapshots), dedicated state columns, DB-level evergreen
freezing. Full design: **`docs/update-architecture.md`**.

## When something is missing from the catalog

1. Confirm it's on VOD: `WebSearch` for the csfd.cz film URL, then scrape the page
   with the Playwright scraper and check `.film-vod-list`.
2. Get its `root_id` (first `/film/{id}` segment). If the root isn't in the DB,
   scrape the root page into cache and `parse` (see `rescrape_broken_roots.py` for
   the pattern), or run `backfill_missing_works.py`.
3. `streamfinder` export → add it as a canary in `check_completeness.py`.
