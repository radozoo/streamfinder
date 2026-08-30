"""PostgreSQL loader with incremental upsert logic."""

from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import json

from sqlalchemy import (
    create_engine,
    text,
    event,
)
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import sessionmaker, Session

from csfd_vod.transformation.models import VODTitle
from csfd_vod.logger import get_logger


logger = get_logger(__name__)


class PostgresLoader:
    """Load VOD titles into PostgreSQL with idempotent upsert."""

    def __init__(self, connection_string: str, pool_size: int = 5, max_overflow: int = 2):
        """
        Initialize PostgreSQL loader.

        Args:
            connection_string: SQLAlchemy connection string
            pool_size: Connection pool size
            max_overflow: Max overflow connections
        """
        self.connection_string = connection_string
        self.engine = create_engine(
            connection_string,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            echo=False,
        )

        # Add event listener for connection ping
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            """Ping database on connect to ensure connection is alive."""
            pass

        self.SessionLocal = sessionmaker(bind=self.engine)

    def create_schema(self):
        """Create database schema from schema.sql."""
        try:
            with self.engine.connect() as conn:
                # Read and execute schema SQL
                with open("db/schema.sql", "r") as f:
                    schema_sql = f.read()

                # Execute each statement separately
                for statement in schema_sql.split(";"):
                    if statement.strip():
                        conn.execute(text(statement))
                conn.commit()

            logger.info("schema_created")

        except Exception as e:
            logger.error("schema_creation_failed", error=str(e))
            raise

    def load_titles(self, titles: List[VODTitle], run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Load titles into database with idempotent upsert.

        Uses INSERT ... ON CONFLICT DO UPDATE for PostgreSQL.

        Args:
            titles: List of validated VODTitle objects
            run_id: Optional run ID for tracking

        Returns:
            Dict with load statistics
        """
        if not run_id:
            run_id = str(uuid.uuid4())

        session: Optional[Session] = None
        stats = {
            "loaded": 0,
            "skipped": 0,
            "errors": 0,
            "run_id": run_id,
        }

        try:
            session = self.SessionLocal()

            for title in titles:
                try:
                    # Upsert fact_titles
                    title_id = self._upsert_fact_title(session, title, run_id)

                    if title_id:
                        # Upsert dimension tables
                        self._upsert_dimensions(session, title_id, title)
                        stats["loaded"] += 1
                    else:
                        stats["skipped"] += 1

                except Exception as e:
                    logger.error(
                        "title_load_error",
                        url_id=title.url_id,
                        error=str(e),
                        run_id=run_id,
                    )
                    self._record_failed_title(session, title, str(e), run_id)
                    stats["errors"] += 1

            session.commit()
            logger.info("titles_loaded", stats=stats)
            return stats

        except Exception as e:
            logger.error("load_transaction_failed", error=str(e), run_id=run_id)
            stats["errors"] += len(titles)
            if session:
                session.rollback()
            raise

        finally:
            if session:
                session.close()

    def _upsert_fact_title(self, session: Session, title: VODTitle, run_id: str) -> Optional[int]:
        """
        Upsert a title into fact_titles table.

        Uses PostgreSQL ON CONFLICT DO UPDATE for idempotency.

        Returns:
            title_id if successful, None otherwise
        """
        try:
            insert_sql = text("""
                INSERT INTO csfd_vod.fact_titles
                    (url_id, title, year, link, date_added, run_id, updated_at,
                     title_en, plot, rating, image_url, title_type, parent_url,
                     vod_date, distributor, premiere_detail, scraped_at,
                     runtime_min, votes_count, trailer_url, age_rating,
                     csfd_id, root_id, season_no, episode_no,
                     season_total, episode_total)
                VALUES
                    (:url_id, :title, :year, :link, :date_added, :run_id, CURRENT_TIMESTAMP,
                     :title_en, :plot, :rating, :image_url, :title_type, :parent_url,
                     :vod_date, :distributor, :premiere_detail, :scraped_at,
                     :runtime_min, :votes_count, :trailer_url, :age_rating,
                     :csfd_id, :root_id, :season_no, :episode_no,
                     :season_total, :episode_total)
                ON CONFLICT (url_id)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    year = EXCLUDED.year,
                    -- Volatile/enriched fields are COALESCEd, never blindly
                    -- overwritten: a re-scrape that hits a bot-protection challenge
                    -- or a partially-rendered page parses these to NULL, and a bare
                    -- `= EXCLUDED.x` would then wipe a good rating/plot/poster with
                    -- that NULL. COALESCE keeps the existing value whenever the fresh
                    -- parse has nothing — so a bad page can only ever ADD, never erase.
                    -- (A fully-blocked page has no title and never reaches here.)
                    title_en = COALESCE(EXCLUDED.title_en, csfd_vod.fact_titles.title_en),
                    plot = COALESCE(EXCLUDED.plot, csfd_vod.fact_titles.plot),
                    rating = COALESCE(EXCLUDED.rating, csfd_vod.fact_titles.rating),
                    image_url = COALESCE(EXCLUDED.image_url, csfd_vod.fact_titles.image_url),
                    title_type = EXCLUDED.title_type,
                    parent_url = EXCLUDED.parent_url,
                    vod_date = COALESCE(EXCLUDED.vod_date, csfd_vod.fact_titles.vod_date),
                    distributor = COALESCE(EXCLUDED.distributor, csfd_vod.fact_titles.distributor),
                    premiere_detail = COALESCE(EXCLUDED.premiere_detail, csfd_vod.fact_titles.premiere_detail),
                    scraped_at = EXCLUDED.scraped_at,
                    runtime_min = COALESCE(EXCLUDED.runtime_min, csfd_vod.fact_titles.runtime_min),
                    votes_count = COALESCE(EXCLUDED.votes_count, csfd_vod.fact_titles.votes_count),
                    trailer_url = COALESCE(EXCLUDED.trailer_url, csfd_vod.fact_titles.trailer_url),
                    age_rating = COALESCE(EXCLUDED.age_rating, csfd_vod.fact_titles.age_rating),
                    csfd_id = EXCLUDED.csfd_id,
                    root_id = EXCLUDED.root_id,
                    season_no = EXCLUDED.season_no,
                    episode_no = EXCLUDED.episode_no,
                    season_total = EXCLUDED.season_total,
                    episode_total = EXCLUDED.episode_total,
                    updated_at = CURRENT_TIMESTAMP,
                    run_id = :run_id
                RETURNING title_id
            """)

            result = session.execute(
                insert_sql,
                {
                    "url_id": title.url_id,
                    "title": title.title,
                    "year": title.year,
                    "link": title.link,
                    "date_added": title.date_added,
                    "run_id": run_id,
                    "title_en": title.title_en,
                    "plot": title.plot,
                    "rating": title.rating,
                    "image_url": title.image_url,
                    "title_type": title.title_type,
                    "parent_url": title.parent_url,
                    "vod_date": title.vod_date,
                    "distributor": title.distributor,
                    "premiere_detail": title.premiere_detail,
                    "scraped_at": title.scraped_at,
                    "runtime_min": title.runtime_min,
                    "votes_count": title.votes_count,
                    "trailer_url": title.trailer_url,
                    "age_rating": title.age_rating,
                    "csfd_id": title.csfd_id,
                    "root_id": title.root_id,
                    "season_no": title.season_no,
                    "episode_no": title.episode_no,
                    "season_total": title.season_total,
                    "episode_total": title.episode_total,
                },
            )

            row = result.fetchone()
            return row[0] if row else None

        except Exception as e:
            logger.error("fact_title_upsert_failed", url_id=title.url_id, error=str(e))
            raise

    # Page-derived dimensions fully rebuilt from each parse (see below).
    _REBUILT_DIMS = (
        "dim_genres", "dim_directors", "dim_actors", "dim_countries",
        "dim_vods", "dim_tags", "dim_screenwriters",
        "dim_cinematographers", "dim_composers",
    )

    # Dimensions cleared ONLY when this parse actually carries a value, mirroring the
    # COALESCE that already protects the fact row's volatile fields.
    #
    # Everything else in _REBUILT_DIMS is read off the title page, where an absent
    # section genuinely means "not listed any more". Platforms are the exception: a
    # serial episode's page carries no .film-vod-list at all, so its only source is
    # the /vod listing — and when a listing page comes back as a bot challenge it
    # parses to zero entries. Clearing on that erases a correct platform, and nothing
    # restores it, because the next incremental parse skips a title whose own page
    # never moved. Myšilov lost its Netflix badge exactly this way while keeping the
    # distributor COALESCE had saved. An empty parse may add nothing; it may not erase.
    _REBUILT_ONLY_IF_PRESENT = {"dim_vods": lambda t: bool(t.vod_platforms)}

    def _upsert_dimensions(self, session: Session, title_id: int, title: VODTitle):
        """Rebuild a title's page-derived dimension rows from the current parse.

        These dimensions are cleared first, then re-inserted. Without the clear the
        inserts only ever ADD (ON CONFLICT DO NOTHING), so stale values from an
        earlier or incorrect parse would survive forever — e.g. seed placeholders
        ("Actor 1", "Director 1") or platforms no longer listed on the page. The
        delete + re-insert runs in the same transaction as the fact upsert, so it
        is atomic per title.
        """
        try:
            for tbl in self._REBUILT_DIMS:
                carries = self._REBUILT_ONLY_IF_PRESENT.get(tbl)
                if carries is not None and not carries(title):
                    continue
                session.execute(
                    text(f"DELETE FROM csfd_vod.{tbl} WHERE title_id = :title_id"),
                    {"title_id": title_id},
                )

            # Genres
            if title.genres:
                for genre in title.genres.split(" / "):
                    genre = genre.strip()
                    if genre:
                        session.execute(
                            text("""
                                INSERT INTO csfd_vod.dim_genres (title_id, genre)
                                VALUES (:title_id, :genre)
                                ON CONFLICT (title_id, genre) DO NOTHING
                            """),
                            {"title_id": title_id, "genre": genre},
                        )

            # Directors
            if title.director:
                for director in title.director.split(", "):
                    director = director.strip()
                    if director:
                        session.execute(
                            text("""
                                INSERT INTO csfd_vod.dim_directors (title_id, director)
                                VALUES (:title_id, :director)
                                ON CONFLICT (title_id, director) DO NOTHING
                            """),
                            {"title_id": title_id, "director": director},
                        )

            # Actors
            if title.actors:
                for actor in title.actors.split(", "):
                    actor = actor.strip()
                    if actor:
                        session.execute(
                            text("""
                                INSERT INTO csfd_vod.dim_actors (title_id, actor)
                                VALUES (:title_id, :actor)
                                ON CONFLICT (title_id, actor) DO NOTHING
                            """),
                            {"title_id": title_id, "actor": actor},
                        )

            # Countries
            if title.countries:
                for country in title.countries.split(" / "):
                    country = country.strip()
                    if country:
                        session.execute(
                            text("""
                                INSERT INTO csfd_vod.dim_countries (title_id, country)
                                VALUES (:title_id, :country)
                                ON CONFLICT (title_id, country) DO NOTHING
                            """),
                            {"title_id": title_id, "country": country},
                        )

            # VOD Platforms + URLs
            if title.vod_platforms:
                vod_url_map = json.loads(title.vod_urls) if title.vod_urls else {}
                for vod in title.vod_platforms.split(", "):
                    vod = vod.strip()
                    if vod:
                        session.execute(
                            text("""
                                INSERT INTO csfd_vod.dim_vods (title_id, vod_platform, vod_url)
                                VALUES (:title_id, :vod_platform, :vod_url)
                                ON CONFLICT (title_id, vod_platform)
                                DO UPDATE SET vod_url = EXCLUDED.vod_url
                            """),
                            {"title_id": title_id, "vod_platform": vod, "vod_url": vod_url_map.get(vod)},
                        )

            # Tags
            if title.tags:
                for tag in title.tags.split(", "):
                    tag = tag.strip()
                    if tag:
                        session.execute(
                            text("""
                                INSERT INTO csfd_vod.dim_tags (title_id, tag)
                                VALUES (:title_id, :tag)
                                ON CONFLICT (title_id, tag) DO NOTHING
                            """),
                            {"title_id": title_id, "tag": tag},
                        )

            # Screenwriters
            if title.script:
                for name in title.script.split(", "):
                    name = name.strip()
                    if name:
                        session.execute(
                            text("""
                                INSERT INTO csfd_vod.dim_screenwriters (title_id, screenwriter)
                                VALUES (:title_id, :screenwriter)
                                ON CONFLICT (title_id, screenwriter) DO NOTHING
                            """),
                            {"title_id": title_id, "screenwriter": name},
                        )

            # Cinematographers
            if title.camera:
                for name in title.camera.split(", "):
                    name = name.strip()
                    if name:
                        session.execute(
                            text("""
                                INSERT INTO csfd_vod.dim_cinematographers (title_id, cinematographer)
                                VALUES (:title_id, :cinematographer)
                                ON CONFLICT (title_id, cinematographer) DO NOTHING
                            """),
                            {"title_id": title_id, "cinematographer": name},
                        )

            # Composers
            if title.music:
                for name in title.music.split(", "):
                    name = name.strip()
                    if name:
                        session.execute(
                            text("""
                                INSERT INTO csfd_vod.dim_composers (title_id, composer)
                                VALUES (:title_id, :composer)
                                ON CONFLICT (title_id, composer) DO NOTHING
                            """),
                            {"title_id": title_id, "composer": name},
                        )

            # Reviews
            if title.reviews:
                for rev in json.loads(title.reviews):
                    author = rev.get("author")
                    if author:
                        session.execute(
                            text("""
                                INSERT INTO csfd_vod.dim_reviews (title_id, author, review_text, stars)
                                VALUES (:title_id, :author, :review_text, :stars)
                                ON CONFLICT (title_id, author) DO NOTHING
                            """),
                            {
                                "title_id": title_id,
                                "author": author,
                                "review_text": rev.get("text"),
                                "stars": rev.get("stars"),
                            },
                        )

        except Exception as e:
            logger.error("dimension_upsert_failed", title_id=title_id, error=str(e))
            raise

    def select_refresh_urls(self, max_age_days: int, limit: int) -> List[str]:
        """URLs of 'hot' titles due for a rating/votes refresh.

        A title is hot while its rating is still maturing: either recently on VOD
        (`vod_date` within `max_age_days`) or still unrated. We prioritise unrated
        titles, then the youngest, then the stalest last scrape — and cap at `limit`
        so a run's Playwright budget is bounded no matter how big the catalogue is.
        Successive runs rotate through the queue via the `scraped_at ASC` tiebreak.

        Evergreen soaps (Ružová zahrada & co.) fall out on their own: they are old
        and well-voted, so they match neither the recency nor the unrated clause.
        """
        sql = text(
            """
            SELECT url_id FROM csfd_vod.fact_titles
            WHERE vod_date IS NOT NULL
              AND (vod_date >= CURRENT_DATE - (:max_age * INTERVAL '1 day')
                   OR rating IS NULL)
            ORDER BY (rating IS NULL) DESC,
                     vod_date DESC,
                     scraped_at ASC NULLS FIRST
            LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"max_age": max_age_days, "limit": limit}).fetchall()
        return [r[0] for r in rows]

    def _record_failed_title(
        self, session: Session, title: VODTitle, error: str, run_id: str
    ):
        """Record failed title in failed_records table for debugging."""
        try:
            session.execute(
                text("""
                    INSERT INTO csfd_vod.failed_records
                        (url_id, error_type, error_message, original_data, run_id)
                    VALUES (:url_id, :error_type, :error_message, :original_data, :run_id)
                """),
                {
                    "url_id": title.url_id,
                    "error_type": "load_error",
                    "error_message": error,
                    "original_data": title.model_dump_json(),
                    "run_id": run_id,
                },
            )
        except Exception as e:
            logger.error("failed_record_insert_failed", error=str(e))

    def close(self):
        """Close database connections."""
        self.engine.dispose()
