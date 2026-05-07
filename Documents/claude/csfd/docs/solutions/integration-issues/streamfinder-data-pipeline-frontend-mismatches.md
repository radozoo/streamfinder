---
id: "2026-04-15-streamfinder-detail-404-broken-images"
date: "2026-04-15"
project: "csfd/streamfinder"
scope:
  - "src/csfd_vod/export/streamfinder_exporter.py"
  - "streamfinder/src/routes/titul/[id]/[slug]/+page.ts"
  - "csfd_vod.fact_titles.image_url (PostgreSQL)"
tags:
  - integration-issues
  - data-export
  - key-mismatch
  - url-parsing
  - sveltekit
  - static-site
---

# Streamfinder: Detail 404 + Broken Image URLs

Two integration bugs between the Python data pipeline and SvelteKit frontend, both caused by implicit contracts between producer and consumer.

## Bug 1: 404 on all title detail pages

### Symptom

Clicking any title from homepage or catalog showed "404 Titul nenalezen".

### Root Cause

`titles_detail.json` was keyed by `url_id` (the CSFD URL path identifier, e.g. `"1837113-prisoner"`), but the SvelteKit page loader at `/titul/[id]/[slug]/+page.ts` constructed the lookup key as `` `${params.id}-${params.slug}` `` where `params.id` is the numeric `title_id` and `params.slug` comes from the URL route. These are fundamentally different identifiers that never matched.

### Fix

Changed `streamfinder_exporter.py` `_build_detail()` to key by `f"{tid}-{slug}"`:

```python
# BEFORE:
detail[t["url_id"]] = {
    "slug": _slug(t["title"], t["year"]),

# AFTER:
slug = _slug(t["title"], t["year"])
detail[f"{tid}-{slug}"] = {
    "slug": slug,
```

Also fixed `_slug()` year guard from `if year:` to `if year is not None:` (year=0 would be falsy).

### Verification

```python
# All 6096 keys match after fix:
ok_all = sum(1 for t in idx if f"{t['id']}-{t['slug']}" in det)
# => 6096/6096
```

### Related commits

- `b13e942` feat(streamfinder): add TMDB enricher + Streamfinder JSON exporter (introduced bug)
- `5690d67` fix(data): re-export titles_detail keyed by {id}-{slug} (fixed)

---

## Bug 2: No poster images displayed

### Symptom

No poster images rendered on any page. 5928 of 6096 titles had `image_url` but all were broken.

### Root Cause

An older parser version (before commit `3390d79`) did not handle protocol-relative URLs (`//image.pmgstatic.com/...`). It blindly prepended `https://www.csfd.cz` to non-absolute URLs, producing `https://www.csfd.cz//image.pmgstatic.com/...` (wrong domain, double slash). The parser was already fixed in `3390d79` but 5928 rows of bad data remained in PostgreSQL.

### Fix

1. SQL backfill to correct existing data:

```sql
UPDATE csfd_vod.fact_titles
SET    image_url = REPLACE(image_url, 'https://www.csfd.cz//', 'https://')
WHERE  image_url LIKE 'https://www.csfd.cz//%';
-- Affected: 5928 rows
```

2. Re-export JSON:

```bash
csfd streamfinder --output-dir streamfinder/static/data
```

### Parser fix (already in place)

```python
# src/csfd_vod/transformation/parser.py lines 186-192
if src.startswith("http"):
    data["image_url"] = src                        # absolute
elif src.startswith("//"):
    data["image_url"] = "https:" + src             # protocol-relative
else:
    data["image_url"] = f"https://www.csfd.cz{src}" # relative path
```

### Related commits

- `3390d79` fix(parser): handle protocol-relative image URLs (parser fix)
- `627667b` fix(data): fix image URLs (strip wrong csfd.cz// prefix) + re-export (data fix)

---

## Lesson Learned

Both bugs stem from the same root problem: **implicit contracts between pipeline stages**.

- Bug 1: The JSON key format was assumed, not specified. The exporter used one convention (`url_id`), the frontend another (`{id}-{slug}`), and nothing enforced agreement.
- Bug 2: The parser produced malformed URLs silently. No validation existed at write time or read time. The bug was only visible on the deployed frontend.

## Prevention

### 1. Contract test: exported keys match frontend route pattern

```python
def test_detail_keys_match_svelte_route():
    detail = exporter._build_detail(...)
    for key, entry in detail.items():
        expected = f"{entry['id']}-{entry['slug']}"
        assert key == expected
```

### 2. URL validation at parse time

Extract URL handling into a `normalize_url()` function with explicit branches for absolute, protocol-relative, and relative URLs. Add a Pydantic field validator on `image_url` that rejects double-slash paths.

### 3. Post-export data quality check

```python
def validate_exported_json(detail: dict) -> list[str]:
    errors = []
    for key, title in detail.items():
        if not re.match(r"^\d+-[a-z0-9-]+$", key):
            errors.append(f"Bad key: {key}")
        for field in ("poster", "backdrop"):
            url = title.get(field)
            if url and "csfd.cz//" in url:
                errors.append(f"Malformed {field} URL: {url}")
    return errors
```

### 4. Cross-reference test: index entries must resolve in detail

```python
def test_index_resolves_in_detail():
    for item in index:
        key = f"{item['id']}-{item['slug']}"
        assert key in detail
```

## Cross-references

- Plan: `docs/plans/2026-04-12-feat-streamfinder-vod-discovery-app-plan.md` (Phase 4: exporter, Phase 8b: detail page)
- Brainstorm: `docs/brainstorms/2026-04-10-parsing-field-definitions-brainstorm.md` (image_url selector definition)
- Brainstorm: `docs/brainstorms/2026-04-12-streamfinder-dashboard-brainstorm.md` (TMDB fallback chain)
