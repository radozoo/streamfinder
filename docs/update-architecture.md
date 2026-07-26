# Update architecture — keeping the catalog fresh

> Companion to `csfd-scraping-rules.md` (the one-shot harvest) and the
> `csfd-scraping` skill.
>
> **Status:** the core is implemented as `python3 -m csfd_vod.main update`
> (discover + refresh + parse + enrich + export, plus bad-page overwrite
> protection in the loader). Still **deferred**: delisting reconciliation,
> dedicated state columns, and DB-level evergreen freezing — see *Deferred* at
> the end. The design below is the full picture; the "Orchestration" section
> documents what the command actually does today.

## The core problem

A full re-scrape of the whole catalog every night is not realistic: it is a large
number of Playwright-rendered pages behind bot protection (see rules doc §1), and
hammering csfd.cz risks a ban. So "update" is **not one job** — it is three jobs
with very different cost and cadence. Treat them separately.

## Three streams

### 1. Discover — what newly hit VOD  *(cheap, always forward-looking)*
Re-harvest of the `/vod` listing. New titles are always on the first pages / in the
most recent months, so we only re-harvest the **last ~2 months**, not the whole
back-catalog — a few dozen listing pages. This is the *only* way we learn a title
exists, so it runs every update. Cheap.

### 2. Refresh — existing titles maturing  *(expensive, budget-capped)*
A fresh release has no rating and few votes; those mature over weeks. This is a
re-scrape of already-known **detail** pages. Expensive (Playwright), so it is
strictly budget-constrained (see below).

### 3. Running series — new episodes  *(medium, but beware evergreens)*
While a series is `is_running`, new episodes keep appearing (and become Kalendár
events). This needs periodic re-harvest of the series — **except evergreen soaps**,
which are firehoses and get frozen (see below).

## Freshness-decay tiering

Rating/votes settle over time; an old title effectively never changes. Tier the
refresh cadence by age since VOD release:

| Age since VOD release | Why | Cadence (daily-cron terms) |
|---|---|---|
| 0–30 days | rating volatile, few votes | every 2–3 days |
| 1–6 months | still settling | weekly |
| 6–24 months | rarely changes | monthly |
| > 2 years | frozen | never (yearly sweep at most) |

A title **graduates** from hot → warm once it has enough votes + age
(`rating_settled`), which shrinks the queue over time. Without graduation the
refresh queue grows without bound.

> **Manual-mode adjustment.** We run manually (see Orchestration), typically weekly,
> not on a daily cron. So the cadence collapses to a rule on `last_scraped_at`:
> young titles (0–30d) refresh on *every* run; older tiers are skipped unless their
> `last_scraped_at` is older than the tier's interval. Same logic, just event-driven.

## Budget-constrained refresh

Because Playwright is slow and ban-prone, refresh is a **priority queue with a
per-run budget** (e.g. N=300 pages). Score ≈ `staleness × volatility`
(age, whether it still lacks a rating, whether it is running). Each run takes the
top-N; slower/older titles wait for a future run. This bounds server load no matter
how big the catalog gets.

## Evergreen serials — cut the firehose

Not all `is_running` series are equal:

- **Prestige / limited** (True Detective S4, Yellowjackets) — a new episode is
  *signal*. Track it; people search for it.
- **Endless telenovela** (Ružová zahrada, Ordinace, Polabí — 40+ episodes/year,
  running for years) — a new episode is *noise*. It floods Kalendár, burns refresh
  budget, and nobody searches by individual episode.

Distinguish them **cheaply, from data we already have** (no extra scrape):

| Signal | Prestige | Evergreen |
|---|---|---|
| `episode_count` | tens | hundreds |
| `cadence_days` | a week+ | daily / 2–3 days |
| run length | 1–3 seasons | years |
| genre | drama/crime | "telenovela" / "soap" (CSFD tags these) |

**Rule:** once a series crosses the threshold (e.g. `episode_count > 60`, or daily
cadence while running > 2 years) it flips to an **evergreen** state:

- ✅ stays in the catalog as a work (card shows "running, 800+ episodes")
- ❌ **stops** emitting per-episode Kalendár events
- ❌ **stops** being refreshed (rating settled long ago)
- 🔄 at most an occasional cheap aggregate check (episode count), never per-episode

This keeps the refresh queue small and Kalendár readable — Kalendár should show
"a new film / a new prestige season dropped", not "Ordinace episode 2384".

