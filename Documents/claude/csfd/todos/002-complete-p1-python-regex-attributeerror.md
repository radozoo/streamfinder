---
status: complete
priority: p1
issue_id: "002"
tags: [code-review, python, bug]
---

# re.search().group(1) can raise AttributeError

## Problem Statement
In `_build_detail`, `re.search(r"v=([^&]+)", t["trailer_url"]).group(1)` will raise `AttributeError` if the search returns None.

## Findings
- **File:** `src/csfd_vod/export/streamfinder_exporter.py` lines 322–327

## Fix
```python
match = re.search(r"v=([^&]+)", t["trailer_url"] or "")
trailer = tmdb.get("trailer_youtube_id") or (match.group(1) if match else None)
```

Also fix `datetime.utcnow()` deprecated in Python 3.12+:
```python
from datetime import datetime, timezone
datetime.now(tz=timezone.utc).isoformat()
```

## Acceptance Criteria
- [ ] Export runs without error on titles with malformed trailer_url
- [ ] No use of `datetime.utcnow()`
