---
date: 2026-04-12
topic: streamfinder-dashboard
---

# Streamfinder — VOD Discovery Dashboard

## What We're Building

Interactive web app for browsing, searching, and exploring VOD titles available on Czech streaming platforms. Data sourced from CSFD.cz scraping pipeline (~6000+ titles, 11 VOD services). Deployed as a static site on GitHub Pages.

**Name:** Streamfinder
**Identity:** Hybrid "cinema archive" — dark-but-not-Netflix (deep navy + warm amber accent), film-feel typography (serif display + sans body), TMDB high-res posters and backdrops, subtle grain texture, slow easing animations.
**Language:** Czech (UI + data)
**Audience:** Personal sharing with friends/family + portfolio piece
**Tech stack:** SvelteKit (static adapter) + LayerCake/D3 for charts + TMDB API for imagery
**Hosting:** GitHub Pages (static export)
**Dark/Light mode:** Dark only
**Mobile:** Fully responsive

---

## Site Structure

```
Streamfinder   Katalog   Kalendář   Insights   [search icon]
     /         /katalog   /kalendar   /insights   /titul/{id}
```

### 1. Homepage (`/`)

**Hero (first viewport) — split layout:**
- **Left:** Featured title — largest poster (TMDB), title, rating, VOD badge, CTA "Detail". Selection: highest-rated title from past 21 days with rating >= 75, votes >= 500, TMDB backdrop available. Fallback: extend window to 45 days, then JSON override.
- **Right:** "Nedavno pribylo" — compact list of past 7-14 days grouped by date (count per day). Below: smaller "Brzy pribude" section with upcoming 1-2 weeks. Link to full calendar.

**Scroll sections below hero:**
- "Nove na VOD tento tyden" — horizontal poster row
- "Nejlepe hodnocene tento mesic" — horizontal poster row
- "Prochazej podle zanru" — genre tiles
- Quick stat teaser (headline numbers) → CTA to Insights

### 2. Katalog (`/katalog`)

**Layout:** Left sticky facet panel + right poster grid.

**Facet panel — pill-based filtering (RA Podcast style):**

| Facet | Type | Details |
|---|---|---|
| Zanry | color-coded pills | ~20-30 genres |
| Tagy | color-coded pills | atmospheric, psychological, etc. |
| VOD sluzby | branded pills | Netflix, HBO Max, Disney+, etc. |
| Zeme | pills | top 20 + "Dalsi..." |
| Typ | pills | film / serial / seria / epizoda (default: film) |
| Rok vydani | bucket pills | 2020s, 2010s, 2000s, 90s, starsi |
| Hodnoceni | bucket pills | Vyborne 85+, Velmi dobre 75-85, Dobre 60-75, Prumer <60 |
| Reziser | autocomplete text search → adds pill to active filters |
| Herci | autocomplete text search → adds pill to active filters |

**Active filters** shown as removable chips above poster grid.
**Progressive filtering:** pills that yield 0 results get disabled/dimmed.
**Poster grid:** poster + title + rating + VOD badge. Click → modal overlay with detail.

### 3. Kalendar (`/kalendar`)

**Format:** Hybrid filmstrip — horizontal timeline, past-dominant.

**Primary zone (above "DNES" anchor):** Past 3-4 weeks as full filmstrip. Each day is a column. Primary title per day (highest rated) gets large poster + plot snippet + metadata. Secondary titles shown as smaller tiles below. Horizontally scrollable deeper into history (lazy-load by week).

**"DNES" anchor:** Visually prominent amber horizontal line with date label.

**Secondary zone (below anchor):** "Brzy pribude" — compact horizontal row of smaller tiles for upcoming 2-3 weeks.

**Quick time links:** Dnes / Tento tyden / Minuly tyden / Tento mesic / Minuly mesic

**Filters:** VOD service, title type (film/serial), genre.

### 4. Insights (`/insights`)

**Scrollable page, each chart is a section.**

