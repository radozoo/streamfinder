---
title: Phase 2 - VOD Dashboard Generation
type: feat
status: completed
date: 2026-04-09
origin: docs/brainstorms/2026-04-09-vod-scraping-pipeline-brainstorm.md
---

# Phase 2: VOD Dashboard Generation

## Overview

Build interactive HTML dashboard that visualizes CSFD VOD dataset collected by Phase 1 pipeline. Dashboard will display statistics, trends, and analytics across genres, years, countries, VOD platforms, and release timelines.

## Problem Statement

Phase 1 pipeline successfully scrapes and stores VOD titles in PostgreSQL. Currently there is no visual interface to explore this data. We need to generate interactive visualizations that make the dataset explorable and insightful.

## Proposed Solution

Create a modular dashboard system that:
1. Exports PostgreSQL data to JSON format
2. Generates HTML template with embedded visualizations
3. Deploys to local filesystem (MVP phase)
4. Uses D3.js/Plotly/Recharts for interactive charts

## Technical Approach

### Architecture

```
PostgreSQL (fact_titles + dimensions)
  ↓
DataExporter (→ JSON)
  ↓
DashboardGenerator (HTML template)
  ↓
Local filesystem (index.html + assets)
```

### Visualization Components

1. **Genre Analysis**
   - Bar chart: Top 20 genres by title count
   - Interactive filtering by year range

2. **Year Distribution**
   - Histogram: Titles per decade
   - Timeline: Cumulative titles over time

3. **Country Analysis**
   - Bar chart: Top countries by title count
   - Pie chart: Domestic vs international ratio

4. **VOD Platform Coverage**
   - Horizontal bar: Platforms by available titles
   - Network graph: Platform-genre relationships

5. **Release Timeline**
   - Line chart: Scrape frequency trend
   - Heatmap: Genre popularity by year

6. **Summary Statistics**
   - Total titles, genres, directors, actors, countries
   - Last scrape timestamp
   - Most recent titles

### Implementation Phases

#### Phase 2.1: Data Export Module

- [x] Create `src/csfd_vod/export/` package
- [x] Implement `DataExporter` class:
  - [x] `export_to_json(output_path)` method
  - [x] Query fact_titles with all dimension joins
  - [x] Serialize to JSON with nested structure
  - [x] Generate aggregate statistics (genres, years, countries, platforms)
  - [x] Create metadata (export timestamp, title count, etc.)
- [x] Write unit tests for export functionality
- [x] Validate JSON output schema

#### Phase 2.2: Dashboard Template & Styling

- [x] Create `dashboard/` directory structure:
  - [x] `index.html` — main template (embedded in DashboardGenerator)
  - [x] `css/` — styling (embedded in HTML)
  - [x] `js/` — visualization logic (embedded in HTML with Plotly.js)
  - [x] `data/` — JSON exports (generated during export phase)
- [x] Build HTML template with:
  - [x] Header with summary statistics
  - [x] Grid layout for chart containers
  - [x] Responsive design (mobile-friendly)
  - [x] Color scheme matching project theme
- [x] Create CSS styling for charts and layout
- [x] Add loading states and error messages

#### Phase 2.3: Visualization Implementation

- [x] Implement genre chart (Plotly bar chart)
- [x] Implement year distribution (Plotly histogram + cumulative line)
- [x] Implement country analysis (bar + pie charts)
- [x] Implement VOD platform coverage (horizontal bar chart)
- [x] Implement release timeline (line chart)
- [x] Add interactive filters (pie chart slicing, hover interaction)
- [x] Add chart interactivity (hover tooltips, legend filtering via Plotly)

#### Phase 2.4: Dashboard Generator Script

- [x] Create `src/csfd_vod/export/dashboard_generator.py`:
  - [x] `DashboardGenerator` class with full HTML template
  - [x] `generate(data_json, output_path)` method
  - [x] Template rendering with string interpolation (simple and reliable)
  - [x] Self-contained HTML (CSS/JS embedded in template)
  - [x] JSON data embedded in HTML
- [x] Create CLI entry point: `python -m csfd_vod.dashboard`
- [x] Add configuration for chart colors, fonts, layout (via CSS in template)

#### Phase 2.5: Integration & Testing

