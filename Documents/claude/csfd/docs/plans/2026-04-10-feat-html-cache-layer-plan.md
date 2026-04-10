---
title: "feat: Add HTML Cache Layer with Scrape/Parse CLI Split"
type: feat
status: completed
date: 2026-04-10
origin: docs/brainstorms/2026-04-10-html-cache-layer-brainstorm.md
---

# feat: Add HTML Cache Layer with Scrape/Parse CLI Split

## Overview

Oddelenie scrapingu od parsovania zavedením HTML cache na disku a refaktoringom CLI na tri subpríkazy: `scrape`, `parse`, `run`.

**Hlavný cieľ:** Umožniť iteratívne ladenie CSS selektorov offline — stiahnuť HTML raz, potom `csfd parse` spúšťať ľubovoľne rýchlo bez internetu a bez záťaže na server. (see brainstorm: docs/brainstorms/2026-04-10-html-cache-layer-brainstorm.md)

## Problem Statement / Motivation

Keď sú selektory zlé (chýbajúce polia, nesprávne CSS triedy), musíme celý scraping spustiť znova — Playwright + rate limiting + 82 stránok = ~15 minút čakania. To robí ladenie selektorov nepraktickým.

## Proposed Solution

### Nový modul: `HTMLCache`

Jednoduchý file-based cache: URL → `cache/html/{md5_hash}.html`. Index URL→hash v `cache/urls.json`.

```
cache/
  html/
    a1b2c3d4.html    # HTML stránky csfd.cz/film/12345/
    e5f6a7b8.html
  urls.json          # {"https://csfd.cz/film/12345/": "a1b2c3d4", ...}
```

### Refaktoring CLI: 3 subpríkazy

```bash
csfd scrape [--url URL]           # Stiahne HTML → cache/html/
csfd parse [--dry-run]            # Číta z cache → parsuje → DB
csfd run   [--url URL] [--dry-run] # Pôvodné správanie (scrape + parse bez cache)
```

## Technical Considerations

### Nové súbory

**`src/csfd_vod/cache/html_cache.py`** — nová trieda `HTMLCache`:
- `has(url) -> bool` — skontroluje či je URL v cache
- `get(url) -> Optional[str]` — načíta HTML zo súboru
- `save(url, html)` — uloží HTML + aktualizuje `urls.json` index
- `all_urls() -> List[str]` — zoznam URL v cache (pre `parse` príkaz)
- `_url_hash(url) -> str` — MD5 hash prvých 8 znakov

### Zmenené súbory

**`src/csfd_vod/config.py`**:
- Pridať `cache_dir: str = "cache"` do `PipelineConfig`
- Načítať z env var `CACHE_DIR` v `load_config_from_env()`

**`src/csfd_vod/main.py`** — refaktoring `main()` na subpríkazy:
- `cmd_scrape(args)` — Stage 1 (URL list) + Stage 2 (HTML download + cache save), skip ak `cache.has(url)`
- `cmd_parse(args)` — načíta `cache.all_urls()`, parsuje z `cache.get(url)`, nahrá do DB
- `cmd_run(args)` — zachová pôvodný `run_pipeline()` bez cache (pre produkčné použitie)
- Použiť `argparse` subparsers (vzor: pridať `subparsers = parser.add_subparsers(dest="command", required=True)`)

**`.gitignore`** — pridať `cache/`

### Vzory z existujúcej kódovej základne

- Disk I/O vzor: `Path(cache_dir).mkdir(parents=True, exist_ok=True)` — pozri `src/csfd_vod/export/exporter.py:72`
- Config vzor: env var načítanie — pozri `src/csfd_vod/config.py:60-83`
- Logging vzor: `logger.info("cache_hit", url=url)` — pozri `src/csfd_vod/logger.py`

### System-Wide Impact

