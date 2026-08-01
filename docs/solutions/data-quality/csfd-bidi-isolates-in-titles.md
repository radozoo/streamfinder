---
id: "2026-08-01-csfd-bidi-isolates-in-titles"
date: "2026-08-01"
project: "csfd/streamfinder"
scope:
  - "src/csfd_vod/transformation/parser.py"
  - "streamfinder/src/lib/components/PosterCard.svelte"
  - "csfd_vod.fact_titles.title (PostgreSQL)"
guard: "check_data_quality.py::check_control_chars, check_data_quality.py::check_whitespace"
tags:
  - data-quality
  - scraping
  - unicode
  - text-normalisation
---

# Invisible bidi isolates and stray whitespace in scraped titles

## Symptom

Episode names rendered with a stray character before the first letter and would
not match string comparisons that should obviously have succeeded. On screen it
looked like a subtle indent or nothing at all; in the data it looked like this:

```
'⁨Križovatka úspechu\n\t\t\t\t\t\t\t\t (E07)'
'Paměť\n\t\t\t\t\t\t\t\t (S03E05)'
```

22 titles carried the invisible characters; 12 073 carried the stray whitespace.

## Root Cause

Two separate things arriving from the same `<h1>`:

1. **Bidi isolates.** ČSFD wraps some episode names in `U+2068` (FIRST STRONG
   ISOLATE) / `U+2069` (POP DIRECTIONAL ISOLATE) — legitimate Unicode for mixed
   left-to-right/right-to-left text, invisible when rendered, but they are real
   characters that survive `.strip()` and break equality checks.

2. **Multi-line markup.** The `(S03E05)` marker sits on its own indented line
   inside the same `<h1>`. `get_text(strip=True)` strips the *ends* of the whole
   string, not the whitespace *between* nodes, so the newline and tabs survived
   into the database.

The parser stored the `<h1>` text as-is, so both leaked through every downstream
consumer: card headlines, detail pages, search, and the exported JSON.

## Fix

Normalise once, at the point of extraction — everything downstream inherits it:

```python
raw = title_elem.get_text(strip=True)
raw = re.sub(r"[⁦-⁩‎‏]", "", raw)
data["title"] = re.sub(r"\s+", " ", raw).strip()
```

The `(SxxEyy)` marker is deliberately **kept** — the season/episode parser below
reads the numbers back out of the title string. Verified against cached HTML that
`S(\d+)E(\d+)` and `\(E(\d+)\)` still match after collapsing.

`PosterCard.svelte` strips the same character class defensively, so an old export
or a future regression cannot put invisible characters back on screen.

## Why it went unnoticed

Nothing errored. The characters are invisible by design and the whitespace only
showed up once a title was rendered next to something else. No check looked at the
*content* of a field — only at whether the field existed.

## Prevention

- [ ] Any text scraped from HTML is whitespace-collapsed at extraction, not at render
- [ ] Control/format characters are stripped before storage, not filtered in the UI
- [ ] `check_data_quality.py` fails the deploy on either class appearing in the export
