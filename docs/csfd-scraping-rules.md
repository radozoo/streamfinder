# CSFD scraping — rules & exceptions

The reference catalog of everything about scraping csfd.cz that is **not obvious
from any single file**. CSFD has an unusually high "surprise density" — bot
protection, phantom pagination, encoding quirks, real-but-placeholder-looking
data. Every rule below cost at least one debugging cycle to learn; each notes
**why** and **where it is enforced in code**.

The procedural companion is the `csfd-scraping` skill (`.claude/skills/`). When you
discover a new rule, add it here AND, if it is a completeness gap, add a canary to
`scripts/check_completeness.py` so it can't reopen unnoticed.

---

## 1. Bot protection — you must use Playwright

CSFD sits behind Anubis / BotStopper. Plain `requests` and the `WebFetch` tool both
get an **"Access Denied"** page (a sad Anubis mascot), not the content.

- Title pages: `VODScraper.scrape_title_details(url)` (Playwright, with UA rotation).
- Listing pages: `VODScraper._scrape_vod_list_playwright(url)`.
- Do **not** try `WebFetch`/`curl` on csfd.cz — they will silently return the block
  page. Use the scraper. (`WebSearch` against csfd.cz is fine for finding a URL.)

## 1b. Two harvest sources — dated feed vs. per-platform catalog

The monthly `/vod/?year=&month=` listing (§2) is a **dated feed**: it only surfaces
a title's *arrival* event, so a title that's on VOD but never had one — an older
catalog title with no dated "on VOD since" entry — is invisible to it. Confirmed
missing this way: **Dexter** (2006, root 224291, Prime Video/SkyShowtime) and
**Game of Thrones** ("Hra o trůny", root 263138, HBO Max/Prime/Lepší.TV) — both
rated, both genuinely on VOD, both absent from every monthly page we ever fetched.

`harvest-platforms` (`cmd_harvest_platforms` / `scrape_vod_platform_all_urls`)
covers this: each platform has a static browse listing at `/vod/{slug}/` (slugs:
`netflix`, `hbo-max`, `disney-plus`, `prime-video`, `sky-showtime`, `apple-tv`,
`oneplay`, `prima-plus`, plus ~18 smaller ones incl. several `youtube-*` and niche
services — `VODScraper.MAJOR_VOD_PLATFORMS` covers the 8 major ones) that lists
everything CURRENTLY available, dated or not. **Important distinction from the
base `/vod/` browse and its query-string facets (`?type=`, etc.):** those do NOT
clamp — paging past the end just keeps returning different content, so they can't
be harvested exhaustively or safely bounded. The per-platform PATH listing
(`/vod/{slug}/`) DOES clamp exactly like the monthly feed — verified empirically:
`/vod/netflix/?page=328` and `?page=329` both return the identical 16 items as
`?page=327`, which is also the paginator's own declared last page. So the same
real-vs-phantom pagination logic applies, and `incomplete_platforms` is the
per-platform analogue of `incomplete_months`.

Run `harvest-platforms` after (or alongside) a monthly `harvest` to catch this
class of gap; it unions into the same `vod_urls.json`, never removing entries.

## 2. Harvesting the /vod listing

Listing URL: `https://www.csfd.cz/vod/?year={y}&month={m}&range=month&page={p}`

- **The default listing already includes every type** — film, seriál, série,
  epizoda, pořad. No `films=`/`others=` filter params are needed (and adding them
  narrows to a subset). Verified: a single page mixes all five types.
- **Phantom paginator (critical).** Page 1 *always* links to a far page number
  (e.g. "20") regardless of the real page count. It is **not** the last page. A
  first completeness guard that trusted it produced 17 false positives.
- **Clamp = the real end signal.** Requesting a page past the end returns the *last
  real page's content* (not an empty page). So the true end of a month is a page
  whose item-set **repeats the previous page**. Stop there.
- **Global-`seen` trap.** `scrape_vod_all_urls` dedupes across all months with one
  global `seen` set. NEVER stop a month because a page had "no *new* URLs" — a
  single mid-month page of already-seen re-releases would truncate the rest of the
  month. This is the exact bug that dropped ~12k episode URLs and hid True Detective
  and Twin Peaks. Stop only on clamp (repeat) or a genuinely empty page.
