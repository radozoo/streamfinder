---
status: pending
priority: p3
issue_id: "007"
tags: [code-review, svelte, simplicity]
---

# Simplification: unused label prop, typeOptions conversion, URL param caps

## Findings

### 1. `label` prop in RangeSlider is unused
No call site passes `label`. Remove the prop + `{#if label}` block + `.range-label` CSS. ~10 lines.

### 2. `typeOptions` converted twice
`+page.svelte` passes `string[]`, `FilterBar` converts to `{name, hit}[]`, mobile sheet converts again inline. Pass `{name: string; hit: boolean}[]` directly from the caller.

### 3. URL param length caps missing (`+page.ts`)
`?crew=A&crew=B` repeated thousands of times causes client-side DoS. Cap at load time:
```ts
const crewParams = url.searchParams.getAll('crew').slice(0, 20).map(s => s.slice(0, 100));
```

### 4. `$effect(() => { filtered; page = 1; })` anti-pattern
Reading a derived in an effect with no visible use is fragile. Add a comment at minimum, or reset `page` inside toggle handlers instead.

### 5. URL sync dirty-check before `replaceState`
Year slider fires `history.replaceState` on every drag position. Check if URL actually changed before calling:
```ts
const target = str ? '?' + str : location.pathname;
if (location.search !== (str ? '?' + str : '')) history.replaceState(null, '', target);
```

### 6. `PosterCard` duplicates inner card markup
The `{#if onclick}` branch duplicates `<img>`, rating, year, platform badge. Use a `{#snippet cardContent()}`.

## Acceptance Criteria
- [ ] `label` prop removed from RangeSlider
- [ ] `typeOptions` conversion in one place
- [ ] URL params capped
