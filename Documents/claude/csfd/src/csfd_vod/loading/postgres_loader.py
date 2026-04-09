"""PostgreSQL loader with incremental upsert logic."""

from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

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
                    (url_id, title, year, director, actors, link, date_added, run_id, updated_at)
                VALUES
                    (:url_id, :title, :year, :director, :actors, :link, :date_added, :run_id, CURRENT_TIMESTAMP)
                ON CONFLICT (url_id)
                DO UPDATE SET
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
                    "director": title.director,
                    "actors": title.actors,
                    "link": title.link,
                    "date_added": title.date_added,
                    "run_id": run_id,
                },
            )

            row = result.fetchone()
            return row[0] if row else None

        except Exception as e:
            logger.error("fact_title_upsert_failed", url_id=title.url_id, error=str(e))
            raise

    def _upsert_dimensions(self, session: Session, title_id: int, title: VODTitle):
        """Upsert dimension tables (genres, directors, actors, countries, vods)."""
        try:
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

            # VOD Platforms
            if title.vod_platforms:
                for vod in title.vod_platforms.split(", "):
                    vod = vod.strip()
                    if vod:
                        session.execute(
                            text("""
                                INSERT INTO csfd_vod.dim_vods (title_id, vod_platform)
                                VALUES (:title_id, :vod_platform)
                                ON CONFLICT (title_id, vod_platform) DO NOTHING
                            """),
                            {"title_id": title_id, "vod_platform": vod},
                        )

        except Exception as e:
            logger.error("dimension_upsert_failed", title_id=title_id, error=str(e))
            raise

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
