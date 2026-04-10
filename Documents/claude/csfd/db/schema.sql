-- PostgreSQL schema for CSFD VOD scraping pipeline
-- Fact/dimension star schema design

CREATE SCHEMA IF NOT EXISTS csfd_vod;

-- Fact table: VOD Titles
CREATE TABLE IF NOT EXISTS csfd_vod.fact_titles (
    title_id SERIAL PRIMARY KEY,
    url_id VARCHAR(500) UNIQUE NOT NULL,
    title VARCHAR(500) NOT NULL,
    year INTEGER,
    director TEXT,
    actors TEXT,
    link VARCHAR(500) NOT NULL,
    date_added DATE,
    date_scraped TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    run_id UUID
);

CREATE INDEX IF NOT EXISTS idx_title ON csfd_vod.fact_titles(title);
CREATE INDEX IF NOT EXISTS idx_year ON csfd_vod.fact_titles(year);
CREATE INDEX IF NOT EXISTS idx_date_scraped ON csfd_vod.fact_titles(date_scraped);

-- New columns added in parser rewrite (2026-04-10)
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS title_en VARCHAR(500);
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS plot TEXT;
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS rating INTEGER;          -- 0-100 or NULL
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS image_url VARCHAR(500);
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS title_type VARCHAR(20);  -- 'film', 'serial', 'seria', 'epizoda'
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS parent_url VARCHAR(500); -- NULL for films/serials
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS vod_date DATE;           -- from list page
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS distributor VARCHAR(200);-- from list page
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS premiere_detail TEXT;    -- raw "Na VOD od..." text
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS reviews JSONB;           -- [{author, text, stars}]
ALTER TABLE csfd_vod.fact_titles ADD COLUMN IF NOT EXISTS scraped_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_title_type ON csfd_vod.fact_titles(title_type);
CREATE INDEX IF NOT EXISTS idx_rating ON csfd_vod.fact_titles(rating);

-- Dimension table: Genres (one row per title-genre combination)
CREATE TABLE IF NOT EXISTS csfd_vod.dim_genres (
    genre_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    genre VARCHAR(100) NOT NULL,
    UNIQUE(title_id, genre)
);

CREATE INDEX IF NOT EXISTS idx_genre ON csfd_vod.dim_genres(genre);

-- Dimension table: Directors (one row per title-director combination)
CREATE TABLE IF NOT EXISTS csfd_vod.dim_directors (
    director_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    director VARCHAR(200) NOT NULL,
    UNIQUE(title_id, director)
);

CREATE INDEX IF NOT EXISTS idx_director ON csfd_vod.dim_directors(director);

-- Dimension table: Actors (one row per title-actor combination)
CREATE TABLE IF NOT EXISTS csfd_vod.dim_actors (
    actor_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    actor VARCHAR(200) NOT NULL,
    UNIQUE(title_id, actor)
);

CREATE INDEX IF NOT EXISTS idx_actor ON csfd_vod.dim_actors(actor);

-- Dimension table: Countries (one row per title-country combination)
CREATE TABLE IF NOT EXISTS csfd_vod.dim_countries (
    country_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    country VARCHAR(100) NOT NULL,
    UNIQUE(title_id, country)
);

CREATE INDEX IF NOT EXISTS idx_country ON csfd_vod.dim_countries(country);

-- Dimension table: VOD Platforms (one row per title-platform combination)
CREATE TABLE IF NOT EXISTS csfd_vod.dim_vods (
    vod_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    vod_platform VARCHAR(100) NOT NULL,
    UNIQUE(title_id, vod_platform)
);

CREATE INDEX IF NOT EXISTS idx_vod_platform ON csfd_vod.dim_vods(vod_platform);

-- Dimension table: Tags
CREATE TABLE IF NOT EXISTS csfd_vod.dim_tags (
    tag_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    tag VARCHAR(100) NOT NULL,
    UNIQUE(title_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_tag ON csfd_vod.dim_tags(tag);

-- Dimension table: Screenwriters
CREATE TABLE IF NOT EXISTS csfd_vod.dim_screenwriters (
    screenwriter_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    screenwriter VARCHAR(200) NOT NULL,
    UNIQUE(title_id, screenwriter)
);

CREATE INDEX IF NOT EXISTS idx_screenwriter ON csfd_vod.dim_screenwriters(screenwriter);

-- Dimension table: Cinematographers
CREATE TABLE IF NOT EXISTS csfd_vod.dim_cinematographers (
    cinematographer_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    cinematographer VARCHAR(200) NOT NULL,
    UNIQUE(title_id, cinematographer)
);

CREATE INDEX IF NOT EXISTS idx_cinematographer ON csfd_vod.dim_cinematographers(cinematographer);

-- Dimension table: Composers
CREATE TABLE IF NOT EXISTS csfd_vod.dim_composers (
    composer_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    composer VARCHAR(200) NOT NULL,
    UNIQUE(title_id, composer)
);

CREATE INDEX IF NOT EXISTS idx_composer ON csfd_vod.dim_composers(composer);

-- Failed records (dead letter queue)
CREATE TABLE IF NOT EXISTS csfd_vod.failed_records (
    failed_record_id SERIAL PRIMARY KEY,
    url_id VARCHAR(500),
    error_type VARCHAR(100),
    error_message TEXT,
    original_data JSONB,
    run_id UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_run_id ON csfd_vod.failed_records(run_id);

-- Pipeline runs metadata
CREATE TABLE IF NOT EXISTS csfd_vod.pipeline_runs (
    run_id UUID PRIMARY KEY,
    stage VARCHAR(50),
    status VARCHAR(50),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    titles_scraped INTEGER,
    titles_parsed INTEGER,
    titles_loaded INTEGER,
    errors_count INTEGER,
    error_details JSONB,
    metrics JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
