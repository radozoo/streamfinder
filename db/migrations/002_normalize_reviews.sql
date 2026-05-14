-- Migration 002: Normalize multi-value columns in fact_titles
-- Removes: director (TEXT), actors (TEXT), reviews (JSONB)
-- Adds: dim_reviews table (data migrated from reviews JSONB)
-- director/actors data already exists in dim_directors/dim_actors

-- 1. Create dim_reviews
CREATE TABLE IF NOT EXISTS csfd_vod.dim_reviews (
    review_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    author VARCHAR(200),
    review_text TEXT,
    stars INTEGER,
    UNIQUE(title_id, author)
);

CREATE INDEX IF NOT EXISTS idx_review_title_id ON csfd_vod.dim_reviews(title_id);

-- 2. Migrate existing reviews JSONB → dim_reviews
INSERT INTO csfd_vod.dim_reviews (title_id, author, review_text, stars)
SELECT
    title_id,
    (review->>'author')::VARCHAR(200),
    review->>'text',
    (review->>'stars')::INTEGER
FROM csfd_vod.fact_titles,
     jsonb_array_elements(reviews) AS review
WHERE reviews IS NOT NULL
  AND review->>'author' IS NOT NULL
ON CONFLICT (title_id, author) DO NOTHING;

-- 3. Drop denormalized columns from fact_titles
ALTER TABLE csfd_vod.fact_titles DROP COLUMN IF EXISTS director;
ALTER TABLE csfd_vod.fact_titles DROP COLUMN IF EXISTS actors;
ALTER TABLE csfd_vod.fact_titles DROP COLUMN IF EXISTS reviews;
