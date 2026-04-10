---
title: "feat: Parser Rewrite with Full Field Extraction"
type: feat
status: completed
date: 2026-04-10
origin: docs/brainstorms/2026-04-10-parsing-field-definitions-brainstorm.md
---

# feat: Parser Rewrite with Full Field Extraction

## Overview

Rewrite the VOD title parser to extract all 22 fields (18 from detail pages + 4 from list pages), support all CSFD title types (film, serial, seria, epizoda), and update the DB schema + loader accordingly. Validate selectors against a random sample of cached HTML spanning 2015-2026.

## Problem Statement / Motivation

The current parser extracts only 8 fields (title, year, country, genres, director, actors, vod_platforms, link). The cached HTML contains significantly more metadata valuable for the dashboard: rating, plot, reviews, tags, poster image, crew (script/camera/music), English title, VOD premiere dates, and title type. List pages (840 cached) contain vod_date, distributor, and type info not available on detail pages.

Additionally, the URL filter (`_TITLE_OVERVIEW_RE`) rejects child URLs for seasons and episodes, discarding valid title types that appear in VOD listings.

## Proposed Solution

Three-phase implementation:

1. **Schema + Model** -- add new columns/tables to match full field list
2. **Parser rewrite** -- detail page parser + new list page parser
3. **Integration + Validation** -- expand URL filter, wire list page data, validate on sample

(see brainstorm: `docs/brainstorms/2026-04-10-parsing-field-definitions-brainstorm.md`)

## Technical Approach

### Verified Selectors (from HTML inspection of cached files)

| Field | Selector / Method | Verified |
|-------|-------------------|----------|
| `title` | `.film-header h1` | yes |
| `title_en` | `.film-header-name .film-names li` (first `<li>`) | yes |
| `year` | regex `(19\|20)\d{2}` on `.origin` text | yes |
| `country` | `.origin` text before first digit | yes |
| `genres` | `.genres a` | yes |
| `director` | `<h4>Rezie:</h4>` parent `<a>`, filter "vice" | yes |
| `script` | `<h4>Scenar:</h4>` parent `<a>`, filter "vice" | yes |
| `camera` | `<h4>Kamera:</h4>` parent `<a>`, filter "vice" | yes |
| `music` | `<h4>Hudba:</h4>` parent `<a>`, filter "vice" | yes |
| `actors` | `<h4>Hraji:</h4>` parent `<a>`, filter "vice" | yes |
| `plot` | `.plot-full` text (fallback `.body--plots`) | yes |
| `rating` | `.film-rating-average` text, parse int (NULL if "? %") | yes |
| `reviews` | `article.article-review` -- author: `a.user-title-name`, text: first `<p>` > 20 chars, stars: `.stars` class suffix | yes |
| `tags` | `.box-tags a` | yes |
| `image_url` | `img[src*="/film/posters/"]` src attr | yes |
| `vod_platforms` | `.film-vod-list a`, filter "vice" and empty | yes |
| `premiere_detail` | `.updated-box-content-padding` -- parse "Na VOD od{date}" | yes |
| `type` | `.film-header-name .type` span text (e.g. "(serial)") | yes |
| `scraped_at` | file mtime or current timestamp | n/a |

**List page selectors (confirmed same structure 2015-2026):**

| Field | Selector / Method |
|-------|-------------------|
| `vod_date` | `.date-title` text, parse "V nabidce od {DD.MM.YYYY}" |
| `list_type` | `.film-title-info .info` -- second `.info` element text ("epizoda", "serial") |
| `distributor` | `p` containing "Distributor:" -- text after colon |
| `film_url` | `.article-img a[href]` -- relative URL |

### Title Hierarchy & URL Filter

Current `_TITLE_OVERVIEW_RE` only matches `/film/\d+[^/]*/prehled/$`. Must expand to include child URLs:

```
/film/\d+[^/]*/prehled/$                        # film or serial
/film/\d+/\d+[^/]*/prehled/$                     # seria or epizoda
```

Parent-child resolution (see brainstorm decision C):
- Parse parent_id from URL: `/film/{parent_id}/{child_id}-...` -> `parent_id`
- Store as `parent_url` (reconstructed) in fact_titles
- Detail page `.type` span distinguishes film vs serial at the parent level

### Implementation Phases

#### Phase 1: Schema + Model Updates

**Files:** `db/schema.sql`, `src/csfd_vod/transformation/models.py`

**`db/schema.sql`** -- add columns to `fact_titles`:

```sql
-- New columns on fact_titles
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS title_en VARCHAR(500);
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS plot TEXT;
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS rating INTEGER;          -- 0-100 or NULL
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS image_url VARCHAR(500);
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS title_type VARCHAR(20);  -- 'film', 'serial', 'seria', 'epizoda'
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS parent_url VARCHAR(500); -- NULL for films/serials
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS vod_date DATE;           -- from list page
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS distributor VARCHAR(100); -- from list page
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS premiere_detail TEXT;     -- raw "Na VOD od..." text
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS reviews JSONB;            -- [{author, text, stars}]
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS scraped_at TIMESTAMP;
```

