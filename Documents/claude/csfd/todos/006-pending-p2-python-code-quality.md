---
status: pending
priority: p2
issue_id: "006"
tags: [code-review, python, quality]
---

# Python exporter: Counter imports, session context manager, slug duplication, _ROLE_MAP

## Problem Statement
Several quick-win quality issues in `streamfinder_exporter.py` that improve correctness and readability.

## Findings — all in `src/csfd_vod/export/streamfinder_exporter.py`

### 1. `Counter` imported inside two method bodies (lines 200, 368)
Move `from collections import Counter` to the top-level import block.

### 2. Session managed with `try/finally` instead of context manager (lines 55–110)
```python
# Replace:
session = self.SessionLocal()
try: ... finally: session.close()
# With:
with self.SessionLocal() as session: ...
```

### 3. `_slug` recomputed twice per title (lines 273, 328)
Pre-compute once: `t["slug"] = _slug(t["title"], t["year"])` after loading titles.

### 4. `_ROLE_MAP` defined inside method (line 202)
Move to module-level constant `_CREW_ROLE_MAP`.

### 5. `_load_titles` manual `zip(cols, row)` — use `.mappings()` (line 133)
```python
for row in session.execute(sql).mappings():
    d = dict(row)
```
Eliminates the `cols` list that can silently drift from the SQL.

## Acceptance Criteria
- [ ] `Counter` import at module level
- [ ] Session uses context manager
- [ ] `_slug` computed once per title
- [ ] `_ROLE_MAP` at module level
- [ ] `_load_titles` uses `.mappings()`
