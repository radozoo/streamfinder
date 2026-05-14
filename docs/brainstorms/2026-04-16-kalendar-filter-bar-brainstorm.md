---
title: "Kalendár: unifikácia filtrovania s katalógom"
date: 2026-04-16
status: draft
feature: filter-bar-on-calendar
components: [FilterBar, kalendar/+page.svelte, kalendar/+page.ts]
---

# Kalendár: unifikácia filtrovania s katalógom

## Čo budujeme

Pridáme plnohodnotný `FilterBar` komponent na stránku `/kalendar` — rovnaký, aký má `/katalog`. Filtre budú nezávislé od katalógu (každá záložka má vlastný stav), persistované v URL, a aplikované na 28-dňový timeline VOD release-ov.

## Prečo to chceme

Aktuálny kalendár má len 3 jednoduché single-select filtre (platforma, typ, žáner) bez URL persistovania. Používateľ nemôže filtrovať podľa hodnotenia, roku, krajiny, tagov ani Tvůrci priamo z kalendára — musí prepínať do katalógu. Zjednotením UX sa navigácia zjednoduší a obe záložky budú konzistentné.

## Rozhodnutia

### Zdieľanie filtrov medzi záložkami
**Rozhodnutie: Nezávislý stav.** Každá záložka má vlastné filtre. Zmena v katalógu neovplyvní kalendár a naopak. Dôvod: obe záložky majú odlišný kontext (objavovanie vs. timeline) a zdieľaný stav by mátol používateľa.

### Ktoré filtre
**Rozhodnutie: Všetky z katalógu** — Platforma, Typ, Žáner, Krajina, Tagy, Rok vydania, Hodnotenie. Crew (Tvůrci) je open question (pozri nižšie). Sort nie je relevantný — kalendár je vždy triedený chronologicky.

### Prázdne dni pri filtrovaní
**Rozhodnutie: Zobraziť prázdne dni.** Ak deň nemá žiadne vyhovujúce tituly, zobrazí sa s prázdnym stavom (napr. "Žiadne tituly pre tieto filtre"). Zachová sa kontinuita časovej osi.

### URL persistovanie
**Rozhodnutie: Áno.** Filtre sa serializujú do URL params ako v katalógu. Parametre sú rovnaké (`?genre=&platform=&...`), ale stránka je `/kalendar` — žiadny konflikt.

## Technický prístup

**Priame reuse `FilterBar` komponentu** — žiadne zmeny v existujúcich komponentoch.

### Čo sa mení

**`streamfinder/src/routes/kalendar/+page.ts`**
- Parsovanie URL params rovnako ako `katalog/+page.ts`
- Vrátenie `initialGenres`, `initialPlatforms`, `initialCountries`, `initialTags`, `initialType`, `initialYearFrom`, `initialYearTo`, `initialRatingMin`

**`streamfinder/src/routes/kalendar/+page.svelte`**
- Pridať filter state (`$state`) — rovnaký pattern ako katalóg (~30 riadkov)
- Pridať `$derived.by` na filtrovanie titulov (existujúca logika z katalógu, len bez `q` a `sort`)
- Pridať `FilterBar` komponent (importovať, vložiť nad timeline)
- Pridať URL sync (`history.replaceState`) rovnaký pattern
- Hit indicátory: vypočítané z aktuálne filtrovaných titulov (subset 28-dňového okna)
- Optionally: `ActiveFilters` chips pod FilterBar-om

**Žiadne zmeny v:**
- `FilterBar.svelte`
- `FilterDropdown.svelte`
- `+layout.svelte` / `+layout.ts`
- Katalóg stránka

### Hit indicátory na kalendári

V katalógu hit indicátory ukazujú, ktoré možnosti majú aspoň 1 titul zodpovedajúci ostatným (nie aktívnym) filtrom. Na kalendári budú hit indicátory vypočítané z titulov v 28-dňovom okne, ktoré zodpovedajú ostatným filtrom — ten istý princíp, len s iným zdrojovým datasetom.

### Dátové flow

```
+layout.ts → titles[] + dimensions{}
     ↓
+page.ts → parse URL params → initialXxx props
     ↓
+page.svelte
  $state: selectedGenres, selectedPlatforms, ...
  $derived.by: filteredTitles (subset titulov v 28-dňovom okne)
  $derived: hitGenres, hitPlatforms, ... (z filteredTitles)
  FilterBar ← všetky props
  Timeline ← filteredTitles zoskupené podľa dátumu
```

## Open Questions

_Žiadne._

## Resolved Questions

- Zdieľaný vs. nezávislý stav → **nezávislý**
- Prázdne dni → **zobraziť** (zachová kontinuitu časovej osi)
- URL persistovanie → **áno**
- Scope filtrov → **Platforma, Typ, Žáner, Krajina, Tagy, Rok, Hodnotenie** (Sort nie — kalendár je vždy chronologický; Crew vynecháme)
- Crew filter → **vynechať** — lazy-loading overhead nie je opodstatnený pre kalendár
- Empty state pre celú stránku → **áno** — ak 0 výsledkov vo všetkých dňoch, zobraziť správu "Žiadne tituly nevyhovujú filtrom"

## Implementačný rozsah

| Súbor | Zmena | Odhad |
|---|---|---|
| `kalendar/+page.ts` | URL param parsing (copy-paste z katalógu, odstraniť `q` a `sort`) | ~20 riadkov |
| `kalendar/+page.svelte` | Filter state + derived + FilterBar + URL sync | ~80 riadkov |
| `FilterBar.svelte` | Žiadna zmena | — |
| Ostatné komponenty | Žiadna zmena | — |

Celkový rozsah: **malý** (~100 riadkov nového kódu, žiadne refaktory).
