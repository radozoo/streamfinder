-- Every VOD release event, not just the one that happened to win (2026-09-07).
--
-- A release event is titul × dátum × platforma, but fact_titles.vod_date is a single
-- column, so a title can only ever appear on one day of the Kalendár. ČSFD lists a
-- running serial's root every week a new episode drops, and lists a film again when
-- it lands on a second platform years later — 3,409 titles in the cached listings
-- carry more than one date, for 3,977 (day, title) events the calendar could not
-- show. Over the last year that is 258 of 365 days silently short.
--
-- Which of the dates won was not even "first" or "last": merge_list_metadata is
-- first-wins over listing files sorted by name, and ČSFD orders a month's pages
-- newest-date-first, so the winner was the NEWEST date in the OLDEST month. Vigil's
-- BBC iPlayer return on 2026-09-06 lost to a 2023 listing; Colisión's 2026-09-07
-- premiere lost to its own 2026-09-28 episode.
--
-- Why the platform lives on the event and not on the title: of those 3,409 titles,
-- 2,937 (86%) have a DIFFERENT platform on different dates. Vigil in 2023 was not
-- BBC iPlayer. The Kalendár has a platform filter, so folding the platforms into a
-- per-title union would surface days on which that platform released nothing.
--
-- Keyed on csfd_id, deliberately:
--   * not url_id — that carries the slug, and ČSFD renames slugs (rules doc §11);
--     identity is csfd_id.
--   * no FK to fact_titles — an event exists whether or not we have scraped the
--     title's own page yet. A LEFT JOIN against this table finds 157 such ids,
--     carrying 174 events, with no row in fact_titles at all.
--
-- platform is NOT NULL DEFAULT '' rather than nullable: in Postgres NULLs are
-- distinct in a unique index, so two platform-less events on the same day for the
-- same title would both insert.
CREATE TABLE IF NOT EXISTS csfd_vod.fact_vod_events (
    event_id    SERIAL PRIMARY KEY,
    csfd_id     INTEGER      NOT NULL,
    vod_date    DATE         NOT NULL,
    platform    VARCHAR(100) NOT NULL DEFAULT '',
    distributor VARCHAR(200),
    list_type   VARCHAR(20),
    first_seen  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (csfd_id, vod_date, platform)
);

CREATE INDEX IF NOT EXISTS idx_vod_event_date ON csfd_vod.fact_vod_events(vod_date);
CREATE INDEX IF NOT EXISTS idx_vod_event_csfd ON csfd_vod.fact_vod_events(csfd_id);