- **Interaction graph:** `cmd_scrape` volá `scraper.scrape_title_details()` → `cache.save()` → disk. `cmd_parse` volá `cache.get()` → `parser.parse()` → `loader.load_titles()`. Žiadne nové callbacks ani middleware.
- **Error propagation:** `cache.get()` vracia `None` ak súbor chýba (rovnaký vzor ako `scrape_title_details()`). `cmd_parse` skipuje `None` HTML.
- **State lifecycle risks:** `cmd_scrape` je idempotentný — skip ak `cache.has(url)`. Čiastočné prerušenie zanechá čiastočnú cache, ďalší beh doplní chýbajúce URL.
- **API surface parity:** `csfd run` zachová pôvodné správanie `run_pipeline()` — existujúce CI/cron skripty netreba meniť.

## Acceptance Criteria

- [x] `csfd scrape` stiahne HTML pre všetky VOD tituly a uloží do `cache/html/{hash}.html`
- [x] `csfd scrape` uloží URL→hash index do `cache/urls.json`
- [x] `csfd scrape` preskočí URL ktoré už sú v cache (idempotentné)
- [x] `csfd parse` načíta HTML z cache a parsuje bez sieťových požiadaviek
- [x] `csfd parse --dry-run` zobrazí parsované výsledky bez nahrávania do DB
- [x] `csfd run` zachová pôvodné správanie (scrape + parse bez cache)
- [x] `cache/` pridané do `.gitignore`
- [x] Cache adresár konfigurovateľný cez `CACHE_DIR` env var (default: `cache/`)
- [x] `csfd scrape` loguje `cache_hit` pre preskočené URL, `cache_saved` pre nové

## Dependencies & Risks

- **Žiadne nové závislosti** — používa len stdlib (`hashlib`, `json`, `pathlib`)
- **Riziko:** Veľkosť cache — 82 HTML súborov × ~200KB = ~16MB (zanedbateľné)
- **Riziko:** Zlomené HTML v cache — `csfd scrape --force` (voliteľné rozšírenie) by prepísalo cache; zatiaľ manuálne `rm -rf cache/`

## Implementation Order

1. `src/csfd_vod/cache/__init__.py` + `html_cache.py` — `HTMLCache` trieda
2. `src/csfd_vod/config.py` — pridať `cache_dir` do `PipelineConfig`
3. `src/csfd_vod/main.py` — refaktoring na subpríkazy
4. `.gitignore` — pridať `cache/`
5. Verify: `csfd scrape` → kontrola `cache/` na disku → `csfd parse --dry-run`

## Verification

```bash
# 1. Scrape — stiahne HTML do cache/
python -m csfd_vod.main scrape
# Očakávaný výstup: "cache_saved" log pre každú URL, cache/ adresár vzniknutý

# 2. Skontroluj cache na disku
ls cache/html/ | wc -l   # Mal by byť ~82
cat cache/urls.json | python -m json.tool | head -20

# 3. Parse offline (bez internetu ak treba)
python -m csfd_vod.main parse --dry-run
# Očakávaný výstup: parsované tituly bez DB zápisu

# 4. Parse + load do DB
python -m csfd_vod.main parse
# Skontroluj: SELECT count(*) FROM csfd_vod.fact_titles;

# 5. Scrape znovu — musí byť idempotentné (všetky cache_hit)
python -m csfd_vod.main scrape
# Očakávaný výstup: iba "cache_hit" logy, žiadny nový request
```

## Sources & References

- **Origin brainstorm:** [docs/brainstorms/2026-04-10-html-cache-layer-brainstorm.md](../brainstorms/2026-04-10-html-cache-layer-brainstorm.md) — Rozhodnutia: dve CLI príkazy, .html súbory, manuálna invalidácia
- Disk I/O vzor: `src/csfd_vod/export/exporter.py:72`
- Config vzor: `src/csfd_vod/config.py:60-83`
- CLI subparsers vzor: argparse docs — `add_subparsers(dest="command", required=True)`