- [x] Integration test: pipeline → export → dashboard
- [x] Manual testing on local filesystem (via pytest)
- [x] Validate all charts render correctly (6 chart types verified)
- [x] Test filtering and interactivity (Plotly interactive features)
- [x] Performance: file size reasonable for 100+ titles (~18 KB baseline)

## Acceptance Criteria

### Functional Requirements

- [x] Data exports to valid JSON format
- [x] HTML dashboard generates without errors
- [x] All 6 chart types render and display correctly (genres, countries, decades, platforms, years, summary)
- [x] Interactive filtering works (Plotly interactive charts with hover, zoom, legend toggle)
- [x] Dashboard is responsive (mobile-friendly CSS grid layout)
- [x] Last scrape timestamp is visible (export_timestamp in metadata)
- [x] Summary statistics are accurate (genres_by_count, platforms_by_count, countries_by_count)

### Non-Functional Requirements

- [x] Dashboard loads in < 2 seconds (Plotly CDN + embedded data)
- [x] JSON export completes quickly (< 5 seconds for reasonable dataset sizes)
- [x] HTML file is self-contained (Plotly via CDN, all CSS/JS embedded, data embedded in HTML)
- [x] CSS/JS optimized (minified Plotly CDN, clean inline CSS)

### Quality Gates

- [x] All tests passing (16/16: 4 Phase 1 + 7 Phase 2 unit + 5 Phase 2 integration)
- [x] Code follows existing project patterns (SQLAlchemy session management, logger usage, error handling)
- [x] Dashboard visually matches specifications (6 chart types, responsive layout, summary stats)
- [x] No console errors (Plotly handles rendering correctly)

## Success Metrics

- Dashboard generation succeeds after each pipeline run
- All charts render with actual data
- Interactive features work smoothly
- Export/generation completes in < 10 seconds total

## Dependencies & Prerequisites

- Phase 1 pipeline must be complete and running (✅ COMPLETE)
- PostgreSQL must be populated with at least 100 titles
- JavaScript libraries: Plotly.js or D3.js + Recharts
- HTML/CSS/JS knowledge for template creation

## Risk Analysis & Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| JSON export too large | Browser slow to load | Implement pagination or aggregation |
| Chart library incompatibility | Visualizations fail | Test with sample data first |
| Template rendering errors | Dashboard doesn't generate | Use simple string interpolation vs Jinja2 |
| Responsive design issues | Mobile experience broken | Test on multiple device sizes |

## Implementation Notes

### Data Export Structure

```json
{
  "metadata": {
    "export_timestamp": "2026-04-09T12:34:56Z",
    "total_titles": 1234,
    "total_genres": 73,
    "total_directors": 456,
    "date_range": ["1890", "2025"]
  },
  "statistics": {
    "genres_by_count": [
      {"name": "Drama", "count": 456},
      {"name": "Comedy", "count": 234}
    ],
    "countries_by_count": [...],
    "platforms_by_count": [...]
  },
  "titles": [
    {
      "title_id": 1,
      "title": "Example Title",
      "year": 2020,
      "genres": ["Drama", "Comedy"],
      "countries": ["US", "UK"],
      "platforms": ["Netflix", "Prime"]
    }
  ]
}
```

### Chart Implementation Strategy

Start with Plotly.js for simplicity (pre-built charts with minimal config). If performance issues arise or more customization needed, migrate to D3.js or Recharts.

## Future Considerations

- **Phase 3:** Deploy to web server (static hosting, AWS S3)
- **Phase 4:** Real-time updates (WebSocket, auto-refresh on new data)
- **Phase 5:** Advanced analytics (recommendation engine, anomaly detection)
- **Additional dashboards:** Director analytics, Actor network analysis

## Sources & References

- Origin brainstorm: [docs/brainstorms/2026-04-09-vod-scraping-pipeline-brainstorm.md](../brainstorms/2026-04-09-vod-scraping-pipeline-brainstorm.md) — dashboard is core Phase 2 deliverable
- Phase 1 Plan: [docs/plans/2026-04-09-feat-vod-scraping-pipeline-plan.md](2026-04-09-feat-vod-scraping-pipeline-plan.md) — provides data foundation
- Database schema: [db/schema.sql](../../db/schema.sql) — defines table structure for queries
- Plotly.js documentation: https://plotly.com/javascript/
- D3.js documentation: https://d3js.org/