- **HTML-encoded ampersands.** Pagination hrefs are `?...&amp;page=20` in the raw
  HTML. Parse them with BeautifulSoup (which decodes `&amp;`), not a raw-string
  regex — a `[?&]page=` regex misses the encoded `&` and under-reports.

Enforced in `src/csfd_vod/extraction/scraper.py`:
`scrape_vod_all_urls` (cache-aware loop + clamp/empty/cap termination),
`_extract_title_urls`, `_declared_last_page` (informational only — phantom).

**Completeness report.** `cmd_harvest` returns `complete` / `incomplete_months`. A
month is *healthy* when it ends on a clamp (or is empty at page 1 = a month with no
releases). An **empty page after real content** means a failed fetch mid-month
(CSFD clamps rather than returning empty at the true end) → reported incomplete.

**Cache-aware / resumable.** The harvest reuses already-downloaded page files and
only fetches what's missing, so a full re-harvest is cheap. Caveat: a *failed* fetch
can still write an error/empty page to cache; if a month looks wrong, delete its
`cache/vod_lists/{year}_{mm}_p*.html` and re-run. Also delete the current + previous
month before an update run — those listings still change.

## 3. URL hierarchy — work vs. release

- Top-level work: `/film/{id}-slug/prehled/`
- Child (season/episode): `/film/{root}-slug/{child}-slug/prehled/`
- `root_id` = first `/film/{id}` segment; `csfd_id` = last id before `/prehled`.
  `is_toplevel = (root_id == csfd_id)`.
- Segment regex that actually works (slug sits between id and slash, so a naive
  `(\d+)/(\d+)` never matches): `re.findall(r"/(\d+)-[^/]*(?=/)", url)` → first =
  root, last = csfd. The trailing lookahead `(?=/)` is required or it only matches
  the first segment.
- **Katalóg shows works only** (`is_toplevel`); episodes/seasons roll up under the
  serial. **Kalendár shows release events** (any level). A missing root referenced
  by children is backfilled by `scripts/backfill_missing_roots.py` /
  `backfill_missing_works.py`.

Enforced in `src/csfd_vod/transformation/parser.py`, `export/streamfinder_exporter.py`.

## 4. Genres — linked AND bare text

CSFD only hyperlinks genres that have a dedicated `/zanry/` page. **Secondary genres
are bare text nodes** in the `.genres` container — Mysteriózní, Rodinný, Stand-up,
Sportovní, Reality-TV, Hudební, Krátkometrážní, Talk-show, … A selector of
`.genres a` drops them (it lost ≥1 genre on 34% of titles). Iterate the container's
children, collect both `<a>` text and bare `NavigableString` text, skip the
`<span class="bullet">` separators. Enforced in `parser.py` (genre block).

## 5. VOD platforms

- **Selector:** `.film-vod-list .box-film-vod-services a` — the real service links
  only. Do **not** use `.film-vod-list a`: it also matches the section heading
  `<h3><a href="/vod/">VOD</a>` (which yields a bogus "VOD" platform — it was on
  1,107 titles) and the "více" toggle.
- **Distributor fallback:** platforms with no `/vod/` page (e.g. Paramount+) appear
  only as `Distributor: …` text. Use it, but denylist non-streaming distributors
  (theatrical/kino) — see `_NON_STREAMING_DISTRIBUTORS` in `list_parser.py`.
- **Re-streamer priority:** IPTV re-streamers (SledovaniTV, Lepší.TV, Telly) must
  rank *below* the majors that actually own the content (HBO Max, etc.). See
  `_PLATFORM_PRIORITY` / `_sort_platforms` in `streamfinder_exporter.py`.
- **Inheritance:** posterless / platformless episodes inherit poster + platforms
  from their serial (and serials inherit platforms from their children).
- **Note:** stored VOD urls are often tunefind tracking redirects, not direct
  service URLs — they still resolve, so this is cosmetic.

## 6. Loader must be idempotent

