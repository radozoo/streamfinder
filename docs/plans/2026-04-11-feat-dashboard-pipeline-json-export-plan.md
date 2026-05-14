---
title: "feat: Dashboard Pipeline — JSON Export Rewrite"
type: feat
status: completed
date: 2026-04-11
origin: docs/brainstorms/2026-04-11-dashboard-pipeline-brainstorm.md
---

# feat: Dashboard Pipeline — JSON Export Rewrite

## Overview

Prepísať existujúci `DataExporter` + `DashboardGenerator` tak, aby:
- Exportoval pre-agregované JSON súbory do `dashboard/data/`
- Opravil N+1 query bug (25 000+ dotazov → 9 dotazov)
- Zahrnul všetky nové polia (`rating`, `vod_date`, `reviews`, `tags`, atď.)
- Pridal `csfd dashboard` CLI príkaz do `main.py`

Pipeline: `csfd parse` → PostgreSQL → `csfd dashboard` → `dashboard/data/*.json` → `dashboard/index.html`

(see brainstorm: docs/brainstorms/2026-04-11-dashboard-pipeline-brainstorm.md)

## Problem Statement

### Bug 1: N+1 query v DataExporter

`exporter.py:154` — `_query_dimension()` sa volá pre každý titul zvlášť:

```python
# Teraz (5159 titulov × 5 dim tabuliek = 25 795 SQL dotazov):
for row in result:
    title_dict["genres"] = self._query_dimension(session, "dim_genres", "genre", title_id)
    title_dict["actors"] = self._query_dimension(session, "dim_actors", "actor", title_id)
    ...
```

Fix: jeden `GROUP BY` dotaz na dimenziu, výsledky zoskupiť v Pythone do `dict[title_id → list]`.

### Bug 2: Chýbajúce polia

`_query_titles_with_dimensions()` (line 105) neobsahuje:
- `rating`, `plot`, `image_url`, `title_type`, `vod_date`, `distributor`, `premiere_detail`, `reviews`, `scraped_at`, `title_en`, `parent_url`

Dimension tabuľky `dim_tags`, `dim_screenwriters`, `dim_cinematographers`, `dim_composers` tiež nie sú exportované.

### Bug 3: Žiadny `csfd dashboard` príkaz

`main.py` nemá `dashboard` subcommand. Export sa musí volať manuálne z Pythonu.

## Proposed Solution

### Architektonická zmena: od "jeden veľký JSON" k "viacero malých JSON"

**Pred:** `export_to_json()` → jeden súbor s 5159 titulmi (pomalý načet v browseri)

**Po:** `csfd dashboard` → `dashboard/data/` so súbormi:

```
dashboard/data/
  summary.json          # počty, metadáta
  genres.json           # [{name, count}] top 30
  directors.json        # [{name, count}] top 30
  actors.json           # [{name, count}] top 30
  countries.json        # [{name, count}]
  platforms.json        # [{name, count}]
  tags.json             # [{name, count}] top 50
  rating_distribution.json  # [{bucket, count}] 0-10, 10-20, ..., 90-100
  vod_by_month.json     # [{month, count}] posledných 24 mesiacov
  top_titles.json       # [{title, year, rating, vod_date, distributor, image_url}] top 100 by rating
```

Každý súbor je nezávislý — D3/Plotly načíta len to, čo potrebuje.

## Technical Approach

### Opravené SQL dotazy (bez N+1)

```python
# src/csfd_vod/export/exporter.py

def _load_dimension(self, session, table: str, col: str) -> dict[int, list[str]]:
    """Načíta celú dimenziu jedným dotazom. Vracia dict title_id → [values]."""
    sql = text(f"SELECT title_id, {col} FROM csfd_vod.{table} ORDER BY {col}")
    result: dict[int, list] = {}
    for row in session.execute(sql):
        result.setdefault(row[0], []).append(row[1])
    return result

def export(self, output_dir: str) -> dict:
    """Exportuje všetky JSON súbory do output_dir."""
    # 1. Načítaj všetky dimenzie jedným dotazom každá (9 dotazov celkovo)
    genres_map = self._load_dimension(session, "dim_genres", "genre")
    actors_map = self._load_dimension(session, "dim_actors", "actor")
    directors_map = self._load_dimension(session, "dim_directors", "director")
    countries_map = self._load_dimension(session, "dim_countries", "country")
    platforms_map = self._load_dimension(session, "dim_vods", "vod_platform")
    tags_map = self._load_dimension(session, "dim_tags", "tag")
    screenwriters_map = self._load_dimension(session, "dim_screenwriters", "screenwriter")
    cinematographers_map = self._load_dimension(session, "dim_cinematographers", "cinematographer")
    composers_map = self._load_dimension(session, "dim_composers", "composer")

    # 2. Načítaj fact_titles (1 dotaz)
    titles = self._load_titles(session)

    # 3. Spoj v Pythone + vypočítaj agregácie
    # 4. Ulož JSON súbory
```

