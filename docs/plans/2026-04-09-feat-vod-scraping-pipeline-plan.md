---
title: VOD Scraping Pipeline - Modular Python + PostgreSQL + D3 Dashboard
type: feat
status: active
date: 2026-04-09
origin: docs/brainstorms/2026-04-09-vod-scraping-pipeline-brainstorm.md
---

# VOD Scraping Pipeline Implementation Plan

## Overview

Rebuild the existing amateur VOD scraping project with a modern, production-ready architecture. The pipeline will:
- Scrape VOD title metadata from csfd.cz weekly (automated via systemd timer or cron)
- Store data in PostgreSQL with fact/dimension table schema (same structure as current CSV exports for Tableau compatibility)
- Generate a static HTML page with D3.js visualizations (replaces Tableau workbook dependency)
- Implement incremental updates with idempotent operations (safe retries, no duplicates)
- Provide observable error handling with alerting (structured logs, metrics, notifications)

**Key Outcome**: A self-contained pipeline that runs reliably every week, produces the same data model as the old project, and eliminates manual intervention.

---

## Problem Statement

### Current State (Pain Points)

The existing VOD scraping project (`/Users/radozoo/Documents/claude/csfd/old/`) has several issues:
1. **Fragmented code**: Multiple unrelated Python scripts (downloader, parser, dimension generator)
2. **Intermediate artifacts**: Uses pickle files as intermediate storage (opaque, brittle, hard to debug)
3. **Manual pipeline**: CSV exports require manual loading into Tableau; no automation
4. **No error recovery**: If scraping fails partway, entire dataset is lost (no incremental updates)
5. **Brittle selectors**: No monitoring for HTML structure changes; silent data loss possible
6. **Manual scheduling**: No automated weekly execution; requires manual intervention
7. **Poor observability**: No logging, no metrics, no alerting
8. **Coupled to Tableau**: Data model tied to Tableau's requirements; hard to change

### Desired Outcome

A modular, observable, automated pipeline that:
- Runs every week without human intervention
- Recovers gracefully from partial failures (incremental updates)
- Produces the same data structure (fact_titles + dimensions) for Tableau compatibility
- Provides an HTML dashboard with D3.js visualizations (Tableau-independent)
- Is easy to debug and maintain (clear modules, structured logs, monitoring)
- Respects csfd.cz server (rate limiting, politeness, proper error handling)

---

## Proposed Solution: Modular Python Pipeline

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ Scheduler (systemd timer or cron)                           │
│ Runs: Weekly (Sunday 02:00 UTC)                             │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Application Entry Point (run_pipeline.py)                   │
│ - Coordinates all stages                                    │
│ - Handles checkpointing and error recovery                  │
│ - Collects metrics and logs                                 │
└────────────────┬────────────────────────────────────────────┘
                 │
        ┌────────┼────────┐
        │        │        │
        ▼        ▼        ▼
    ┌───────┐ ┌───────┐ ┌─────────────┐
    │Stage 1│ │Stage 2│ │Stage 3      │
    │Scrape │ │Parse  │ │Load + Viz   │
    └───────┘ └───────┘ └─────────────┘
        │        │        │
        └────────┼────────┘
                 │
                 ▼
         ┌──────────────┐
         │PostgreSQL DB │
         │+ Dimensions  │
         └──────────────┘
                 │
                 ▼
         ┌──────────────┐
         │HTML + D3.js  │
         │Dashboard     │
         └──────────────┘
```

### Component Structure

```
csfd-vod-pipeline/
├── src/
│   └── csfd_vod/
│       ├── __init__.py
│       ├── main.py                    # Entry point, orchestration
│       ├── config.py                  # Settings from .env + config.json
│       ├── logger.py                  # Structured logging setup
│       ├── metrics.py                 # Pipeline metrics collection
│       │
│       ├── extraction/
│       │   ├── scraper.py             # HTTP requests, retry logic, rate limiting
│       │   ├── rate_limiter.py        # Exponential backoff, delay management
│       │   └── session_manager.py     # Connection pooling, cookie handling
│       │
│       ├── transformation/
│       │   ├── parser.py              # BeautifulSoup selectors, field extraction
│       │   ├── models.py              # Pydantic models for Title, Dimension records
│       │   ├── validators.py          # Data validation (required fields, types, ranges)
│       │   └── deduplicator.py        # Dedup logic, upsert key generation
│       │
│       ├── loading/
│       │   ├── postgres_loader.py     # Upsert logic, transaction handling
│       │   ├── schema_manager.py      # Schema initialization, migrations
│       │   └── connection_pool.py     # SQLAlchemy pool configuration
│       │
│       ├── dashboard/
│       │   ├── json_exporter.py       # PostgreSQL → JSON export
│       │   ├── html_generator.py      # Static HTML generation
│       │   └── d3_templates.py        # D3.js chart templates
│       │
│       └── utils/
│           ├── errors.py              # Custom exceptions, error classification
│           └── checkpoint.py          # Progress tracking, resume capability
│
├── db/
│   └── schema.sql                     # DDL for all tables, constraints, indexes
│
├── config/
│   ├── selectors.json                 # BeautifulSoup CSS selectors
│   ├── config.example.json            # Template for local config
│   └── .env.example                   # Environment variables template
│
├── data/
│   ├── raw/                           # Raw HTML downloads (temp)
│   └── exports/                       # Generated JSON + HTML
│
├── tests/
│   ├── test_scraper.py
│   ├── test_parser.py
│   ├── test_postgres_loader.py
│   └── fixtures/                      # Sample HTML for regression testing
│
├── scripts/
│   └── run_pipeline.py                # Scheduler entry point (called by cron/systemd)
│
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml             # Dev environment with PostgreSQL
│
├── .env.example
├── .gitignore
├── requirements.txt                   # Runtime dependencies
├── requirements-dev.txt               # Testing, linting
├── setup.py / pyproject.toml
├── CLAUDE.md                          # Project documentation
└── README.md
```

---

## Technical Approach

### Phase 1: Core Pipeline Foundation (Weeks 1–2)

#### 1.1 Project Setup & Configuration

**Deliverables:**
- [ ] Directory structure, Git setup, `.gitignore`
- [ ] Virtual environment with `requirements.txt`
- [ ] `.env` and `config.json` templates for credentials/settings
- [ ] PostgreSQL schema (DDL in `db/schema.sql`)
- [ ] GitHub Actions workflow for testing (optional early)

**Technical Decisions:**
- **Python version**: 3.11+ (modern async/type support, but sync used for initial simplicity)
- **Dependencies**:
  ```
  requests==2.31.0               # HTTP with session pooling
  beautifulsoup4==4.12.2         # HTML parsing
  lxml==4.9.2                    # Faster BS4 backend
  psycopg2-binary==2.9.9         # PostgreSQL adapter
  sqlalchemy==2.0.20             # ORM + connection pooling
  pydantic>=2.0                  # Data validation models
  python-dotenv==1.0.0           # .env file loading
  structlog==24.1.0              # Structured logging
  tenacity==8.2.3                # Retry logic with backoff
  ```
- **Logging**: Structured JSON via `structlog` (parseable by monitoring systems)
- **Database**: PostgreSQL with SQLAlchemy ORM for type safety and migrations

**Critical Decisions Needed** (see Gap Analysis, section 1–5):
- [ ] **Deduplication key**: How to identify "same title" across scrapes? (URL, title+year, title+director?)
- [ ] **Mandatory fields**: Which fields are required? Which can be NULL?
- [ ] **Data type validation**: Range checks, format validation (year, links, etc.)?

#### 1.2 Scraper Module (requests + BeautifulSoup + Resilience)

**Deliverables:**
- [x] `src/csfd_vod/extraction/scraper.py`: HTTP downloader with session, retries, rate limiting
- [x] `src/csfd_vod/extraction/rate_limiter.py`: Exponential backoff, delay management
- [x] `src/csfd_vod/config/selectors.json`: CSS selectors for each field (versioned)
- [x] Sample HTML fixtures for testing

**Implementation Details:**

```python
# src/csfd_vod/extraction/scraper.py
class VODScraper:
    def __init__(self, config: ScrapeConfig, logger):
        self.session = requests.Session()
        self.rate_limiter = RateLimiter(delay_ms=500, jitter_ms=200)
        self.selectors = load_selectors("config/selectors.json")
    
    def scrape_vod_list(self) -> List[VODTitle]:
        """
        Fetch VOD titles from csfd.cz/vod page
        Returns list of scraped title dicts (url, title, etc.)
        Handles retries with exponential backoff
        """
        vod_page_url = "https://csfd.cz/..."  # Fill in actual URL
        for attempt in range(3):
            try:
                response = self.session.get(
                    vod_page_url,
                    headers={"User-Agent": self.get_random_user_agent()},
                    timeout=10
                )
                if response.status_code == 200:
                    return self.extract_title_links(response.text)
                elif response.status_code == 429:
                    # Rate limited; back off harder
                    wait_time = self.rate_limiter.get_backoff(attempt=attempt)
                    time.sleep(wait_time)
                else:
                    raise Exception(f"HTTP {response.status_code}")
            except (RequestException, Timeout) as e:
                if attempt < 2:
                    wait_time = self.rate_limiter.get_backoff(attempt=attempt)
                    time.sleep(wait_time)
                else:
                    raise
    
    def scrape_title_details(self, title_url: str) -> Optional[VODTitle]:
        """
        Fetch full details (genres, director, actors, etc.) for a single title
        Returns VODTitle dict or None if parsing fails
        """
        for attempt in range(3):
            try:
                self.rate_limiter.wait()  # Respect rate limits
                response = self.session.get(
                    title_url,
                    headers={"User-Agent": self.get_random_user_agent()},
                    timeout=10
                )
                response.raise_for_status()
                return self.extract_title_details(response.text)
            except TransientError:  # Timeout, 5xx
                if attempt < 2:
                    time.sleep((2 ** attempt) + random.uniform(0, 1))
                else:
                    logger.warning("scrape_failed_transient", url=title_url, attempts=3)
                    return None  # Skip this title, continue pipeline
            except PermanentError as e:  # 404, parsing error
                logger.warning("scrape_failed_permanent", url=title_url, error=str(e))
                return None  # Skip this title