## Things that WILL bite you (beyond the obvious)

These matter more than the scheduling itself:

- **🔴 Delisting (a title leaves VOD).** If you only ever *add*, you never notice a
  title was **removed** from a platform — this is exactly what happened to True
  Detective. Needs **reconciliation**: what was in a month's previous harvest and is
  now absent may be delisted. **Guard hard against incomplete harvests** — the
  phantom paginator / a truncated harvest would otherwise wipe half the catalog.
  Only reconcile-delete when the harvest for that month came back `complete` (see
  rules doc §2 and the completeness invariant).

- **🔴 Bad page overwriting good data.** When bot protection returns a challenge
  page, the parser gets garbage and rating comes back `null`. A blind upsert then
  **overwrites a good rating with null**. Rule: on re-scrape, a field may only be
  overwritten if the new value is not "suspiciously empty" (e.g. never replace a
  present rating with null — keep the old value and log it).

- **Series-stopped detection.** `is_running` must be able to flip to false (no new
  episode for N days), or the hot queue runs forever.

- **Slug/URL changes.** csfd.cz `csfd_id` is stable; the slug is not. Key everything
  on id, never on the URL string.

- **rating null→value is the signal** to keep a title hot; after it appears, demote.

- **Politeness / anti-ban.** Jitter between requests, spread load, no bursts.

- **TMDB re-enrich only for what's missing** — never pull TMDB for everything each
  run; only new roots and titles lacking a poster/trailer.

## State signals

The refresh queue currently derives "hot" from existing columns — no new schema:

- `vod_date` — age tier (young ⇒ hot)
- `rating IS NULL` — never got a rating yet ⇒ hot, prioritised first
- `scraped_at` — staleness tiebreak (stalest re-scraped first), so successive
  runs rotate through the queue

Future refinement (deferred) would add dedicated columns for richer policy:
`first_seen_at`, `last_scraped_at` (distinct from parse time), `scrape_count`,
`rating_settled` (explicit hot→warm graduation), and an evergreen flag.

## Orchestration — manual / semi-manual (chosen)

We deliberately **do not** run a cron or a VPS. Playwright + bot protection in
GitHub Actions is fragile (CI IPs get blocked fast). Instead the whole thing is
**one command, run by hand** when the net is stable (roughly weekly):

```
python3 -m csfd_vod.main update
  ├─ discover   re-harvest the last N months (--discover-months, default 2) with a
  │             FORCED refetch of those months, union new URLs into vod_urls.json,
  │             download only the new title pages. New episodes of running series
  │             show up here as new listing URLs — no per-series crawl needed.
  ├─ refresh    budget-capped re-scrape of hot titles (--refresh-budget, default
  │             200; --refresh-max-age-days, default 180). A re-scrape that comes
  │             back as a challenge page (parses to no title) is REJECTED and the
  │             good cached copy is kept.
  ├─ parse      re-parse the whole cache → load (idempotent; loader COALESCEs
  │             volatile fields so a bad page can never erase a good rating/poster)
  ├─ enrich     TMDB for missing only  (--skip-enrich to skip)
  └─ export     regenerate streamfinder/static/data/*.json  (--skip-export to skip)
                → then a human runs the gate, commits, and pushes → GH Pages deploy
```

Flags: `--skip-discover`, `--skip-refresh`, `--skip-enrich`, `--skip-export`, and
`--dry-run` (discover + refresh into cache only, no DB/enrich/export). The command
**never commits or pushes** — the operator reviews and does that. It fits the
"on a train, intermittent net" workflow; wrap it in cron later without logic change.

## Deferred (not in the command yet)

- **Delisting reconciliation.** Needs per-month URL snapshots + a `complete`-harvest
  guard before it may delete anything (else the phantom paginator wipes the catalog).
  Until then a title that leaves VOD lingers; re-add detection is manual.
- **Dedicated state columns** (see *State signals*) for richer refresh policy.
- **DB-level evergreen freezing.** Today soaps fall out of refresh naturally (old +
  well-voted). An explicit frozen state (stop episode events, stop refresh) is a
  frontend/export concern still to be wired.

## Verification (same gates as a harvest)

- `python3 scripts/check_completeness.py` — canary titles + minimum work count must
  hold; it gates the deploy. `update` prints a reminder to run it.
- Any new gap found becomes a new canary — executable knowledge doesn't rot.
- `cd streamfinder && npm run check && npm run build`.