**New dimension tables:**

```sql
-- Dimension table: Tags
CREATE TABLE IF NOT EXISTS csfd_vod.dim_tags (
    tag_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    tag VARCHAR(100) NOT NULL,
    UNIQUE(title_id, tag)
);

-- Dimension tables: Script, Camera, Music (same pattern as directors)
CREATE TABLE IF NOT EXISTS csfd_vod.dim_screenwriters (...);
CREATE TABLE IF NOT EXISTS csfd_vod.dim_cinematographers (...);
CREATE TABLE IF NOT EXISTS csfd_vod.dim_composers (...);
```

**`models.py`** -- extend `VODTitle`:

```python
class VODTitle(BaseModel):
    # Existing
    url_id: str
    title: str
    year: Optional[int] = None
    director: Optional[str] = None
    actors: Optional[str] = None
    genres: Optional[str] = None
    countries: Optional[str] = None
    vod_platforms: Optional[str] = None
    link: str
    date_added: datetime

    # New fields
    title_en: Optional[str] = None
    plot: Optional[str] = None
    rating: Optional[int] = None           # 0-100, NULL if unrated
    image_url: Optional[str] = None
    title_type: Optional[str] = None       # 'film', 'serial', 'seria', 'epizoda'
    parent_url: Optional[str] = None
    script: Optional[str] = None           # comma-separated
    camera: Optional[str] = None           # comma-separated
    music: Optional[str] = None            # comma-separated
    tags: Optional[str] = None             # comma-separated
    reviews: Optional[str] = None          # JSON string [{author, text, stars}]
    vod_date: Optional[date] = None        # from list page
    distributor: Optional[str] = None      # from list page
    premiere_detail: Optional[str] = None
    scraped_at: Optional[datetime] = None
```

#### Phase 2: Parser Rewrite

**Files:** `src/csfd_vod/transformation/parser.py` (rewrite `_extract_fields`), new `src/csfd_vod/transformation/list_parser.py`

**Detail page parser** -- extend `_extract_fields()` with new extraction for each field. Pattern for crew fields (script/camera/music) is identical to existing director/actors:

```python
def _extract_crew(self, soup, label):
    """Extract crew names by h4 label (e.g. 'Scenar:', 'Kamera:', 'Hudba:')."""
    h4 = soup.find("h4", string=label)
    if h4:
        names = [a.get_text(strip=True) for a in h4.parent.select("a")
                 if a.get_text(strip=True).lower() != "vice"]
        return ", ".join(names) if names else None
    return None
```

**Rating extraction:**

```python
rating_elem = soup.select_one(".film-rating-average")
if rating_elem:
    rating_text = rating_elem.get_text(strip=True)
    match = re.match(r"(\d+)%", rating_text)
    if match:
        data["rating"] = int(match.group(1))
```

**Title type + parent_url from URL parsing:**

```python
# Type from detail page header
type_span = soup.select_one(".film-header-name .type")
if type_span:
    type_text = type_span.get_text(strip=True).strip("()")
    # "serial" -> "serial", "seria" not expected on detail page
    data["title_type"] = type_text

# Parent-child from URL pattern
child_match = re.match(r"https://www\.csfd\.cz/film/(\d+)/(\d+)", url)
if child_match:
    parent_id = child_match.group(1)
    data["parent_url"] = f"https://www.csfd.cz/film/{parent_id}/prehled/"
    if not data.get("title_type"):
        data["title_type"] = "epizoda"  # child URL without type = episode
```

**Reviews (first 3, as JSON):**

```python
import json

review_articles = soup.select("article.article-review")[:3]
reviews = []
for rev in review_articles:
    author_el = rev.select_one("a.user-title-name")
    text_el = next((p for p in rev.select("p") if len(p.get_text(strip=True)) > 20), None)
    stars_el = rev.select_one(".stars")
    reviews.append({
        "author": author_el.get_text(strip=True) if author_el else None,
        "text": text_el.get_text(strip=True) if text_el else None,
        "stars": int(stars_el["class"][-1].split("-")[-1]) if stars_el and len(stars_el.get("class", [])) > 1 else None,
    })
if reviews:
    data["reviews"] = json.dumps(reviews, ensure_ascii=False)
```

**New list page parser** (`list_parser.py`):

```python
class VODListParser:
    """Parse VOD list pages for vod_date, type, distributor per film URL."""

    def parse(self, html: str) -> List[dict]:
        """Return list of {film_url, vod_date, list_type, distributor}."""
        soup = BeautifulSoup(html, "html.parser")
        results = []
        current_date = None

        for elem in soup.select(".date-title, article.article"):
            if "date-title" in elem.get("class", []):
                # Parse "V nabidce od DD.MM.YYYY"
                current_date = self._parse_vod_date(elem.get_text(strip=True))
            else:
                entry = self._parse_article(elem)
                entry["vod_date"] = current_date
                results.append(entry)

        return results
```

