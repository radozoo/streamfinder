---
date: 2026-04-11
topic: dashboard-pipeline
---

# Dashboard Pipeline — Multi-value Fields & Data Architecture

## What We're Building

Statický HTML/D3 dashboard generovaný z PostgreSQL databázy.
Python skript (`build_dashboard.py`) spustí SQL agregácie a uloží výsledky ako JSON súbory.
D3 v `index.html` načíta JSON a vykreslí grafy.

## Pipeline

```
csfd parse → PostgreSQL → build_dashboard.py → data/*.json → index.html (D3)
```

## Why This Approach

Tri možnosti boli zvažované:
- **A: Statické JSON + D3** ← zvolené
- B: Embedded JSON v HTML (jeden súbor)
- C: FastAPI + live D3 (príliš komplexné pre týždenný pipeline)

Dôvod: Projekt je osobný, dáta sa menia týždenne pri re-parsovaní. Statické JSON je jednoduché, nevyžaduje server, dashboard funguje ako standalone HTML súbor.

## Key Decisions

- **Multi-value polia → dimension tabuľky:** `dim_genres`, `dim_actors`, `dim_directors`, `dim_countries`, `dim_vods`, `dim_tags`, `dim_screenwriters`, `dim_cinematographers`, `dim_composers` — už normalizované, GROUP BY agregácia priamo v SQL
- **Reviews:** JSONB v `fact_titles` — riešime neskôr v samostatnom brainstorme
- **Vizualizácie:** otvorená otázka — samostatný brainstorm

## Open Questions

- Aké konkrétne grafy/vizualizácie chceme? (samostatný brainstorm)
- Ako často sa bude dashboard regenerovať? (manuálne vs. cron)
- Kde bude dashboard hostovaný? (lokálne / GitHub Pages / iné)

## Next Steps

→ `/cde:plan` pre implementáciu `build_dashboard.py` a JSON schémy
→ Brainstorm vizualizácií (samostatne)
