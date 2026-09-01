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
- **One link can hold two services.** A few `<a>`s wrap a pair across several
  lines (`"Peacock /\n\t\t\tHulu"`). Collapse the whitespace and split on `/`, or
  the blob becomes a third bogus platform that matches no alias and no brand
  colour. No legitimate platform name contains a slash — verified against the
  full `dim_vods` set.
- **The same service appears under several names** (`HBO Max`/`Max`,
  `Voyo`/`Oneplay`), which silently splits one platform into two filters.
  Canonicalise in `_PLATFORM_ALIASES` (exporter). `check_data_quality.py` flags
  new near-duplicate spellings; genuinely distinct look-alikes (`Apple TV` vs
  `Apple TV+`, the YouTube tiers) are listed in its `CONFIRMED_DISTINCT`.

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

---

## 12. A work and its episodes are two /vod rows — merge them, don't pick one

ČSFD lists a serial and each of its episodes separately, and **neither row is
reliably the complete one**. The episode's row usually comes from the /vod feed that
announced the release and names the service it premiered on; the serial's own page
often lists whoever resells the whole show, which in Czechia is frequently an IPTV
reseller (Lepší.TV, SledovaniTV, Telly, Oneplay).

The exporter used to prefer the serial and discard the episode's own platform, on
the theory that an episode's entry "is often just an IPTV reseller". It is
**frequently the reverse**:

| title | the episode says | the serial says |
|---|---|---|
| Klara S02E01 | HBO Max | Lepší.TV |
| Star Trek: Lower Decks S04E08 | Paramount+ | Prime Video, SkyShowtime |
| The Walking Dead: Dead City S03E03 | AMC+ | Telly |
| Trollové — Série 1 | Netflix | SledovaniTV |

That cost **1,181 episodes** a platform they are actually on, and hid one from
**443 serials** that their own episodes carry.

**Rule: merge both directions, never replace.** `_merge_vods` unions the two lists
and `_sort_platforms` decides what leads — the priority table already ranks real
services above resellers, so the primary is what the "Sledovat na …" button offers.
The merge is purely additive: it introduced **no platform name that was not already
in the catalog**, and removed nothing.

Note that an episode page frequently has **no `.film-vod-list` box at all** (Klara's
has none). Its platform comes from the /vod listing via `list_merge`, including the
distributor fallback — which is why §5's "the listing is authoritative for
serials/episodes" matters here too.

### 12b. Facet counts must be computed from the exported index

Because platforms are merged on the way into `titles_index.json`, counting them from
the dimension tables gave a pill that disagreed with its own result set — "Lepší.TV
3 758" opening 6,377 titles, with 52 of 69 platforms off. `_build_dimensions` now
counts from the built index, which is what the filters match against.
`scripts/check_completeness.py` asserts it on the shipped artifact, because nothing
about the site looks wrong when it drifts.

## 13. Alternative names — the first one is NOT the English one

`.film-header-name .film-names` lists a title under every country/language it was
released in, one `<li>` per release, nearly all of them hidden behind a "více"
toggle. The order is country-of-origin first:

```
Jižní Korea | Ojingeo geim      ← <li> #1, the only one the parser used to keep
Jižní Korea | 오징어 게임
Kanada      | Squid Game        ← what a user actually types
USA         | Squid Game
```

So `title_en` is the **origin** name, not the English name. Keeping only `<li>` #1
stored "Ojingeo geim" for Hra na oliheň, "Sen to Čihiro no kamikakuši" for Cesta do
fantazie and the Slovak "Parazit" for Parazit — and since search matched
`title` + `title_en` only, "Squid Game", "Spirited Away" and "Parasite" all returned
nothing. On a 600-title sample, **30% of titles carry an English-flagged name that is
not the one kept**, and 6% led with a non-Latin script.

Rules:

- Collect **every** `<li>`, not the first. Filter out the `<a>` toggle text
  ("více"/"méně" — `get_text` drags it in) and dedupe: the same string under five
  flags is one name. Stored in `fact_titles.alt_titles` (TEXT[]), `alt_titles[1]`
  being `title_en`.
