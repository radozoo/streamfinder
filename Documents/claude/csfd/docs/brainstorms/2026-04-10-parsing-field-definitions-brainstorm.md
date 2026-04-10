---
date: 2026-04-10
topic: parsing-field-definitions
---

# Parsing Field Definitions & Strategy

## What We're Building

A comprehensive parser for two HTML source types (VOD list pages + film detail pages) that extracts all relevant metadata and handles the full CSFD title hierarchy (film, serial, seria, epizoda).

## HTML Sources

| Source | Location | Contains |
|--------|----------|----------|
| List pages | `cache/vod_lists/{year}_{month}_p{page}.html` | vod_date, type, distributor, title, film URL |
| Detail pages | `cache/html/{md5}.html` | title, year, country, genres, directors, actors, plot, rating, reviews, tags, image, vod_platforms, premiere dates |

## Field List (Final)

### From Detail Pages

| Field | Source Element | Notes |
|-------|---------------|-------|
| `title` | `.film-header h1` | Czech title |
| `title_en` | detail page | English/original title if present |
| `year` | `.origin` regex | Production year |
| `country` | `.origin` text before `(` | Country of origin |
| `genres` | `.genres a` | Comma-separated |
| `director` | `h4 "Rezie:"` parent `a` | Filter "vice" links |
| `script` | `h4 "Scenar:"` parent `a` | Screenwriter(s) |
| `camera` | `h4 "Kamera:"` parent `a` | Cinematographer(s) |
| `music` | `h4 "Hudba:"` parent `a` | Composer(s) |
| `actors` | `h4 "Hraji:"` parent `a` | Filter "vice" links |
| `plot` | TBD selector | Film synopsis/description |
| `rating` | TBD selector | CSFD percentage rating |
| `reviews` | TBD selector | First 3 reviews (text + author) |
| `tags` | TBD selector | User tags, not present on all titles |
| `image_url` | TBD selector | Poster/cover image URL |
| `vod_platforms` | `.film-vod-list a` | Filter "vice" and empty |
| `premiere_detail` | TBD selector | Premiere date from detail page |
| `link` | URL | Full CSFD URL |
| `scraped_at` | timestamp | When HTML was downloaded |

### From List Pages

| Field | Source Element | Notes |
|-------|---------------|-------|
| `vod_date` | `.date-title` text | "V nabidce od {datum}" — VOD availability date |
| `type` | `.film-title-info .info:nth-of-type(2)` | "epizoda" or absent (= film/serial) |
| `distributor` | `p:-soup-contains("Distributor:")` | Platform that listed the title |
| `film_url` | `.article-img a[href]` | Links list entry to detail page |

## Title Hierarchy

CSFD has 4 title types:

```
Film            /film/12345-nazov/prehled/
Serial          /film/12345-nazov/prehled/       (same URL pattern as film)
Seria (season)  /film/12345/67890-seria-1/prehled/   (child URL)
Epizoda         /film/12345/67890-s01e01/prehled/    (child URL)
```

### Key Decisions

- **Include all types** (B) — films, serials, seasons, episodes
- **URL filter must be expanded** — current `_TITLE_OVERVIEW_RE` rejects child URLs
- **Parent-child via URL parsing + detail page verification** (C):
  - URL `/film/12345/67890-...` -> parent ID = 12345
  - Verify against detail page link to parent (if exists)
- Fields per type: `type`, `season_number`, `episode_number`, `parent_url`

## Temporal Snapshot

- Rating and reviews are **snapshots** at scraping time (B)
- Each record stores `scraped_at` timestamp for context
- Allows future re-scraping for updated ratings

## Parsing Validation Strategy

Random sample to verify selectors work across years (CSFD may have changed HTML structure):

- ~10 detail pages spread evenly across 2015-2026
- ~5 list pages from different years
- Targeted: 1 film, 1 serial, 1 episode (different types)
- Manually verify all selectors produce correct output
- Fix any year-specific selector variations

## Open Questions

- Exact selectors for: `title_en`, `plot`, `rating`, `reviews`, `tags`, `image_url`, `premiere_detail` — need HTML inspection
- How to distinguish film vs serial on detail page (both use same URL pattern)
- Whether list page HTML structure changed between 2015 and 2026

## Next Steps

-> `/cde:plan` for implementation (parser rewrite + expanded harvesting + sample validation)