**Must-have (v1):**
- Headline numbers (count-up animation): total titles, services, genres, % films, avg rating
- Bar chart: title count per VOD service (horizontal, sorted)
- Scatter plot with switchable dimensions: avg rating × title count, toggle between VOD services / countries / genres / directors. Bubble size = total votes.
- "Hidden gems" quadrant: votes (popularity) × rating (quality), 4 quadrants labeled (Mainstream hit / Hidden gem / Guilty pleasure / Skip). Clickable dots → title detail.

**Nice-to-have (v2):**
- Rating distribution per VOD service (violin/histogram)
- Timeline: new titles per month (stacked area by service)
- Treemap: genres sized by count, colored by avg rating
- Heatmap: genre × VOD service
- World map: countries colored by title count

### 5. Title Detail (`/titul/{id}`)

**Hybrid approach:** Opens as modal overlay in Katalog/Kalendar (preserves browse context). Also exists as full page for sharing/direct URL. Modal has "Otevrit stranku titulu" button.

**Layout (full page):**
```
[TMDB BACKDROP — wide, blurred edges]
  [POSTER]  Title CZ
            Title EN (year)
            ★ rating • votes hlasu • type
            runtime • age rating
            [genre pills]
            Kde sledovat:
            [▶ Netflix od 1.4.] [▶ HBO od 15.6.]  ← clickable, opens platform URL

[Plot / Obsah]

[▶ TRAILER — YouTube embed]

[Tvurci: Rezie / Scenar / Kamera / Hudba]
[Herci]
[Zeme]
[Tagy — pills]

[Recenze — TOP 3 only, no "show more"]
  ★★★★★ "text..." — author
  ★★★★  "text..." — author
  ★★★   "text..." — author

[← Zpet]                    [Otevrit na CSFD ↗]
```

---

## Schema Changes Required

### New fields to scrape (parser additions):
- `runtime_min` INTEGER — film duration in minutes
- `votes_count` INTEGER — number of CSFD ratings
- `trailer_url` VARCHAR(500) — YouTube trailer URL
- `age_rating` VARCHAR(20) — age restriction (e.g., "od 15 let")

### Schema refactors:
1. **dim_vods** — add `vod_date DATE` (per-platform release date, moved from fact_titles) and `vod_url VARCHAR(500)` (direct link to watch on platform)
2. **fact_titles** — drop `vod_date` after migration to dim_vods (keep `date_added` for pipeline metadata)

### New enrichment step:
- TMDB API integration: for each title, search TMDB by title+year, store `tmdb_id`, `poster_path`, `backdrop_path`, `trailer_youtube_id`
- Fallback: if TMDB not found, use CSFD `image_url`
- Requires free TMDB API key

---

## Key Design Decisions

- **Past-dominant calendar:** VOD content is actionable NOW (you can watch it), so past releases are primary, future releases are secondary teaser
- **Featured title = quality gate:** rating >= 75, votes >= 500, past 21 days. Never show low-rated content in hero.
- **Pill-based faceted search:** intuitive click-to-filter interaction, progressive narrowing, inspired by RA Podcast Mixes genre browser
- **TMDB for visuals, CSFD for data:** CSFD posters are low-res (~300px). TMDB provides 4K posters + backdrops + trailers. Hybrid approach gives portfolio-grade visuals with rich Czech-specific data.
- **Top 3 reviews only:** no "show more" — keeps detail page clean. Full reviews on CSFD link.
- **Svelte over React:** lighter bundle, built-in transitions for cinema-feel, LayerCake for editorial data-viz style
- **Dark only:** cinema = darkness. No light mode toggle.
- **VOD platform links:** direct "watch now" URLs from CSFD → one click from discovery to watching

---

## Open Questions

- Exact color palette (deep navy base, amber accent — specific hex TBD during implementation)
- Typography pairing (serif display + sans body — specific fonts TBD)
- Logo design (stylized lens / play button?)
- Poster grid density (how many columns on desktop/tablet/mobile)
- Calendar: exact scroll/snap behavior for horizontal filmstrip
- Insights v2 chart prioritization order

## Next Steps

→ `/cde:plan` for implementation details (component structure, data pipeline, build/deploy)