#### Phase 3: Integration + Validation

**Files:** `src/csfd_vod/extraction/scraper.py` (URL filter), `src/csfd_vod/loading/postgres_loader.py` (new columns + dimensions), `src/csfd_vod/main.py` (wire list parser into `cmd_parse`), `tests/test_parser.py`

1. **Expand URL filter** in `scraper.py`:
   ```python
   _TITLE_OVERVIEW_RE = re.compile(
       r'^https://www\.csfd\.cz/film/\d+[^/]*/(?:\d+[^/]*/)?prehled/$'
   )
   ```

2. **Update `postgres_loader.py`**:
   - Add new columns to INSERT/UPSERT SQL
   - Add dimension upserts for tags, screenwriters, cinematographers, composers

3. **Wire list page data into `cmd_parse`**:
   - After detail-page parsing, load list pages from `cache/vod_lists/`
   - Parse each list page with `VODListParser`
   - Merge `vod_date`, `distributor`, `list_type` into parsed titles by matching `film_url` -> `url_id`

4. **Sample validation script** (`scripts/validate_selectors.py`):
   - Pick ~10 random detail pages + ~5 list pages from cache
   - Parse each, print extracted fields as table
   - Flag any NULL mandatory fields or obviously wrong values

## Edge Cases & Mitigations

| Edge Case | Handling |
|-----------|----------|
| No English title | `title_en = NULL` (many Czech films have no translation) |
| Rating shows "? %" | `rating = NULL` (not 0) |
| < 3 reviews | JSON array with 0-2 items |
| No `.plot-full` | Fallback to `.body--plots`, then NULL |
| No tags on title | `tags = NULL`, no dim_tags rows |
| No poster image | `image_url = NULL` |
| Episode URL in list but no detail HTML cached | Skip -- `csfd scrape` must download it first |
| `premiere_detail` has no date | Store raw text, parse best-effort |
| Actors truncated with "vice" link | Parse only visible names (consistent with current behavior) |
| Distributor empty in older list pages | `distributor = NULL` |

## Acceptance Criteria

- [ ] All 18 detail-page fields extracted from cached HTML
- [ ] All 4 list-page fields extracted from cached list HTML
- [ ] VODTitle model has all new fields with proper types/validators
- [ ] DB schema has new columns + 4 new dimension tables (tags, screenwriters, cinematographers, composers)
- [ ] URL filter accepts child URLs (seria/epizoda)
- [ ] `csfd parse --dry-run` succeeds on full cache (4092 detail + 840 list pages)
- [ ] Parse success rate >= 95% on detail pages (title extraction)
- [ ] Validation script confirms correct extraction on 10+ sample pages across 2015-2026
- [ ] Existing tests updated + new tests for each new field
- [ ] Reviews stored as JSONB in DB, queryable

## Dependencies & Risks

| Risk | Mitigation |
|------|------------|
| CSFD HTML structure varied over time | Sample validation across years; `.plot-full` vs `.body--plots` fallback |
| Child URL volume explosion | ~6058 URLs currently; episodes may add 10-50% more -- manageable |
| Stale `selectors.json` config | Move all extraction to hardcoded selectors in parser (config selectors are already stale/unused) |
| Review structure varies | Defensive parsing with None fallbacks for each sub-field |

## Files to Modify

| File | Changes |
|------|---------|
| `db/schema.sql` | Add columns to fact_titles + 4 new dimension tables |
| `src/csfd_vod/transformation/models.py` | Add 12 new fields to VODTitle |
| `src/csfd_vod/transformation/parser.py` | Rewrite `_extract_fields` for all 18 detail fields |
| `src/csfd_vod/transformation/list_parser.py` | **NEW** -- list page parser |
| `src/csfd_vod/extraction/scraper.py` | Expand `_TITLE_OVERVIEW_RE` regex |
| `src/csfd_vod/loading/postgres_loader.py` | Add new columns to upsert + new dimension upserts |
| `src/csfd_vod/main.py` | Wire list parser into `cmd_parse` |
| `tests/test_parser.py` | Update SAMPLE_HTML + add tests for new fields |
| `scripts/validate_selectors.py` | **NEW** -- sample validation script |

## Sources

- **Origin brainstorm:** [docs/brainstorms/2026-04-10-parsing-field-definitions-brainstorm.md](docs/brainstorms/2026-04-10-parsing-field-definitions-brainstorm.md) -- Key decisions: (1) include all title types, (2) parent-child via URL parsing + detail page, (3) snapshot approach with scraped_at
- HTML structure verified on cached files: `cache/html/4fb850ad.html` (film), `cache/html/209e0b31.html` (serial)
- List page structure verified: `cache/vod_lists/2015_01_p01.html` (2015) and `cache/vod_lists/2026_04_p01.html` (2026) -- same selectors work