```

**Rate Limiting Strategy:**
- Default: 500ms delay between requests (+ random jitter 0–200ms)
- On 429 (rate limited): Exponential backoff: 1s, 2s, 4s
- On timeout: Exponential backoff, max 3 attempts
- On permanent error (404): Skip record, continue pipeline
- Session pooling: Reuse TCP connections (reduce overhead)

**User-Agent Rotation:**
```json
// config/selectors.json (example)
{
  "user_agents": [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36...",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36..."
  ],
  "vod_page": {
    "url": "https://csfd.cz/vod/",
    "title_link_selector": "article.article a.title"
  },
  "title_page": {
    "title_selector": "h1.title",
    "year_selector": "span.year",
    "genre_selector": "span.genre",
    "director_selector": "a[data-role='director']",
    "actors_selector": "a[data-role='actor']",
    "vod_selector": "span.vod-platform"
  }
}
```

**Testing:**
- Unit tests with mocked responses (pre-saved HTML from csfd.cz)
- Regression tests if selectors break (compare before/after parsing results)

**Critical Decisions Needed**:
- [ ] What is the exact csfd.cz VOD page URL and structure?
- [ ] How many titles are we scraping (~1000? 5000? 20000?)?
- [ ] Should we scrape title details sequentially or in parallel batches?

#### 1.3 Parser Module (BeautifulSoup + Field Extraction)

**Deliverables:**
- [x] `src/csfd_vod/transformation/parser.py`: Extract fields from HTML
- [x] `src/csfd_vod/transformation/models.py`: Pydantic models for type safety
- [x] `src/csfd_vod/transformation/validators.py`: Data quality rules (in models.py)

**Data Models:**

```python
# src/csfd_vod/transformation/models.py
from pydantic import BaseModel, Field, validator

