---
status: pending
priority: p2
issue_id: "011"
tags: [code-review, python, bug, regex]
dependencies: []
---

# Python: YouTube regex `[^&]+` captures URL fragment, produces invalid ID

## Problem Statement
The YouTube ID extraction regex `r"v=([^&#]+)"` in `streamfinder_exporter.py` correctly stops at `&` (query param separator) but does NOT stop at `#` (fragment separator). A URL like `https://youtube.com/watch?v=dQw4w9WgXcW#t=30` would produce `dQw4w9WgXcW#t=30` as the captured YouTube ID — an invalid ID that would silently fail to load in an embed.

## Findings
- **File:** `src/csfd_vod/export/streamfinder_exporter.py` line 322
- **Current:** `re.search(r"v=([^&]+)", t.get("trailer_url") or "")`
- **Problem:** `[^&]` does not exclude `#`, so URL fragments are captured as part of the ID
- **Impact:** Titles with fragment-containing trailer URLs get invalid YouTube IDs in `titles_detail.json`, causing broken trailer embeds in the frontend

## Proposed Solutions

### Option A: Add `#` to the negated character class (Recommended)

```python
_yt_match = re.search(r"v=([^&#]+)", t.get("trailer_url") or "")
trailer = tmdb.get("trailer_youtube_id") or (_yt_match.group(1) if _yt_match else None)
```

One character change. Minimal risk.

- **Effort:** Tiny
- **Risk:** None

### Option B: Parse with `urllib.parse`

```python
from urllib.parse import urlparse, parse_qs
_parsed = urlparse(t.get("trailer_url") or "")
_yt_id = parse_qs(_parsed.query).get("v", [None])[0]
trailer = tmdb.get("trailer_youtube_id") or _yt_id
```

More robust — handles all URL edge cases correctly.

- **Pros:** Cannot produce malformed IDs; handles edge cases (empty param, multiple `v=` values)
- **Cons:** More verbose; adds an import
- **Effort:** Small
- **Risk:** Low

## Recommended Action
Option A — one-character fix, correct for the known URL format. Option B is overkill for scraping output where URL format is known.

**Also fix in same commit:** Rename `_yt_match` → `yt_match` (leading underscore is non-idiomatic for a local variable in Python).

## Technical Details
- **File:** `src/csfd_vod/export/streamfinder_exporter.py` line 322
- **Combined fix:**
  ```python
  yt_match = re.search(r"v=([^&#]+)", t.get("trailer_url") or "")
  trailer = tmdb.get("trailer_youtube_id") or (yt_match.group(1) if yt_match else None)
  ```

## Acceptance Criteria
- [ ] Trailer URL `?v=abc123#t=30` produces YouTube ID `abc123` (not `abc123#t=30`)
- [ ] Trailer URL `?v=abc123&foo=bar` still produces `abc123`
- [ ] Trailer URL without `v=` produces `None` (no AttributeError)

## Work Log
- 2026-04-16: Identified by Python reviewer
