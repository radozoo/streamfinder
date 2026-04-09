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
    run_id UUID,
    INDEX idx_title (title),
    INDEX idx_year (year),
    INDEX idx_date_scraped (date_scraped)
);

-- Dimension table: Genres (one row per title-genre combination)
CREATE TABLE IF NOT EXISTS csfd_vod.dim_genres (
    genre_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    genre VARCHAR(100) NOT NULL,
    UNIQUE(title_id, genre),
    INDEX idx_genre (genre)
);

-- Dimension table: Directors (one row per title-director combination)
CREATE TABLE IF NOT EXISTS csfd_vod.dim_directors (
    director_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    director VARCHAR(200) NOT NULL,
    UNIQUE(title_id, director),
    INDEX idx_director (director)
);

-- Dimension table: Actors (one row per title-actor combination)
CREATE TABLE IF NOT EXISTS csfd_vod.dim_actors (
    actor_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    actor VARCHAR(200) NOT NULL,
    UNIQUE(title_id, actor),
    INDEX idx_actor (actor)
);

-- Dimension table: Countries (one row per title-country combination)
CREATE TABLE IF NOT EXISTS csfd_vod.dim_countries (
    country_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    country VARCHAR(100) NOT NULL,
    UNIQUE(title_id, country),
    INDEX idx_country (country)
);

-- Dimension table: VOD Platforms (one row per title-platform combination)
CREATE TABLE IF NOT EXISTS csfd_vod.dim_vods (
    vod_id SERIAL PRIMARY KEY,
    title_id INTEGER NOT NULL REFERENCES csfd_vod.fact_titles(title_id) ON DELETE CASCADE,
    vod_platform VARCHAR(100) NOT NULL,
    UNIQUE(title_id, vod_platform),
    INDEX idx_vod_platform (vod_platform)
);

-- Failed records (dead letter queue)
CREATE TABLE IF NOT EXISTS csfd_vod.failed_records (
    failed_record_id SERIAL PRIMARY KEY,
    url_id VARCHAR(500),
    error_type VARCHAR(100),
    error_message TEXT,
    original_data JSONB,
    run_id UUID,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_run_id (run_id)
);

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