### Nový SQL pre fact_titles

```sql
SELECT
    title_id, url_id, title, title_en, year, link,
    rating, plot, image_url, title_type, parent_url,
    vod_date, distributor, premiere_detail, reviews, scraped_at,
    date_added
FROM csfd_vod.fact_titles
ORDER BY vod_date DESC NULLS LAST
```

### CLI príkaz

```python
# src/csfd_vod/main.py — nový subcommand

def cmd_dashboard(args) -> dict:
    """Exportuj JSON súbory a vygeneruj HTML dashboard."""
    config = load_config_from_env()
    exporter = DataExporter(config.database.connection_string)
    output_dir = Path("dashboard/data")
    stats = exporter.export(str(output_dir))
    logger.info("dashboard_exported", **stats)
    return {"success": True, **stats}

# V main():
p_dashboard = subparsers.add_parser("dashboard", help="Export JSON + generate HTML dashboard")
p_dashboard.add_argument("--output-dir", default="dashboard", help="Output directory")
```

## Acceptance Criteria

- [x] `csfd dashboard` príkaz funguje bez chýb
- [x] `dashboard/data/*.json` obsahuje všetkých 10 súborov
- [x] Export prebehne v < 10 sekúnd (nie 25 000 dotazov)
- [x] `top_titles.json` obsahuje `rating`, `vod_date`, `image_url`
- [x] `rating_distribution.json` správne počíta buckety 0-10, 10-20, ...
- [x] `vod_by_month.json` pokrýva posledných 24 mesiacov
- [x] Existujúce testy prechádzajú (`pytest tests/`)
- [x] `dashboard/index.html` sa otvorí v prehliadači a zobrazí grafy

## Files to Modify

| Súbor | Zmena |
|-------|-------|
| `src/csfd_vod/export/exporter.py` | Kompletný rewrite: fix N+1, nové polia, export do `dashboard/data/*.json` |
| `src/csfd_vod/export/dashboard_generator.py` | Update HTML template pre nové JSON súbory a grafy |
| `src/csfd_vod/main.py` | Pridaj `dashboard` subcommand (cmd_dashboard funkcia) |
| `tests/test_exporter.py` | Update testy pre nové rozhranie |

## Dependencies & Risks

| Riziko | Mitigácia |
|--------|-----------|
| `reviews` je JSONB — čo exportovať? | Exportovať počet reviews na titul, nie raw text (pre teraz) |
| `dashboard/index.html` stará Plotly šablóna nezodpovedá novým JSON súborom | Aktualizovať `DashboardGenerator` spolu s exporterom |
| `date_added` vs `vod_date` — ktoré použiť pre timeline? | `vod_date` (keď prišiel na VOD), nie `date_added` (kedy sme ho pridali do DB) |

## Sources

- **Origin brainstorm:** [docs/brainstorms/2026-04-11-dashboard-pipeline-brainstorm.md](docs/brainstorms/2026-04-11-dashboard-pipeline-brainstorm.md)
  - Rozhodnutie: Statické JSON súbory + Plotly/D3, pipeline `csfd parse → DB → csfd dashboard → JSON → HTML`
- Existujúci exporter: [src/csfd_vod/export/exporter.py](src/csfd_vod/export/exporter.py) — N+1 bug na line 154
- Existujúci dashboard generator: [src/csfd_vod/export/dashboard_generator.py](src/csfd_vod/export/dashboard_generator.py) — Plotly šablóna, treba update
- CLI vzor: [src/csfd_vod/main.py:298](src/csfd_vod/main.py) — existujúci pattern pre subcommands
