# Update architecture — keeping the catalog fresh

> Design/reference doc. **No code yet** — this is the agreed plan for how the
> catalog gets refreshed over time. Companion to `csfd-scraping-rules.md`
> (which covers the one-shot harvest) and the `csfd-scraping` skill.

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

## New state we need to track

Columns that don't exist yet but are prerequisites for any of the above:

- `first_seen_at` — when we first harvested the title
- `last_scraped_at` — drives the manual-mode cadence rule
- `scrape_count` — diagnostics
- `rating_settled` (bool) — the hot→warm graduation flag
- an evergreen flag (or derive it on the fly from `episode_count` / `cadence_days`)

## Orchestration — manual / semi-manual (chosen)

We deliberately **do not** run a cron or a VPS. Playwright + bot protection in
GitHub Actions is fragile (CI IPs get blocked fast). Instead the whole thing is
**one command, run by hand** when the net is stable (roughly weekly):

```
python3 -m csfd_vod.main update
  ├─ discover   re-harvest last 2 months + running (non-evergreen) series
  ├─ refresh    priority queue, budget N titles (hot/young first)
  ├─ reconcile  mark delisted — ONLY if that month's harvest == complete
  ├─ enrich     TMDB for new / missing only
  └─ export     regenerate streamfinder/static/data/*.json
                (then a human does the commit + push → GH Pages deploy)
```

No cron, no VPS, no brittle CI Playwright. The operator decides *when*, which fits
the "on a train, intermittent net" workflow. This can be wrapped in a cron later
without changing the logic — the manual `update` command is the unit either way.

## Verification (same gates as a harvest)

- `python3 scripts/check_completeness.py` — canary titles + minimum work count must
  hold; it gates the deploy.
- Any new gap found becomes a new canary — executable knowledge doesn't rot.
- `cd streamfinder && npm run check && npm run build`.
