-- Migration 003: Add Streamfinder fields
-- New columns for dashboard: runtime, votes, trailer, age rating, VOD URLs, TMDB metadata
-- 2026-04-12

-- fact_titles: new fields for title detail page
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS runtime_min INTEGER;
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS votes_count INTEGER;
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS trailer_url VARCHAR(500);
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS age_rating VARCHAR(20);

-- dim_vods: add direct watch URL per platform
ALTER TABLE csfd_vod.dim_vods ADD COLUMN IF NOT EXISTS vod_url VARCHAR(500);

-- dim_tmdb: TMDB enrichment metadata per title
CREATE TABLE IF NOT EXISTS csfd_vod.dim_tmdb (
    tmdb_id INTEGER PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    poster_path VARCHAR(200),
    backdrop_path VARCHAR(200),
    trailer_youtube_id VARCHAR(50),
    enriched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(title_id)
);

CREATE INDEX IF NOT EXISTS idx_tmdb_title_id ON csfd_vod.dim_tmdb(title_id);
