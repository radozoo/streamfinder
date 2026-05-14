---
status: pending
priority: p2
issue_id: "003"
tags: [code-review, security, python]
---

# Security: SQL allowlist + YouTube ID + VOD URL validation

## Problem Statement
Three security hygiene issues in the exporter that should be fixed before data corruption or injection is possible.

## Findings

### 1. SQL identifier interpolation in `_load_dim` (line 143)
`f"SELECT title_id, {col} FROM csfd_vod.{table}"` — col/table are internal constants today, but no guard prevents future misuse.

**Fix:** Add allowlist check:
```python
_ALLOWED_DIMS = {"dim_genres": "genre", "dim_tags": "tag", ...}
def _load_dim(self, session, table, col):
    if _ALLOWED_DIMS.get(table) != col:
        raise ValueError(f"Unknown dimension: {table!r}/{col!r}")
```

### 2. Unvalidated YouTube ID in iframe src (line 322 + TitleModal.svelte:123)
`trailer_youtube_id` written to JSON without format validation, then embedded in iframe URL.

**Fix:**
```python
_YT_ID_RE = re.compile(r'^[A-Za-z0-9_\-]{6,20}$')
if trailer and not _YT_ID_RE.match(trailer):
    trailer = None
```

### 3. VOD URLs not scheme-validated (line 151, TitleModal.svelte:104)
`vod.url` rendered directly in `<a href>`. A `javascript:` URL from a bad scrape would execute.

**Fix:**
```python
if url and not url.startswith("https://"):
    url = None
```

## Acceptance Criteria
- [ ] `_load_dim` raises ValueError for unknown table/col combos
- [ ] `trailer_youtube_id` validated to `[A-Za-z0-9_-]{6,20}` before export
- [ ] VOD URLs must start with `https://` or are nulled out
