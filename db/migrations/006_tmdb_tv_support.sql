-- TMDB enrichment for series, and a record of searches that found nothing.
--
-- The enricher only ever queried /search/movie, so `title_type = 'film'` was a
-- necessary guard: searching a serial among films returns a confident wrong match.
-- With /search/tv wired in, series can be enriched too — 6 845 serials and 1 747
-- shows had no TMDB row at all, which is why a serial's detail page has no backdrop
-- and 390 of them have no artwork whatsoever.
--
-- A search that finds nothing leaves no trace today, so those titles are searched
-- again on every single run: the last enrich spent 1 285 of its 1 295 lookups
-- re-asking questions already answered. At ~10 000 TV candidates that waste is the
-- whole run. This table records the misses so they can be retried on a schedule
-- rather than constantly.

CREATE TABLE IF NOT EXISTS csfd_vod.tmdb_misses (
    title_id INTEGER PRIMARY KEY REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    attempts INTEGER NOT NULL DEFAULT 1,
    last_tried_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tmdb_misses_last_tried ON csfd_vod.tmdb_misses(last_tried_at);
