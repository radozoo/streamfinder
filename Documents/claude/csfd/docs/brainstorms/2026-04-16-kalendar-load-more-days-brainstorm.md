---
title: "Kalendár: zobraz ďalšie dni (rozšírenie okna)"
date: 2026-04-16
status: draft
feature: calendar-load-more-days
components: [kalendar/+page.svelte, kalendar/+page.ts]
---

# Kalendár: zobraz ďalšie dni

## Čo budujeme

Tlačidlo "Zobraz ďalšie dni" na konci timeline-u. Každé kliknutie rozšíri okno o +14 dní dozadu do histórie. Maximum je 365 dní (1 rok). Aktuálna hĺbka okna sa persistuje do URL (`?days=42`).

## Prečo to chceme

Aktuálny limit 28 dní je hardkódovaný konštantou. Používateľ nemá žiadnu možnosť pozrieť sa na staršie VOD príchody — napríklad čo prišlo pred 2 mesiacmi na Netflix. Jednoduchým tlačidlom na spodku stránky rozšírime hodnotu bez zmeny celkovej štruktúry UI.

## Rozhodnutia

| Otázka | Rozhodnutie |
|---|---|
| Krok rozšírenia | +14 dní na kliknutie |
| Maximálny limit | 365 dní (1 rok) |
| URL persistovanie | Áno — `?days=42` |
| Výchozí stav | 28 dní (nezmenené správanie) |

## Technický prístup

Minimálna zmena — jeden reaktívny stav navyše, žiadne nové komponenty.

### Zmeny

**`kalendar/+page.ts`**
- Parsovanie `?days` URL param (číslo, clamped 28–365)
- Vrátenie `initialDays: number`

**`kalendar/+page.svelte`**
- `DAYS_BACK` zo `const` → `let daysBack = $state(data.initialDays)` (default 28)
- `MIN_DATE` a `ALL_DATES` zmenia na `$derived` (závisia od `daysBack`)
- Po kliknutí: `daysBack = Math.min(daysBack + 14, 365)` + URL sync
- Tlačidlo na spodku timeline-u: zobrazené ak `daysBack < 365`
- Tlačidlo skryté / nahradené textom "Zobrazuje sa celý rok" keď `daysBack >= 365`

### Žiadne zmeny v:
- `+layout.ts` / `+layout.svelte`
- Žiadnych komponentoch
- Katalóg stránka

## Rozsah

| Súbor | Zmena | Odhad |
|---|---|---|
| `kalendar/+page.ts` | Parsovanie `?days` param | ~5 riadkov |
| `kalendar/+page.svelte` | State + derived + button + URL sync | ~20 riadkov |

**Celkový rozsah: veľmi malý** (~25 riadkov, žiadne nové súbory).

## Open Questions

_Žiadne._

## Resolved Questions

- Krok rozšírenia → **+14 dní**
- Maximálny limit → **365 dní**
- URL persistovanie → **áno** (`?days=N`)
- Výchozí správanie → **zachované** (28 dní ak `?days` nie je v URL)
