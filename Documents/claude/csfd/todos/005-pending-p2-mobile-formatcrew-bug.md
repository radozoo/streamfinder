---
status: pending
priority: p2
issue_id: "005"
tags: [code-review, svelte, bug]
---

# Mobile sheet formatItem lambda produces "(, )" when role/count empty

## Problem Statement
The inline `formatItem` lambda in the mobile sheet differs from the desktop `formatCrew` function and has a bug: when `role` and `count` are nullish it produces `"John Doe (, )"`.

## Findings
- **File:** `streamfinder/src/routes/katalog/+page.svelte` line 447
```ts
formatItem={(item) => `${item.name} (${item.role ?? ''}, ${item.count ?? ''})`}
```
When both are null: `"John Doe (, )"`

The desktop `FilterBar.svelte` has `formatCrew()` that correctly handles missing fields.

## Fix
Extract `formatCrew` from `FilterBar.svelte` into `+page.svelte` (or a shared `$lib/utils/formatCrew.ts`) and use it in both places:
```ts
function formatCrew(item: { name: string; role?: string; count?: number }) {
    const parts = [item.name];
    if (item.role) parts.push(`(${item.role}`);
    if (item.count !== undefined && item.role) parts[parts.length - 1] += `, ${item.count}`;
    if (item.role) parts[parts.length - 1] += ')';
    return parts.join(' ');
}
```

## Acceptance Criteria
- [ ] Mobile sheet crew items display without "(, )" when role/count missing
- [ ] One shared `formatCrew` function, not two
