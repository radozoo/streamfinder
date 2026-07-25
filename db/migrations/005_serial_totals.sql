-- Migration 005: Serial season/episode totals
-- 2026-07-24
--
-- Most serials appear on /vod as a whole (their episodes were never scraped
-- individually), so the child-derived season/episode counts are empty for them and
-- the Katalóg card shows no shape. The serial's own page states the authoritative
-- totals in its header ("Série (2) Epizody (18)"), so we capture those directly.
--
-- These are the totals the show HAS (for the card); is_running/cadence/timeline stay
-- derived from the episodes actually on VOD.

ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS season_total INTEGER;   -- "Série (N)" — only for multi-season shows
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS episode_total INTEGER;  -- "Epizody (M)"

-- Populated by the parser (or scripts/backfill_serial_totals.py) from cached HTML;
-- cannot be derived from the URL, so no SQL backfill here.