`postgres_loader._upsert_dimensions` **deletes a title's page-derived dimension rows,
then re-inserts** them (see `_REBUILT_DIMS`). Inserting with `ON CONFLICT DO NOTHING`
alone is a trap: a re-parse can then only ever *add*, so stale values survive forever
— seed placeholders and platforms no longer listed on the page. Delete + insert runs
in the same transaction as the fact upsert (atomic per title).

## 7. Don't assume placeholder-looking data is junk

`"Director X"` looks like a seed placeholder but is a **real director** (Julien
Christian Lutz — worked on *Mike*, *Cross*, *October Faction*). Always verify a
suspicious value against the freshly-scraped page before deleting it. (Genuine seed
junk from early dev — `"Director 1"`, `"Actor 1/2"`, and url-less `Netflix/Prime/VOD`
— did exist on title_ids 6–15 and was cleaned by the idempotent re-parse.)

## 8. Season / episode parsing

- `S(\d+)E(\d+)` in title → season_no / episode_no; else bare `\(E(\d+)\)`; else série
  season from the slug (`/\d+-(?:serie|season)-(\d+)`) or the title.
- Serial totals from the serial page headers: `Série (N)` / `Epizody (M)` →
  season_total / episode_total.

## 9. Environment / logging

- The working interpreter is **`python3`** (not `python`).
- `structlog` logs to **stdout**; it can't be silenced with `logging.disable`.
- CLI: `python3 -m csfd_vod.main <cmd>` — commands: `harvest`, `scrape`, `parse`,
  `run`, `enrich`, `streamfinder`, `dashboard`.
- Secrets: `.env` holds `TMDB_API_KEY`; it is gitignored — **never commit it**.
  `enrich` reads it (`export TMDB_API_KEY=$(grep ^TMDB_API_KEY= .env | cut -d= -f2)`).

## 10. Verifying completeness

- Frontend: `cd streamfinder && npm run check && npm run build`.
- Catalog canary: `python3 scripts/check_completeness.py` — known-VOD titles (True
  Detective, Twin Peaks, …) + a minimum work count must hold; exits non-zero to gate
  a deploy.
- After a harvest: check the returned `complete` / `incomplete_months`.
- **Rule of thumb:** every real gap you find becomes a new canary in
  `check_completeness.py`. Executable knowledge doesn't rot; prose does.

## 11. Slug drift → duplicate titles

ČSFD **renames a title's URL slug over time** while the numeric id stays fixed:

- a pre-air episode gets a placeholder slug that is later replaced with the real
  name — `…/1622613-episode-5/prehled/` → `…/1622613-pamet/prehled/`;
- a film's working/English slug flips to the Czech title —
  `…/1723354-the-miniature-wife/…` → `…/1723354-miniaturni-manzelka/…`.

Because `url_id` (the loader's conflict key) carries the slug, the new URL is a
**different key**, so the loader INSERTs a *second* row for the same `csfd_id`
instead of updating — and the title then renders **twice** in the catalog/calendar.
An `update` run surfaces this: discover re-harvests recent months, sees the new
slug, and adds the duplicate.

**Identity is `csfd_id`, not `url_id`.** Fixes, defence in depth:

- **Cleanup:** `scripts/dedupe_titles.py` collapses rows sharing a `csfd_id` (keep
  the richest — rated > unrated, more votes, has a date, real slug over a
  placeholder, newest as tiebreak) and drops non-overview junk rows
  (`/recenze/`, `?comment=` that were stored as titles). It also prunes the removed
  URLs from the HTML cache and `cache/vod_urls.json` so a re-parse can't resurrect
  them. Dry-run by default; `--apply` executes.
- **Self-heal:** `csfd_vod.main update` runs that dedupe automatically after
  parse/load, so the DB can't accumulate drift.
- **Export guard:** `StreamfinderExporter._load_titles` dedupes by `csfd_id` and
  filters non-overview URLs, so even a stray duplicate can never reach the site.
- Display name comes from the `title` column, **not** the slug — so keeping either
  row shows the correct name; the slug only affects the outbound ČSFD link.
