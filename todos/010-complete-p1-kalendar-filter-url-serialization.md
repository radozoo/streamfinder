---
status: pending
priority: p1
issue_id: "010"
tags: [code-review, svelte, sveltekit, kalendar, url-params, agent-native]
dependencies: []
---

# Kalendár: filter state (platforma/typ/žáner) nie je URL-serializovaný

## Problem Statement
Kalendár má tri filtre (`selectedPlatform`, `selectedType`, `selectedGenre`) ktoré existujú iba ako lokálny `$state`. Na rozdiel od `?days=N`, tieto filtre sa nikdy nezapíšu do URL a nikdy sa z URL nečítajú. Používateľ, ktorý nastaví filtre a zdieľa link, dostane link bez filtrov. Agent, ktorý chce reprodukovať zobrazenie, nemôže.

Katalóg má vzorové riešenie (URL params + `$effect` sync) — kalendár by mal rovnakú konzistenciu.

**Súvisí s brainstorm dokumentom:** `docs/brainstorms/2026-04-16-kalendar-filter-bar-brainstorm.md` — URL persistovanie bolo explicitne rozhodnuté ako "áno".

## Findings
- **File:** `streamfinder/src/routes/kalendar/+page.svelte` lines 53–56 (filter state) + 66–83 (filter usage)
- **File:** `streamfinder/src/routes/kalendar/+page.ts` — číta iba `?days`, nie `?platform`, `?type`, `?genre`
- Katalóg (`katalog/+page.ts` + `katalog/+page.svelte`) má kompletný vzor na kopírovanie

## Proposed Solutions

### Option A: Port catalog URL pattern to calendar (Recommended)

**`kalendar/+page.ts`** — pridať čítanie 3 nových params:
```ts
export const load: PageLoad = async ({ parent, url }) => {
    const { titles, dimensions } = await parent();
    const daysParam = Number(url.searchParams.get('days') ?? 28);
    const initialDays = Math.min(Math.max(daysParam, 28), 365);
    return {
        titles,
        dimensions,
        initialDays,
        initialPlatform: url.searchParams.get('platform') ?? '',
        initialType:     url.searchParams.get('type')     ?? '',
        initialGenre:    url.searchParams.get('genre')    ?? '',
    };
};
```

**`kalendar/+page.svelte`** — inicializovať z `data` + `$effect` URL sync:
```ts
let selectedPlatform = $state(untrack(() => data.initialPlatform));
let selectedType     = $state(untrack(() => data.initialType));
let selectedGenre    = $state(untrack(() => data.initialGenre));

$effect(() => {
    const params = new URLSearchParams();
    if (daysBack !== 28)         params.set('days',     String(daysBack));
    if (selectedPlatform)        params.set('platform', selectedPlatform);
    if (selectedType)            params.set('type',     selectedType);
    if (selectedGenre)           params.set('genre',    selectedGenre);
    const qs = params.toString();
    history.replaceState(null, '', qs ? '?' + qs : location.pathname);
});
```

- **Pros:** Konzistentné s katalógom; agent-accessible; zdieľateľné linky
- **Cons:** Mierne väčší `+page.ts`
- **Effort:** Small (~20 riadkov)
- **Risk:** Low

### Option B: Nechať na neskorší brainstorm (Filter Bar refactor)
Brainstorm `2026-04-16-kalendar-filter-bar-brainstorm.md` plánuje pridať celý `FilterBar` na kalendár. URL serialization príde automaticky s tou refaktorom.

- **Pros:** Nič nerobiť teraz; jeden koordinovaný commit
- **Cons:** Filter bar refactor je väčší feature; toto je malý izolovaný fix
- **Effort:** None now
- **Risk:** Medium — brainstorm môže byť odložený dlho

## Recommended Action
Option A ak sa FilterBar refactor nepriblíži v krátkom čase. Option B ak je FilterBar refactor naplánovaný na tento sprint.

## Technical Details
- **Files:** `streamfinder/src/routes/kalendar/+page.ts`, `streamfinder/src/routes/kalendar/+page.svelte`
- **Reference:** `streamfinder/src/routes/katalog/+page.ts` lines 1–20 (vzor)
- **Related brainstorm:** `docs/brainstorms/2026-04-16-kalendar-filter-bar-brainstorm.md`

## Acceptance Criteria
- [ ] `?platform=Netflix` v URL nastaví selectedPlatform na "Netflix" pri načítaní
- [ ] Zmena filtra zapíše URL param bez reloadu
- [ ] Zdieľaný link s `?days=42&genre=Drama` zobrazí kalendár s 42 dňami filtrovaný na Drama
- [ ] Prázdne filtre neproducujú `?platform=` prázdny param v URL

## Work Log
- 2026-04-16: Identifikované agent-native reviewerom (P1); súvisí s brainstorm rozhodnutím
