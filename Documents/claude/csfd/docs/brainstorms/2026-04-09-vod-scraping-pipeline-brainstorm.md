---
name: VOD Scraping Pipeline + Interactive Dashboard
description: Modernized scraping pipeline for csfd.cz VOD titles with PostgreSQL backend and interactive HTML visualization
type: project
---

# VOD Scraping Pipeline Brainstorm

## What We're Building

A **modular Python pipeline** that scrapes VOD titles from csfd.cz weekly, stores them in PostgreSQL, and generates a static **HTML page** with D3.js visualizations of the data.

### Components:
1. **Data Pipeline** (Python)
   - Scraper module: download HTML from csfd.cz
   - Parser module: extract Title, Genre, Year, Director, Link, VOD Platforms, Date
   - DB Manager: incremental upserts to PostgreSQL
   
2. **HTML Page** (Static, generated weekly)
   - Built with D3.js for charts/visualizations
   - Data embedded as JSON in the HTML
   - Shows genre distributions, director frequencies, VOD platforms, trends
   - Can be inspired by Tableau workbook (but not a direct copy)
   - Client-side rendering (no server needed)

3. **Scheduler**
   - Weekly execution (systemd timer, Airflow, or lightweight scheduler)
   - Error handling: incremental updates on failure

---

## Why This Approach

**Modularity** → Clean separation of concerns. Each module can be tested independently.

**PostgreSQL** → Better for Tableau integration, querying, and scaling. Supports relationships and aggregations needed for the dimension tables.

**Incremental Updates** → If scraping fails, we don't lose data. We only update what we successfully fetched.

**Interactive HTML** → No dependency on Tableau licenses/exports. Full control over interactivity and styling.

**Weekly Scheduling** → Automated, repeatable. No manual intervention needed.

---

## Key Decisions

### 1. **Architecture: Modular Python Pipeline**
```
csfd_pipeline/
├── src/
│   ├── scraper.py        # Download + retry logic
│   ├── parser.py         # Extract fields from HTML
│   ├── db_manager.py     # PostgreSQL operations
│   └── config.py         # Settings (URLs, delays, etc.)
├── db/
│   └── schema.sql        # Tables: titles, genres, directors, etc.
├── scheduler/
│   └── run.py            # Entry point (called by cron/Airflow)
└── dashboard/
    └── index.html        # Generated HTML + JS visualization
```

### 2. **Database Schema**
- **fact_titles**: Title, Year, Link, Director, DateAdded, etc.
- **dim_genres**: Url_id, Genre (exploded)
- **dim_directors**: Url_id, Director (exploded)
- **dim_actors**: Url_id, Actor (exploded)
- **dim_countries**: Url_id, Country (exploded)
- **dim_vods**: Url_id, VOD_Platform (exploded)

Same structure as current CSV exports → easy for Tableau.

### 3. **Scraping Strategy**
- Use existing approach (requests + BeautifulSoup) as inspiration
- Add robustness:
  - Configurable delays between requests
  - Randomized User-Agents
  - Retry logic with exponential backoff
  - Session management

### 4. **Error Handling & Updates**
- **Scraping fails** → Log error, don't insert incomplete data
- **Partial success** → Insert what we got, keep old data for missing entries
- **Database failure** → Crash with clear error (don't corrupt data)

### 5. **HTML Page**
- Static HTML page generated weekly alongside scraping
- D3.js visualizations with embedded JSON data
- Charts: Genre distribution, Directors by frequency, VOD platform popularity, trends
- No server-side rendering needed (client-side D3 rendering)
- Can be inspired by Tableau workbook layout, but custom design
- Link to csfd.cz title pages included

---

## Resolved Questions

1. **Visualization Framework** → **D3.js** ✓ (matches RA project experience)

2. **Deployment Target** → **Recommendations:**
   - **Best:** Docker container on cloud (AWS EC2 t3.micro / Linode 5$, weekly scheduled)
   - **Alternative:** Local cron job if laptop runs 24/7
   - **Why:** Reliable, scalable, low-cost, easier to maintain

3. **Tableau Workbook** → **Not needed** ✓ (HTML page only, can use as inspiration)

4. **Data Delivery** → **Static HTML** ✓ (Generated 1x weekly with scraping)
   - HTML file with embedded JSON data
   - No live API needed (simpler deployment)
   - D3.js renders charts client-side

5. **Data Freshness** → Weekly (acceptable with static approach)

---

## Implementation Outline

### Phase 1: Core Pipeline (weeks 1-2)
- Scraper module with retry logic
- Parser module (extract fields)
- PostgreSQL schema setup
- DB manager (incremental inserts)
- First test run with 100 titles

### Phase 2: HTML Page Generation (weeks 2-3)
- D3 charts: genre distribution, directors, VOD platforms, timeline, trends
- Data export from PostgreSQL → JSON (embedded in HTML)
- HTML page template with D3 visualization code
- Styling & layout (inspired by existing Tableau workbook, but custom design)

### Phase 3: Scheduling & Deployment (week 4)
- systemd timer or cron on Docker container
- Error monitoring/logging
- Documentation

### Phase 4: Polish & Testing (week 4+)
- End-to-end testing
- Incremental update logic validation
- Performance checks

---

## Next Steps

Ready to move to **`/cde:plan`** phase where we'll detail:
- Module structure & responsibilities
- Database schema (SQL)
- Scraping algorithm & error handling
- D3 visualization specs
- Deployment instructions