class VODTitle(BaseModel):
    url_id: str = Field(..., description="Unique identifier (csfd.cz URL)")
    title: str = Field(..., description="Title name")
    year: Optional[int] = Field(None, description="Release year (1890–2030)")
    director: Optional[str] = Field(None, description="Directors (comma-separated)")
    actors: Optional[str] = Field(None, description="Actors (comma-separated)")
    genres: Optional[str] = Field(None, description="Genres (forward-slash separated)")
    countries: Optional[str] = Field(None, description="Countries (forward-slash separated)")
    vod_platforms: Optional[str] = Field(None, description="VOD platforms (comma-separated)")
    link: str = Field(..., description="Full csfd.cz URL")
    date_added: datetime = Field(default_factory=datetime.utcnow, description="When added to VOD")
    
    @validator('year')
    def validate_year(cls, v):
        if v is not None and (v < 1890 or v > 2030):
            raise ValueError(f"Year out of range: {v}")
        return v
    
    @validator('title')
    def validate_title(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Title cannot be empty")
        return v.strip()

class ParsedTitle:
    """Intermediate representation during parsing"""
    def __init__(self, url: str, soup: BeautifulSoup, selectors: dict):
        self.url = url
        self.soup = soup
        self.selectors = selectors
        self.raw_data = {}
        self.errors = []
    
    def parse(self) -> Optional[VODTitle]:
        """Extract all fields from HTML, return VODTitle or None if critical fields missing"""
        try:
            self.raw_data['title'] = self.extract_field('title_selector')
            self.raw_data['year'] = self.extract_field('year_selector', as_int=True)
            self.raw_data['director'] = self.extract_field('director_selector')
            # ... etc
            
            # Validate and create model
            return VODTitle(**self.raw_data)
        except ValidationError as e:
            self.errors.append(f"Validation error: {e}")
            return None
        except Exception as e:
            self.errors.append(f"Parsing error: {e}")
            return None
    
    def extract_field(self, selector_key: str, as_int=False) -> Optional[str]:
        """Extract field using CSS selector, with error handling"""
        selector = self.selectors.get(selector_key)
        if not selector:
            self.errors.append(f"Missing selector: {selector_key}")
            return None
        
        try:
            elements = self.soup.select(selector)
            if not elements:
                # Selector returned no results: either optional field or selector broke
                self.errors.append(f"Selector '{selector_key}' returned 0 results")
                return None
            
            # Join multiple elements (e.g., multiple genres)
            text = ", ".join(e.get_text(strip=True) for e in elements)
            
            if as_int:
                return int(text)
            return text if text else None
        except Exception as e:
            self.errors.append(f"Error extracting '{selector_key}': {e}")
            return None
```

**Parsing Workflow:**
1. For each title URL, download HTML (done by Scraper)
2. Create BeautifulSoup object
3. For each field (title, year, director, etc.), extract using CSS selector
4. Validate extracted data against Pydantic model
5. If validation passes: return VODTitle object
6. If validation fails: log error, return None (skip this record)
7. Track per-selector success rate for alerting

**Critical Decisions Needed**:
- [ ] Do we explode genres/directors at parse time or at DB load time? (Recommend: at DB load time for clarity)
- [ ] How to handle "no director" vs. "director missing" (parse error)?
- [ ] Should we require selectors.json to be updated without redeploy?

#### 1.4 Database Manager (PostgreSQL + Incremental Upsert)

**Deliverables:**
- [ ] `db/schema.sql`: DDL for all tables
- [ ] `src/csfd_vod/loading/postgres_loader.py`: Upsert logic
- [ ] Connection pooling configuration (SQLAlchemy)

**Schema Design:**

```sql
-- db/schema.sql

-- Fact table (one row per title in current week's scrape)
CREATE TABLE fact_titles (
    title_id BIGSERIAL PRIMARY KEY,
    url_id VARCHAR(500) UNIQUE NOT NULL,  -- csfd.cz URL (dedup key)
    title VARCHAR(500) NOT NULL,
    year INTEGER CHECK (year >= 1890 AND year <= 2030),
    director VARCHAR(1000),              -- comma-separated (exploded to dim table)
    actors VARCHAR(2000),                -- comma-separated (exploded to dim table)
    link VARCHAR(1000) NOT NULL,         -- full csfd.cz URL
    date_added DATE NOT NULL,            -- when added to VOD
    date_scraped DATE NOT NULL,          -- when we scraped it (weekly snapshot)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    run_id VARCHAR(50),                  -- for tracking which pipeline run
    CONSTRAINT url_id_format CHECK (url_id ~ '^https://csfd\.cz')
);

-- Dimension tables (exploded)
CREATE TABLE dim_genres (
    genre_id BIGSERIAL PRIMARY KEY,
    title_id BIGINT NOT NULL REFERENCES fact_titles(title_id) ON DELETE CASCADE,
    genre VARCHAR(100) NOT NULL,
    UNIQUE(title_id, genre)
);

CREATE TABLE dim_directors (
    director_id BIGSERIAL PRIMARY KEY,
    title_id BIGINT NOT NULL REFERENCES fact_titles(title_id) ON DELETE CASCADE,
    director VARCHAR(200) NOT NULL,
    UNIQUE(title_id, director)
);

CREATE TABLE dim_actors (
    actor_id BIGSERIAL PRIMARY KEY,
    title_id BIGINT NOT NULL REFERENCES fact_titles(title_id) ON DELETE CASCADE,
    actor VARCHAR(200) NOT NULL,
    UNIQUE(title_id, actor)
);

CREATE TABLE dim_countries (
    country_id BIGSERIAL PRIMARY KEY,
    title_id BIGINT NOT NULL REFERENCES fact_titles(title_id) ON DELETE CASCADE,
    country VARCHAR(100) NOT NULL,
    UNIQUE(title_id, country)
);

CREATE TABLE dim_vods (
    vod_id BIGSERIAL PRIMARY KEY,
    title_id BIGINT NOT NULL REFERENCES fact_titles(title_id) ON DELETE CASCADE,
    vod_platform VARCHAR(100) NOT NULL,
    UNIQUE(title_id, vod_platform)
);

-- Audit table (for error recovery)
CREATE TABLE failed_records (
    failed_record_id BIGSERIAL PRIMARY KEY,
    url_id VARCHAR(500) NOT NULL,
    error_type VARCHAR(50),              -- 'parse_error', 'db_error', etc.
    error_message TEXT,
    original_data JSONB,                 -- raw scraped data for manual review
    run_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Progress checkpoint (for resuming after failures)
CREATE TABLE pipeline_runs (
    run_id VARCHAR(50) PRIMARY KEY,
    stage VARCHAR(50),                   -- 'scraping', 'parsing', 'loading', 'dashboard'
    status VARCHAR(20),                  -- 'in_progress', 'success', 'failure'
    start_time TIMESTAMP DEFAULT NOW(),
    end_time TIMESTAMP,
    titles_scraped INTEGER DEFAULT 0,
    titles_parsed INTEGER DEFAULT 0,
    titles_loaded INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    error_details JSONB,
    metrics JSONB                        -- duration, resource usage, etc.
);

-- Indexes for common queries
CREATE INDEX idx_fact_titles_date_scraped ON fact_titles(date_scraped DESC);
CREATE INDEX idx_fact_titles_url_id ON fact_titles(url_id);
CREATE INDEX idx_dim_genres_genre ON dim_genres(genre);
CREATE INDEX idx_dim_directors_director ON dim_directors(director);
CREATE INDEX idx_dim_vods_platform ON dim_vods(vod_platform);
```

**Upsert Logic (SQLAlchemy):**

```python
# src/csfd_vod/loading/postgres_loader.py
from sqlalchemy.dialects.postgresql import insert

class PostgreSQLLoader:
    def __init__(self, engine):
        self.engine = engine
        self.Session = sessionmaker(bind=engine)
    
    def load_titles(self, titles: List[VODTitle], run_id: str) -> LoadResult:
        """
        Upsert titles and all dimensions in a transaction
        Returns: (inserted_count, updated_count, errors)
        """
        result = LoadResult()
        session = self.Session()
        
        try:
            for title in titles:
                try:
                    # Fact table: INSERT ... ON CONFLICT UPDATE
                    stmt = insert(FactTitle).values(
                        url_id=title.url_id,
                        title=title.title,
                        year=title.year,
                        director=title.director,
                        actors=title.actors,
                        link=title.link,
                        date_added=title.date_added,
                        date_scraped=date.today(),
                        run_id=run_id
                    ).on_conflict_do_update(
                        index_elements=['url_id'],
                        set_=dict(
                            title=title.title,
                            year=title.year,
                            director=title.director,
                            actors=title.actors,
                            updated_at=func.now(),
                            run_id=run_id
                        )
                    )
                    
                    result_proxy = session.execute(stmt)
                    title_id = result_proxy.inserted_primary_key[0]
                    
                    # Dimensions: explode and insert
                    self.load_dimensions(session, title_id, title)
                    
                    result.inserted_count += 1
                except IntegrityError as e:
                    session.rollback()
                    result.errors.append(f"Integrity error for {title.url_id}: {e}")
                    logger.warning("title_load_failed", url_id=title.url_id, error=str(e))
                except Exception as e:
                    session.rollback()
                    result.errors.append(str(e))
                    logger.error("title_load_error", url_id=title.url_id, error=str(e))
            
            session.commit()
            result.status = "success"
        except Exception as e:
            session.rollback()
            result.status = "failure"
            result.errors.append(f"Transaction failed: {e}")
            logger.critical("load_transaction_failed", error=str(e))
        finally:
            session.close()
        
        return result
    
    def load_dimensions(self, session, title_id: int, title: VODTitle):
        """Explode multi-valued fields and insert dimension rows"""
        # Genres
        if title.genres:
            for genre in title.genres.split('/'):
                genre = genre.strip()
                if genre:
                    stmt = insert(DimGenre).values(title_id=title_id, genre=genre)\
                        .on_conflict_do_nothing(index_elements=['title_id', 'genre'])
                    session.execute(stmt)
        
        # Directors (similar pattern)
        if title.director:
            for director in title.director.split(','):
                director = director.strip()
                if director:
                    stmt = insert(DimDirector).values(title_id=title_id, director=director)\
                        .on_conflict_do_nothing(index_elements=['title_id', 'director'])
                    session.execute(stmt)
        
        # ... similar for actors, countries, vod_platforms
```

**Connection Pooling:**
```python
# src/csfd_vod/loading/connection_pool.py
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

def create_db_engine(db_url: str):
    return create_engine(
        db_url,
        poolclass=QueuePool,
        pool_size=5,           # Small pool for weekly batch job
        max_overflow=2,
        pool_recycle=3600,     # Recycle connections after 1 hour
        pool_pre_ping=True,    # Test connection before reuse
        echo=False,            # Set to True for SQL debugging
    )
```

**Critical Decisions Needed**:
- [ ] Is URL the deduplication key, or title+year? (Recommend: URL, most reliable)
- [ ] Should we track historical snapshots (fact_titles_archive) for trend analysis?
- [ ] Should we use soft deletes (is_deleted flag) or hard deletes?

#### 1.5 Integration Test

**Deliverable:**
- [ ] End-to-end test with 10–20 real titles from csfd.cz (staging DB only)
- [ ] Verify: no duplicates, dimensions correctly exploded, upsert idempotence

**Test Scenario:**
```python
def test_e2e_scrape_and_load():
    # 1. Scrape 10 titles from csfd.cz (real network call)
    scraper = VODScraper(config)
    titles_list = scraper.scrape_vod_list()[:10]
    
    titles = []
    for url in titles_list:
        title = scraper.scrape_title_details(url)
        if title:
            titles.append(title)
    
    # 2. Parse and validate
    assert len(titles) > 5  # At least 50% success
    
    # 3. Load to staging DB
    loader = PostgreSQLLoader(staging_engine)
    result = loader.load_titles(titles, run_id="test-001")
    
    # 4. Verify
    session = Session(staging_engine)
    assert session.query(FactTitle).count() == len(titles)
    assert session.query(DimGenre).count() > len(titles)  # Multiple genres per title
    
    # 5. Run again (idempotence check)
    result2 = loader.load_titles(titles, run_id="test-002")
    assert session.query(FactTitle).count() == len(titles)  # No duplicates
    
    # 6. Cleanup
    session.query(FactTitle).delete()
    session.commit()
```

---

### Phase 2: Dashboard Generation (Weeks 2–3)

#### 2.1 JSON Data Export

**Deliverables:**
- [ ] `src/csfd_vod/dashboard/json_exporter.py`: PostgreSQL → JSON
- [ ] Data aggregation queries (genre distribution, director frequency, etc.)

**Export Strategy:**

```python
# src/csfd_vod/dashboard/json_exporter.py
class JSONExporter:
    def __init__(self, engine):
        self.engine = engine
    
    def export_for_dashboard(self) -> dict:
        """Export aggregated data from PostgreSQL → JSON for D3"""
        with self.engine.connect() as conn:
            # Genre distribution (top 30)
            genres = conn.execute(text("""
                SELECT genre, COUNT(*) as count
                FROM dim_genres
                GROUP BY genre
                ORDER BY count DESC
                LIMIT 30
            """)).fetchall()
            
            # Director frequency (top 30)
            directors = conn.execute(text("""
                SELECT director, COUNT(*) as count
                FROM dim_directors
                GROUP BY director
                ORDER BY count DESC
                LIMIT 30
            """)).fetchall()
            
            # VOD platform popularity
            vods = conn.execute(text("""
                SELECT vod_platform, COUNT(*) as count
                FROM dim_vods
                GROUP BY vod_platform
                ORDER BY count DESC
            """)).fetchall()
            
            # Raw title list (for search/detail view)
            titles = conn.execute(text("""
                SELECT 
                    title_id, title, year, director, link,
                    (SELECT ARRAY_AGG(genre) FROM dim_genres WHERE title_id = ft.title_id) as genres,
                    (SELECT ARRAY_AGG(vod_platform) FROM dim_vods WHERE title_id = ft.title_id) as vod_platforms
                FROM fact_titles ft
                ORDER BY date_added DESC
            """)).fetchall()
            
            return {
                "metadata": {
                    "generated_at": datetime.utcnow().isoformat(),
                    "title_count": len(titles),
                    "genre_count": len(genres),
                    "director_count": len(directors),
                },
                "genres": [{"name": g[0], "count": g[1]} for g in genres],
                "directors": [{"name": d[0], "count": d[1]} for d in directors],
                "vod_platforms": [{"name": v[0], "count": v[1]} for v in vods],
                "titles": [
                    {
                        "id": t[0],
                        "title": t[1],
                        "year": t[2],
                        "director": t[3],
                        "link": t[4],
                        "genres": t[5] or [],
                        "vod_platforms": t[6] or []
                    }
                    for t in titles
                ]
            }
```

#### 2.2 HTML Page Generation

**Deliverables:**
- [ ] `src/csfd_vod/dashboard/html_generator.py`: Static HTML file generation
- [ ] `src/csfd_vod/dashboard/d3_templates.py`: D3.js chart templates
- [ ] CSS styling (Tokyo Night theme or custom)

**HTML Generation:**

```python
# src/csfd_vod/dashboard/html_generator.py
class HTMLGenerator:
    def generate(self, data: dict, output_path: str) -> bool:
        """
        Generate static HTML with embedded JSON and D3.js code
        Returns: True if successful, False if failed
        """
        try:
            # Embed data as window.__VOD_DATA__
            data_json = json.dumps(data, default=str)
            
            html_content = f"""
            <!DOCTYPE html>
            <html lang="cs">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>ČSFD VOD Dashboard</title>
                <style>{self.get_css()}</style>
            </head>
            <body>
                <div id="app">
                    <h1>ČSFD VOD Titles Dashboard</h1>
                    <div id="genre-chart"></div>
                    <div id="director-chart"></div>
                    <div id="platform-chart"></div>
                </div>
                
                <script>
                    window.__VOD_DATA__ = {data_json};
                </script>
                <script src="https://d3js.org/d3.v7.min.js"></script>
                <script>{self.get_d3_code()}</script>
            </body>
            </html>
            """
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info("html_generated", path=output_path, size_bytes=len(html_content))
            return True
        except Exception as e:
            logger.error("html_generation_failed", error=str(e))
            return False
    
    def get_d3_code(self) -> str:
        """D3.js visualization code (minimal example)"""
        return """
        // Genre distribution (bar chart, top 20)
        const data = window.__VOD_DATA__;
        
        const margin = {top: 20, right: 30, bottom: 30, left: 60};
        const width = 800 - margin.left - margin.right;
        const height = 400 - margin.top - margin.bottom;
        
        const svg = d3.select("#genre-chart")
            .append("svg")
            .attr("width", width + margin.left + margin.right)
            .attr("height", height + margin.top + margin.bottom)
            .append("g")
            .attr("transform", `translate(${margin.left},${margin.top})`);
        
        const x = d3.scaleBand().range([0, width]).padding(0.1);
        const y = d3.scaleLinear().range([height, 0]);
        
        x.domain(data.genres.slice(0, 20).map(d => d.name));
        y.domain([0, d3.max(data.genres, d => d.count)]);
        
        svg.selectAll(".bar")
            .data(data.genres.slice(0, 20))
            .enter()
            .append("rect")
            .attr("class", "bar")
            .attr("x", d => x(d.name))
            .attr("y", d => y(d.count))
            .attr("width", x.bandwidth())
            .attr("height", d => height - y(d.count))
            .attr("fill", "#d41d4a");
        
        // X axis
        svg.append("g")
            .attr("transform", `translate(0,${height})`)
            .call(d3.axisBottom(x))
            .selectAll("text")
            .attr("transform", "rotate(-45)")
            .style("text-anchor", "end");
        
        // Y axis
        svg.append("g").call(d3.axisLeft(y));
        """
```

**Critical Decisions Needed**:
- [ ] Exact D3 visualizations required? (pie, bar, network graph, timeline?)
- [ ] Should dashboard be interactive (filters, search) or static display?
- [ ] Performance target (load time, browser compatibility)?

---

### Phase 3: Scheduling & Deployment (Week 4)

#### 3.1 Scheduler Configuration

**Option A: systemd Timer (Recommended for Linux)**

```ini
# /etc/systemd/system/vod-scraper.timer
[Unit]
Description=Weekly VOD Scraper
After=network-online.target
Wants=network-online.target

[Timer]
# Every Sunday at 02:00 UTC
OnCalendar=Sun *-*-* 02:00:00
Persistent=true
Unit=vod-scraper.service

[Install]
WantedBy=timers.target

---

# /etc/systemd/system/vod-scraper.service
[Unit]
Description=VOD Scraper Service
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
MemoryLimit=1G
CPUQuota=50%
StandardOutput=journal
StandardError=journal
SyslogIdentifier=vod-scraper

# Pull latest image and run
ExecStart=/usr/bin/docker run --rm \
  -v /var/lib/vod-scraper/data:/app/data \
  --env-file /etc/vod-scraper/.env \
  vod-scraper:latest

# Restart on failure
Restart=on-failure
RestartMaxAttempts=3
RestartSec=5min

[Install]
WantedBy=multi-user.target
```

**Option B: Cron (Simpler, but less observability)**

```bash
# /etc/cron.d/vod-scraper
# Every Sunday at 02:00 UTC
0 2 * * 0 /usr/bin/docker run --rm -v /var/lib/vod-scraper/data:/app/data --env-file /etc/vod-scraper/.env vod-scraper:latest >> /var/log/vod-scraper.log 2>&1
```

#### 3.2 Docker Containerization

**Deliverables:**
- [ ] Multi-stage Dockerfile
- [ ] docker-compose.yml for local development
- [ ] Container image pushed to registry (Docker Hub or private)

**Dockerfile:**

```dockerfile
# Multi-stage build
FROM python:3.13-slim as builder
WORKDIR /tmp
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.13-slim
WORKDIR /app

# Non-root user
RUN useradd -m -u 1000 pipeline

# Copy dependencies from builder
COPY --from=builder /root/.local /home/pipeline/.local

# Application code
COPY --chown=pipeline:pipeline . .

USER pipeline
ENV PATH=/home/pipeline/.local/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "from csfd_vod.db import check_connection; check_connection()" || exit 1

ENTRYPOINT ["python", "-m", "csfd_vod.main"]
```

**docker-compose.yml (Development):**

```yaml
version: '3.8'
services:
  vod-scraper:
    build:
      context: .
      dockerfile: docker/Dockerfile
    environment:
      DB_HOST: postgres
      DB_NAME: vod_scraper
      DB_USER: vod_scraper
      DB_PASSWORD: dev-only
      LOG_LEVEL: DEBUG
    volumes:
      - ./data:/app/data
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - vod-net

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: vod_scraper
      POSTGRES_USER: vod_scraper
      POSTGRES_PASSWORD: dev-only
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U vod_scraper"]
      interval: 5s
      timeout: 5s
      retries: 5
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db/schema.sql:/docker-entrypoint-initdb.d/schema.sql
    networks:
      - vod-net

networks:
  vod-net:

volumes:
  postgres_data:
```

#### 3.3 Structured Logging & Monitoring

**Deliverables:**
- [ ] Structured logging with `structlog` (JSON output)
- [ ] Metrics collection (scrape duration, title count, error rate)
- [ ] Alert webhook (Slack or email on failure)

**Logging Configuration:**

```python
# src/csfd_vod/logger.py
import structlog
import sys

def configure_logging(log_level="INFO"):
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

logger = structlog.get_logger()

# Usage throughout pipeline
logger.info("pipeline_start", run_id="weekly-2026-04-09")
logger.info("scrape_complete", titles_found=342, duration_seconds=125)
logger.error("parse_failed", url="https://csfd.cz/...", error="selector_no_match")
logger.warning("db_insert_slow", duration_ms=5000, title_count=100)
```

**Monitoring Output (systemd journal):**
```bash
journalctl -u vod-scraper -f
journalctl -u vod-scraper --since "1 hour ago"
journalctl -u vod-scraper -o json  # Parse JSON logs
```

**Alert Webhook (Slack on Failure):**

```python
# src/csfd_vod/main.py (after pipeline completes)
def send_alerts_if_failed(result: PipelineResult):
    if result.status == "failure":
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if webhook_url:
            requests.post(webhook_url, json={
                "text": f":warning: VOD Scraper Failed",
                "blocks": [
                    {"type": "section", "text": {"type": "mrkdwn", "text": 
                        f"*Run ID:* {result.run_id}\n"
                        f"*Status:* FAILED\n"
                        f"*Errors:* {result.errors_count}\n"
                        f"*Logs:* Check systemd journal"
                    }}
                ]
            })
```

---

### Phase 4: Polish & Testing (Week 4+)

#### 4.1 Unit Tests

**Deliverables:**
- [ ] `tests/test_scraper.py`: Mock HTTP responses, test retry logic
- [ ] `tests/test_parser.py`: Sample HTML fixtures, test field extraction
- [ ] `tests/test_postgres_loader.py`: Test upsert idempotence, dimension explosions
- [ ] Fixtures: Real sample HTML from csfd.cz (pre-saved)

**Test Example:**

```python
# tests/test_parser.py
import pytest
from csfd_vod.transformation.parser import ParsedTitle
from csfd_vod.transformation.models import VODTitle

@pytest.fixture
def sample_html():
    with open('tests/fixtures/csfd_title_sample.html', 'r') as f:
        return f.read()

@pytest.fixture
def selectors():
    return {
        "title_selector": "h1.title",
        "year_selector": "span.year",
        "genre_selector": "span.genre",
        "director_selector": "a[data-role='director']",
    }

def test_parser_extracts_all_fields(sample_html, selectors):
    soup = BeautifulSoup(sample_html, 'html.parser')
    parser = ParsedTitle(
        url="https://csfd.cz/film/...",
        soup=soup,
        selectors=selectors
    )
    
    title = parser.parse()
    assert title is not None
    assert title.title == "Expected Title"
    assert title.year == 2020
    assert "Drama" in title.genres

def test_parser_handles_missing_optional_fields(sample_html_no_director, selectors):
    # Test title without director
    parser = ParsedTitle(url="...", soup=..., selectors=selectors)
    title = parser.parse()
    assert title is not None
    assert title.director is None  # Optional field

def test_parser_rejects_invalid_year(sample_html_bad_year, selectors):
    # Year = "banana" should fail validation
    parser = ParsedTitle(url="...", soup=..., selectors=selectors)
    title = parser.parse()
    assert title is None
    assert "year" in " ".join(parser.errors)
```

#### 4.2 End-to-End Testing

**Deliverable:**
- [ ] Automated test that runs full pipeline (scrape → parse → load → dashboard)
- [ ] Against staging PostgreSQL database
- [ ] Verify: no duplicates, dimension counts correct, dashboard generates

#### 4.3 Performance Testing

**Deliverable:**
- [ ] Profile pipeline with realistic data (1000+ titles)
- [ ] Measure: scraper throughput (titles/second), parse time, load time, dashboard generation time
- [ ] Identify bottlenecks (I/O, CPU, memory)

#### 4.4 Documentation

**Deliverables:**
- [ ] `CLAUDE.md`: Project overview, architecture, setup, commands
- [ ] `README.md`: User-facing documentation, how to run, how to deploy
- [ ] Operator runbook: "Pipeline failed, what do I do?"
- [ ] API documentation for each module

---

## System-Wide Impact Analysis

### Interaction Graph

**Happy Path (Weekly Scrape):**
```
Scheduler (systemd/cron)
  ↓
  Entry point (main.py) - starts logging, creates run_id
    ↓
    Scraper module - downloads HTML from csfd.cz
      - Retries on timeout (exponential backoff)
      - Respects rate limits (429 handling)
      - Returns list of title URLs
    ↓
    Parser module - extracts fields from HTML
      - Validates with Pydantic models
      - Returns VODTitle objects or None (on error)
      - Tracks per-selector error rate
    ↓
    Loader module - upserts to PostgreSQL
      - BEGIN TRANSACTION
      - INSERT ... ON CONFLICT fact_titles (handles duplicates)
      - EXPLODE and INSERT dimensions (genres, directors, etc.)
      - COMMIT or ROLLBACK on error
    ↓
    Dashboard module - exports JSON and generates HTML
      - Query PostgreSQL for aggregations
      - Render D3.js templates
      - Write HTML file to output path
    ↓
    Metrics collection - log pipeline stats
    ↓
    Alert webhook (if failures) - notify operator
    ↓
    Exit (success or failure status)
  ↓
Scheduler marks job as complete
```

**Error Path (Network Timeout):**
```
Scraper encounters timeout on URL #50
  ↓
  Retry logic: exponential backoff (1s, 2s, 4s)
    ↓
    If all 3 retries fail:
      - Log warning (not critical)
      - Add to failed_records table
      - Continue to next URL (best effort)
    ↓
  After scraping: log metrics
    - titles_attempted: 1000
    - titles_succeeded: 990
    - error_rate: 1%
    ↓
  If error_rate > threshold (10%):
    - Alert operator: "High error rate, possible site issue"
    - Continue anyway (don't fail entire run)
```

**Concurrency Risk (Scheduler Misfires):**
```
Week 1: Scheduled run starts at Sunday 02:00
  Scraping takes 30 minutes (finishes 02:30)
  ↓
Week 1 (manually): Operator starts manual run at 02:15 (overlapping)
  ↓
  Two processes both:
    - Download HTML from same URLs (wasteful, but safe)
    - Parse independently (safe)
    - Try to insert to PostgreSQL concurrently (DANGER)
      - Transaction A inserts title #1, dimension genre
      - Transaction B inserts title #1, dimension genre
      - ON CONFLICT clause should handle this (both attempt to insert same genre)
      - Database constraint prevents duplicate → one succeeds, one fails gracefully
    ↓
  Result: No data corruption (thanks to UNIQUE constraints)
  But: Wasted resources, potential for partial state
  
Mitigation:
  - Filesystem lock file (check before starting)
  - Or database-level lock (pessimistic)
  - Or distributed lock service (Redis, etcd)
```

### Error Propagation

| Layer | Error | Handling |
|-------|-------|----------|
| **Scheduler** | systemd/cron fails to start | System admin manually restarts service; not application responsibility |
| **Network (Scraper)** | Timeout fetching csfd.cz | Retry 3x with exponential backoff; skip record on permanent failure |
| **HTML Parsing** | Selector returns 0 results | Log warning (selector broken?); skip record; track per-selector error rate |
| **Data Validation** | Year = "banana" (validation error) | Reject record; skip; log error |
| **Database (Insert)** | Foreign key constraint violation | Transaction rollback; log error; save to failed_records for manual review |
| **Database (Connection)** | PostgreSQL unreachable | Crash with clear error; alert operator; retry next scheduled run |
| **Dashboard Generation** | D3.js template error | Skip dashboard generation; keep old HTML; log error |
| **File I/O** | Disk full when writing HTML | Catch exception; alert operator; old dashboard remains available |

### State Lifecycle Risks

**Partial Failure Scenario:**
1. Scraper succeeds: 1000 titles downloaded (state: OK)
2. Parser succeeds: 990 titles parsed, 10 failed (state: OK, best effort)
3. Loader: Inserts first 500 titles successfully, then PG connection dies
4. Transaction rollback: All 500 inserts reversed (state: SAFE, but back to empty DB)
5. Next scheduled run retries: Scrapes again, parses again, tries to insert again
6. Idempotency check: URL+date composite key prevents duplicates (state: SAFE)

**Safe State Transitions:**
```
IDLE
  ↓
SCRAPING (write to /data/raw/ directory)
  ↓ (success)
PARSING (read from /data/raw/, write to /data/parsed.json)
  ↓ (success)
LOADING (atomic: BEGIN, UPSERT, COMMIT or ROLLBACK)
  ↓ (success)
DASHBOARD (read from DB, write to /data/exports/index.html)
  ↓ (success)
IDLE (ready for next run)

OR at any step:
  ERROR → IDLE (with alert to operator, failed_records saved)
```

### API Surface Parity

Who else might consume this data?
- Tableau (uses PostgreSQL directly or CSV exports)
- External dashboards (consume JSON + HTML)
- Analytics (query PostgreSQL for aggregations)
- Mobile app (could query PostgreSQL or JSON API)

**Current scope**: Internal use (dashboard for repository owner). No external APIs planned.

### Integration Test Scenarios

1. **Full pipeline with 10 titles**: Scrape, parse, load, dashboard → verify no errors, correct counts
2. **Duplicate title in two weeks**: Insert in week 1, re-insert in week 2 → verify no duplicates
3. **HTML selector breakage**: Save old HTML without breaking selectors, verify error logged
4. **Database offline during load**: Verify transaction rollback, failed_records saved
5. **Concurrent runs**: Two processes start simultaneously, verify no data corruption (ON CONFLICT saves us)

---

## Critical Open Questions (From SpecFlow Analysis)

**These must be answered before implementation:**

1. **Deduplication Key** (Q1)
   - Use csfd.cz URL as unique identifier? Or title + year?
   - **Decision needed** before Phase 1.4 (database schema)

2. **Mandatory vs. Optional Fields** (Q2)
   - Which fields MUST be present? (Title + URL definitely; genre/director/year?)
   - **Decision needed** before Phase 1.3 (parser validation)

3. **HTML Structure Change Detection** (Q3)
   - How to detect when csfd.cz changes selectors?
   - Alert threshold: if parser fails on > 20% of titles?
   - **Decision needed** before Phase 3 (monitoring)

4. **Scraping Rate Limit Policy** (Q7)
   - Default delay between requests (500ms, 1s, 5s)?
   - Rotate proxies or just User-Agent?
   - **Decision needed** before Phase 1.2 (scraper implementation)

5. **Historical Data for Trends** (Q8)
   - Do we archive weekly snapshots for trend analysis?
   - Or just show current week's distribution?
   - **Decision needed** before Phase 1.4 (schema design)

6. **D3 Visualization Specifications** (Q9)
   - Exact charts: pie, bar, network, timeline?
   - Top 20 genres or all genres?
   - **Decision needed** before Phase 2.2 (HTML generation)

7. **HTML Deployment Strategy** (Q10)
   - Local filesystem? S3? GitHub Pages?
   - How is it served to users?
   - **Decision needed** before Phase 3.2 (deployment)

8. **Scheduler Implementation** (Q26)
   - systemd timer, cron, or APScheduler?
   - Exact day/time of weekly run?
   - **Decision needed** before Phase 3.1 (scheduler setup)

---

## Acceptance Criteria

### Functional Requirements

- [ ] **Weekly Execution**: Pipeline runs automatically every Sunday 02:00 UTC (configurable)
- [ ] **Data Completeness**: Scrapes all VOD titles from csfd.cz (1000+)
- [ ] **Data Accuracy**: Extracted fields match csfd.cz (title, genres, director, year, VOD platforms)
- [ ] **Idempotency**: Running pipeline twice with same source data produces identical database state (no duplicates)
- [ ] **Incremental Updates**: If scraping fails partway, previously scraped data still reaches database (partial success)
- [ ] **Dashboard Generation**: Static HTML with D3.js visualizations generated weekly, accessible via HTTP
- [ ] **Data Model Compatibility**: PostgreSQL schema matches original CSV structure (fact_titles + dim_* tables) for Tableau compatibility
- [ ] **Error Recovery**: Failed titles logged in failed_records table; operator can inspect and retry

### Non-Functional Requirements

- [ ] **Performance**: Pipeline completes in < 30 minutes (scrape 1000+ titles, parse, load, generate dashboard)
- [ ] **Rate Limiting**: Respects csfd.cz server (500ms delays, random jitter, exponential backoff on 429)
- [ ] **Observability**: All operations logged as structured JSON; systemd journal accessible
- [ ] **Reliability**: Automatic retry on transient failures; no IP bans from csfd.cz
- [ ] **Maintainability**: Code modular (scraper, parser, loader independent); easy to update selectors without redeploy
- [ ] **Testability**: Unit tests with fixtures; integration tests against staging DB

### Quality Gates

- [ ] Unit test coverage ≥ 80% (core modules)
- [ ] All exceptions handled (no unhandled errors)
- [ ] No SQL injection risks (parameterized queries via SQLAlchemy)
- [ ] No credentials in code (all from .env)
- [ ] Documentation complete (CLAUDE.md, README, operator runbook)

---

## Success Metrics

1. **Pipeline Uptime**: Runs successfully ≥ 95% of weeks (< 1 failure per 20 weeks)
2. **Data Completeness**: Scrapes ≥ 95% of VOD titles (< 50 missing titles)
3. **Error Rate**: Parser/loader error rate < 5% (< 50 of 1000 titles fail)
4. **Dashboard Freshness**: HTML updated weekly within 1 hour of scrape completion
5. **Operator Involvement**: Zero manual intervention required (fully automated)
6. **Data Consistency**: No duplicate titles in database (idempotency verified)

---

## Dependencies & Prerequisites

### External Dependencies

- **csfd.cz**: Website availability, HTML structure stability
  - Mitigation: Monitor error rates; alert operator on structure changes
- **PostgreSQL**: Database availability, disk space
  - Mitigation: Regular backups, connection pooling with retries
- **systemd/cron**: Scheduler availability
  - Mitigation: Systemd service health check, restart policy

### Internal Dependencies

- **Python 3.11+**: Runtime environment
- **Docker**: For containerization and deployment
- **PostgreSQL 16**: Database backend
- **Network access**: To download HTML from csfd.cz (outbound HTTP)

### Data Dependencies

- **Staging PostgreSQL database**: For testing before production deployment
- **Sample HTML fixtures**: Pre-saved csfd.cz pages for parser testing

---

## Risk Analysis & Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|-----------|
| **csfd.cz changes HTML structure** | Silent data loss (empty fields, wrong parsing) | Medium | Monitor selector success rate; alert on errors; version selectors in config.json |
| **csfd.cz rate-limits or bans IP** | Pipeline stops working; weekly data gaps | Low | Respect rate limits (500ms delays); rotate User-Agents; implement exponential backoff |
| **PostgreSQL connection pool exhausted** | Database hangs; inserts fail | Low | Monitor pool utilization; set max_overflow; implement connection recycling |
| **Scheduler misfires (2 runs concurrently)** | Race conditions; partial state corruption | Low | Implement filesystem lock; or rely on UNIQUE constraints to prevent duplicates |
| **Disk full (logs or HTML file)** | Pipeline crashes; old dashboard lost | Low | Log rotation policy (30 days); alert on disk usage; archive HTML with dates |
| **Operator doesn't notice failures** | Stale data served without warning | Medium | Slack/email alerts on failure; "last updated" timestamp on dashboard |
| **Selectors become outdated without detection** | Systematic data loss (0 results for all records) | Low | Monitor per-selector success rate; set threshold (e.g., alert if < 95% success) |

---

## Resource Requirements

### Development Time
- Phase 1 (Core Pipeline): 5–7 days (scraper, parser, loader, basic testing)
- Phase 2 (Dashboard): 2–3 days (JSON export, D3 charts, HTML generation)
- Phase 3 (Deployment): 1–2 days (systemd/Docker setup, monitoring)
- Phase 4 (Testing & Polish): 2–3 days (E2E tests, performance tuning, documentation)
- **Total**: 10–15 days (2–3 weeks with buffers)

### Infrastructure
- **Storage**: PostgreSQL database (~100MB for 1000 titles + dimensions)
- **Compute**: Single-core, 512MB RAM sufficient (weekly batch job)
- **Deployment**: Docker container on cloud VM (AWS t3.micro, ~$10/month)
- **Backups**: Daily PostgreSQL snapshots (RDS automated backups, or manual pg_dump)

### Monitoring & Logging
- systemd journal (built-in, no cost)
- Slack webhook for alerts (free tier)
- Optional: CloudWatch (AWS) or Datadog (~$30/month)

---

## Future Considerations

### Extensibility

1. **Real-time Updates**: Upgrade from weekly to daily/hourly scrapes
   - Change scheduler from systemd timer to APScheduler
   - Add incremental scraping (only fetch new/updated titles, not entire list)

2. **Multi-source Data**: Scrape from other VOD platforms beyond csfd.cz
   - Add configurable URL patterns and selectors
   - Deduplicate across sources

3. **Machine Learning Integration**: Recommend VOD titles based on genres/directors
   - Export features to ML pipeline
   - Score recommendations

4. **Mobile App**: Serve data via REST API
   - Add Flask/FastAPI app serving PostgreSQL queries
   - Implement caching (Redis)

5. **Tableau Integration**: Direct Tableau connection to PostgreSQL
   - Currently only CSV exports; could use live ODBC connection
   - Dimension tables already optimized for Tableau star schema

---

## Documentation Plan

### Immediate (Phase 1–2)

- [ ] `CLAUDE.md`: Project overview, architecture, local setup
- [ ] `README.md`: User guide, how to run locally, how to deploy
- [ ] `docs/API.md`: Module documentation (Scraper, Parser, Loader, Dashboard)
- [ ] `docs/SELECTORS.md`: CSS selector documentation and examples

### Phase 3–4

- [ ] `docs/RUNBOOK.md`: Operator guide ("Pipeline failed, what do I do?")
- [ ] `docs/SCHEMA.md`: Database schema documentation
- [ ] `docs/DEPLOYMENT.md`: Production deployment instructions
- [ ] `docs/MONITORING.md`: How to monitor pipeline, view logs, set up alerts

---

## Implementation Timeline

```
Week 1 (Apr 9–15):
  Mon–Tue: Project setup, schema design, scraper module
  Wed–Thu: Parser module with validation, unit tests
  Fri: Loader module, integration test with staging DB

Week 2 (Apr 16–22):
  Mon–Tue: Polish Phase 1, fix bugs, performance tuning
  Wed–Thu: Dashboard JSON export and D3 charts
  Fri: HTML generation, basic CSS styling

Week 3 (Apr 23–29):
  Mon: Scheduler setup (systemd timer + Docker)
  Tue: E2E testing, error scenario validation
  Wed–Fri: Documentation, monitoring setup, operator runbook

Week 4 (Apr 30–May 6):
  Mon: Code review, refactoring
  Tue–Thu: Edge case testing, performance optimization
  Fri: Cutover to production, first real weekly run

Ongoing:
  Monitor pipeline weekly, adjust thresholds based on real data
  Update selectors if csfd.cz changes HTML
  Collect metrics, identify optimization opportunities
```

---

## Sources & References

### Origin Brainstorm
- **Brainstorm document:** [docs/brainstorms/2026-04-09-vod-scraping-pipeline-brainstorm.md](docs/brainstorms/2026-04-09-vod-scraping-pipeline-brainstorm.md)
  - Key decisions carried forward:
    1. Modular Python architecture (separate scraper, parser, loader modules)
    2. PostgreSQL backend with fact/dimension table schema
    3. Static HTML page with D3.js visualizations (no Tableau needed)
    4. Weekly scheduled execution with incremental updates
    5. Robust error handling and recovery

### Local Patterns & Examples
- **RA Podcast Pipeline** (`/Users/radozoo/Documents/claude/ra/`)
  - Module structure and orchestration pattern
  - D3.js visualization example
  - GitHub Actions weekly scheduling
  - Progress tracking and resume capability
- **ts-demo-factory** (`/Users/radozoo/Documents/claude/demo-maker/ts-demo-factory/`)
  - Pydantic models for type safety
  - Configuration management (.env + Config dataclass)
  - Error handling patterns
- **Old CSFD code** (`/Users/radozoo/Documents/claude/csfd/old/`)
  - Selector references for BeautifulSoup
  - Dimension table explosion logic
  - CSV export structure

### Best Practices References
- **Web Scraping 2026**: [Web Scraping Best Practices 2026: Architecture, Ethics, and Production Patterns](https://use-apify.com/blog/web-scraping-best-practices-2026)
- **Python Pipelines**: [Data Pipelines with Python: 6 Frameworks](https://dagster.io/guides/data-pipelines-with-python-6-frameworks-quick-tutorial)
- **PostgreSQL Schema**: [Star Schema vs Snowflake Schema](https://www.montecarlodata.com/blog-star-schema-vs-snowflake-schema/)
- **D3.js Optimization**: [Optimizing D3 Chart Performance for Large Data Sets](https://reintech.io/blog/optimizing-d3-chart-performance-large-data)
- **Docker Best Practices**: [Best practices for containerizing Python with Docker](https://snyk.io/blog/best-practices-containerizing-docker/)
- **systemd Timers**: [systemd timers vs cron in 2026](https://crongen.com/blog/cron-vs-systemd-timers-2026)

### Technology Documentation
- **SQLAlchemy**: https://docs.sqlalchemy.org/en/20/ (ORM, connection pooling)
- **Pydantic**: https://docs.pydantic.dev/latest/ (data validation)
- **structlog**: https://www.structlog.org/ (structured logging)
- **D3.js**: https://d3js.org/guides (data visualization)
- **BeautifulSoup**: https://www.crummy.com/software/BeautifulSoup/bs4/doc/ (HTML parsing)

---

## Next Steps

Ready to proceed with implementation. Critical decisions required before Phase 1:

1. [ ] **Deduplication strategy**: URL vs. title+year
2. [ ] **Optional/mandatory fields**: Finalize data model
3. [ ] **D3 visualizations**: Specific charts and interactive features
4. [ ] **Scheduler choice**: systemd timer or cron
5. [ ] **Deployment target**: VM, cloud, or local

Once clarified, begin Phase 1 implementation (scraper module).