- `title_en` keeps its meaning (origin name): the detail page shows it under the
  Czech title and the TMDB enricher matches it as the original title. Search is what
  reads the full array.
- The exporter ships only the names that add a new string (`_search_names` drops
  anything folding to `title`/`title_en`) — ~0.6 per title, ~0.7 MB on a 33 MB index.
- **Season and episode pages carry no `.film-names` at all.** `alt_titles` stays
  NULL there (the loader COALESCEs it, so a bad page can't erase a good list), and
  the frontend's `buildSearchIndex` lets a release inherit its serial's names —
  otherwise "squid game" finds the serial but not its Série 3 release in the Kalendár.
- Folding is duplicated in three places on purpose (`streamfinder/src/lib/search.ts`,
  the exporter, `check_completeness.py`): NFD-decompose, drop combining marks,
  lowercase. Keep them identical or the canary stops testing what the site does.

## 14. The bot check is a WAIT, not a failure — and no network is not a slow site

Two ways the scrape wastes a whole day, both fixed at one place each in
`extraction/scraper.py`.

### 14a. Anubis needs a few seconds; five was not enough

ČSFD fronts the site with Anubis. Its interstitial is a ~7 KB page that computes a
proof-of-work in the browser and *then* redirects itself to the page you asked for.
Every asset it loads sits under `.within.website/x/cmd/anubis`, which is the marker to
test for (`_is_challenge_page`).

The Playwright path waited 5 s for `.film-header h1` and treated a miss as a dead
page. But the challenge takes longer than that: on 2026-09-01, **126 of 154 selector
misses were a plain timeout with no navigation pending** — the challenge sitting there
computing while we walked away from it. The caller then launched a whole new browser
and met the same wall: **2.09 navigations per title at ~21 s each**, against 1.00 at
3.5 s on a healthy day. 146 of 200 titles done when the run was killed.

So `_await_selector_through_challenge` keeps the 5 s wait for the ordinary page and,
when the page in hand IS the challenge, waits it out (20 s). Both Playwright paths use
it — titles and listings.

**Corollary:** the plain-HTTP fallback can never pass a proof-of-work, having no JS.
Once it has been served the interstitial it will be served it for the rest of the run,
so `_plain_http_challenged` retires it and the retry goes straight back to the browser
— 157 pointless round trips for 146 titles on that same run.

**When measuring, count `playwright_navigate_title_start` per `cache_saved`.** 1.00 is
healthy, 2.00 means the challenge is being paid for twice. The rate is intermittent and
ČSFD's, not ours: 1.00 for all of 9.–20. 8., 1.85–2.07 on 21.–22. 8., back to 1.06 on
30. 8., 2.09 on 1. 9.

### 14b. A DNS failure must abort, not retry

`NetworkUnavailable` is raised as soon as an error means "there is no network"
(`ERR_INTERNET_DISCONNECTED`, `ERR_NAME_NOT_RESOLVED`, urllib3's `NameResolutionError`,
…) — confirmed by a DNS probe first, three tries over ~30 s, so a Wi-Fi handover does
not abort a healthy run. Deliberately narrow: a connection reset, a timeout or a 429 is
what a loaded site or a bot check looks like, and those keep their retries.

Why: the 08:00 trigger wakes a laptop whose lid has been shut since the night, and on
battery `caffeinate -s` cannot hold it awake — clamshell sleep wins, so the run gets
DarkWake bursts with no network. On 2026-09-01 the retry ladders ground three months of
listing pages through DNS failures for **2 h 16 min** (a single attempt took 17
minutes), reported every month as `fetch_failed`, and by the time the lid was opened
the awake budget was gone. Failing in seconds leaves the whole day for the next try.

`csfd_vod.main` maps it to **exit code 3**, and `refresh.sh` treats 3 the way it treats
a laptop that slept: `skipped`, quiet, retried at the next trigger. It is not a fault
to wake a human for — it is the wrong moment.
