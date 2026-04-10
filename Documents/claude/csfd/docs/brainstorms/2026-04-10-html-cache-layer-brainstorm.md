---
title: HTML Cache Layer for CSFD VOD Scraping Pipeline
type: feat
status: active
date: 2026-04-10
---

# HTML Cache Layer for CSFD VOD Scraping Pipeline

## What We're Building

Oddelenie scrapingu od parsovania pomocou HTML cache na disku. Namiesto toho, aby pipeline scrapeoval stránku a ihneď ju parsoval (a zahodil HTML), zavedieme dva kroky:

1. **`csfd scrape`** — stiahne HTML pre každú stránku a uloží ju na disk do `cache/html/`
2. **`csfd parse`** — načíta HTML súbory z disku, spustí parsovanie a nahrá dáta do DB

Cieľom je umožniť iteratívne ladenie CSS selektorov bez nutnosti znova kontaktovať server.

---

## Prečo Tento Prístup

**Hlavný problém:** Keď sú selektory zlé (nesprávne CSS triedy, chýbajúce polia), musíme celý scraping spustiť znova — Playwright, rate limiting, 82+ stránok, ~10-15 minút čakania. To spomaľuje ladenie.

**Riešenie:** Raz stiahneme HTML, uložíme lokálne, a potom môžeme `csfd parse` spúšťať ľubovoľne rýchlo bez internetu a bez záťaže na csfd.cz.

---

## Kľúčové Rozhodnutia

| Téma | Rozhodnutie | Dôvod |
|------|-------------|-------|
| **Primárny účel** | Offline ladenie parserov | Nie optimalizácia produkčných behov |
| **CLI** | Dve separátne príkazy | `csfd scrape` + `csfd parse` — jasné oddelenie zodpovednosti |
| **Formát cache** | `.html` súbory | Jednoduché, prehliadateľné v browseri, žiadna extra vrstva |
| **Cesta** | `cache/html/{url_hash}.html` | Hash z URL = unikátny kľúč, ľudsky nečitateľný ale funkčný |
| **Invalidácia** | Manuálna | Cache je trvalá, kým ju manuálne nevymažeš — ideálne pre ladenie |

---

## Navrhovaná Štruktúra

```
cache/
  html/
    a1b2c3d4.html      # HTML stránky https://csfd.cz/film/12345/
    e5f6a7b8.html      # HTML stránky https://csfd.cz/film/67890/
    ...
  urls.json            # Zoznam URL → hash mapovanie (pre debugovanie)
```

**Pomenovanie súborov:** MD5 alebo SHA1 hash z URL → `cache/html/{hash}.html`

Súbor `cache/urls.json` je nepovinný pomocný index:
```json
{
  "https://csfd.cz/film/12345/titanic/": "a1b2c3d4",
  "https://csfd.cz/film/67890/avatar/": "e5f6a7b8"
}
```

---

## CLI Rozhranie

```bash
# Krok 1: Scrape — stiahne VOD zoznam + HTML všetkých stránok
csfd scrape [--url URL]

# Krok 2: Parse — načíta z cache, parsuje, nahrá do DB
csfd parse [--dry-run]

# Celý pipeline naraz (pre produkciu)
csfd run [--url URL] [--dry-run]
```

**`csfd scrape`:**
- Stage 1: Stiahne zoznam URL z VOD stránky (Playwright)
- Stage 2: Pre každú URL stiahne HTML a uloží do `cache/html/`
- Uloží index URL → hash do `cache/urls.json`
- Koniec — žiadne parsovanie, žiadna DB

**`csfd parse`:**
- Načíta `cache/urls.json` (zoznam čo máme v cache)
- Pre každý súbor načíta HTML z disku
- Spustí parser → VODTitle objekty
- Nahrá do DB (alebo `--dry-run` pre zobrazenie výsledkov)

---

## Čo Sa Nemení

- `VODScraper` — Playwright logika zostáva rovnaká
- `VODTitleParser` — CSS selektory, parsovanie zostáva rovnaké
- `PostgresLoader` — upsert logika zostáva rovnaká
- `config/selectors.json` — selektory sa len menia pri ladení

---

## Open Questions

Žiadne — všetky kľúčové rozhodnutia sú vyjasnené.

---

## Resolved Questions

- **Primárny účel?** → Offline ladenie parserov
- **CLI?** → Dve separátne príkazy (`scrape` + `parse`)
- **Formát?** → `.html` súbory na disku
- **Invalidácia?** → Manuálna (trvalá cache)
