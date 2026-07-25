-- Migration 004: Title hierarchy (Work vs. Release model)
-- 2026-07-24
--
-- ČSFD /vod mixes levels: film, whole serial, new season, single episode. The
-- Katalóg should show top-level works only; the Kalendár shows release events that
-- link up to their work. The bridge is the numeric root id derived from the URL:
--   /film/{ROOT_ID}-slug/{CHILD_ID}-slug/prehled/   → episode/season under a serial
--   /film/{ID}-slug/prehled/                        → top-level work (root_id == csfd_id)
--
-- The old parent_url column stayed empty for 100% of rows (regex never matched the
-- "-slug" between id and slash). We replace it with integer ids that join cleanly.

ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS csfd_id INTEGER;     -- own ČSFD id
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS root_id INTEGER;     -- top-level serial id (== csfd_id for works)
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS season_no INTEGER;
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS episode_no INTEGER;

CREATE INDEX IF NOT EXISTS idx_root_id ON csfd_vod.fact_titles(root_id);

-- Backfill: root_id = first /film/{id}; csfd_id = id of the segment before /prehled
-- (second segment for children, only segment for works). Falls back to root_id.
UPDATE csfd_vod.fact_titles SET
    root_id = substring(url_id from 'csfd\.cz/film/(\d+)')::int,
    csfd_id = COALESCE(
        substring(url_id from '/(\d+)-[^/]*/prehled')::int,
        substring(url_id from 'csfd\.cz/film/(\d+)')::int
    )
WHERE root_id IS NULL;

-- Season/episode number from the "(S02E05)" marker ČSFD puts in episode titles.
UPDATE csfd_vod.fact_titles SET
    season_no  = substring(title from 'S(\d+)E\d+')::int,
    episode_no = substring(title from 'S\d+E(\d+)')::int
WHERE title ~ 'S\d+E\d+';

-- Episodes with only a bare "(E07)" marker (season unknown).
UPDATE csfd_vod.fact_titles SET
    episode_no = substring(title from '\(E(\d+)\)')::int
WHERE episode_no IS NULL AND title ~ '\(E\d+\)';

-- Standalone season rows ("série N") carry only a season number, from the URL slug
-- or the title.
UPDATE csfd_vod.fact_titles SET
    season_no = COALESCE(
        season_no,
        substring(url_id from '/\d+-serie-(\d+)')::int,
        substring(url_id from '/\d+-season-(\d+)')::int,
        substring(title from '[Ss][ée]rie (\d+)')::int,
        substring(title from '[Ss]eason (\d+)')::int
    )
WHERE title_type = 'série' AND season_no IS NULL;
