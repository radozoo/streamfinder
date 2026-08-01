---
id: "2026-08-01-cached-error-pages-as-success"
date: "2026-08-01"
project: "csfd/streamfinder"
scope:
  - "src/csfd_vod/extraction/scraper.py"
  - "scripts/purge_failed_cache.py"
  - "cache/html/"
guard: "scripts/purge_failed_cache.py (report mode) — a gate in scripts/check_all.py"
tags:
  - data-quality
  - scraping
  - caching
  - silent-failure
  - catalog-completeness
---

# 566 titles were permanently missing because failed scrapes were cached as successes

## Symptom

Chasing two stubborn orphan serials (Humans, Tate no Yusha no Nariagari), their
cached pages turned out to be 4 KB and 9 KB with no `.film-header h1` at all.
Measuring the whole cache showed the shape of the problem:

```
cached pages          50 995
  contain film-header 50 429   ← exactly the number `parse` loads
  do NOT               566     ← all under 10 KB
```

The distribution is bimodal with nothing in between: a real ČSFD title page is
150 KB+, every failed one is under 10 KB (the smallest is 39 bytes). So 566 titles
had been fetched, stored, and were **never going to appear in the catalog**.

## Root Cause

`VODScraper.scrape_title_details` waited for the title element and then carried on
regardless:

```python
try:
    page.wait_for_selector(selector, timeout=5000)
    logger.info("playwright_title_selector_found", selector=selector)
except Exception as e:
    logger.warning("title_selector_not_found_in_page", ...)   # only a warning

time.sleep(2)
html_content = page.content()
...
logger.info("scrape_title_details_success", ...)              # reported as success
return html_content
```

A 404, a bot-check interstitial or a truncated response therefore came back as a
perfectly ordinary return value. `cmd_scrape` cached it, and from then on
`HTMLCache.has()` — which only asks whether a file exists — reported the URL as
done. Every subsequent run skipped it. The failure was permanent and invisible:
`cmd_scrape` still logged `saved`, `parse` still logged `errors: 0`.

## Fix

Treat a missing title element as a failed scrape:

```python
except Exception as e:
    logger.warning("title_selector_not_found_in_page", selector=selector, error=str(e), url=title_url)
    if browser:
        browser.close()
    return None
```

The caller already handled `None` correctly (`if html: cache.save(...)`), so nothing
gets cached and the URL is retried on the next run.

Pages cached before the fix have to be cleared by hand:
`scripts/purge_failed_cache.py --apply`, then `csfd scrape`.

## Why it went unnoticed

Every counter said everything was fine. `scrape` reported the pages as saved,
`parse` reported zero errors, and `check_completeness.py` passed because the
catalog was large and its canary titles happened not to be among the 566.

The only signal was the *distribution* of file sizes in the cache — which nothing
looked at, because nothing had a reason to look at the cache at all. It surfaced
only when two individual orphans were opened by hand and turned out to be 4 KB.

## Prevention

- [x] A scrape that does not contain the element it was waiting for returns None
- [x] Never cache a response that has not been validated as the expected page shape
- [x] `has()`-style cache checks must not be the sole judge of "already done"
- [x] `purge_failed_cache.py` report mode is a gate in `check_all.py`. It fails on
      **both** halves: pages cached that are not title pages, and indexed URLs whose
      page is gone — the state `--apply` leaves behind until `--refetch` has run.
      Without the second half, purging and forgetting to refetch shows up green.

The gate reads only files ≤ 50 KB (`SUSPECT_MAX_BYTES`). The bimodal split makes that
safe — real pages are 150 KB+ — and it keeps the run at ~0.5 s instead of reading
~7 GB, which is the difference between a gate that runs every time and one that doesn't.

## What the write-up alone would not have prevented

This incident was documented before it was guarded, and the guard field said
*"run after any large scrape"* — an instruction to a human, and one nobody would have
run, because the whole point of the bug is that nothing looks wrong. A finding is only
recorded once something executable enforces it; until then the document is a story
about the past, not a check on the future.
