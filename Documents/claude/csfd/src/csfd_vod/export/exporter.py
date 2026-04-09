"""Data exporter: Converts PostgreSQL data to JSON format."""

import json
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from csfd_vod.logger import get_logger

logger = get_logger(__name__)


class DataExporter:
    """Export VOD data from PostgreSQL to JSON format."""

    def __init__(self, connection_string: str):
        """
        Initialize data exporter.

        Args:
            connection_string: SQLAlchemy connection string
        """
        self.connection_string = connection_string
        self.engine = create_engine(connection_string, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def export_to_json(self, output_path: str) -> Dict[str, Any]:
        """
        Export VOD data to JSON file.

        Args:
            output_path: Path to write JSON file

        Returns:
            Dict with export statistics
        """
        session: Session | None = None
        try:
            session = self.SessionLocal()

            # Query all data
            titles = self._query_titles_with_dimensions(session)
            stats = self._compute_statistics(session)

            # Build export structure
            export_data = {
                "metadata": {
                    "export_timestamp": datetime.utcnow().isoformat() + "Z",
                    "total_titles": len(titles),
                    "total_genres": stats["total_genres"],
                    "total_directors": stats["total_directors"],
                    "total_actors": stats["total_actors"],
                    "total_countries": stats["total_countries"],
                    "total_platforms": stats["total_platforms"],
                    "date_range": stats["date_range"],
                },
                "statistics": {
                    "genres_by_count": stats["genres_by_count"],
                    "countries_by_count": stats["countries_by_count"],
                    "platforms_by_count": stats["platforms_by_count"],
                    "years_by_count": stats["years_by_count"],
                    "decade_distribution": stats["decade_distribution"],
                },
                "titles": titles,
            }

            # Write to file
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            result = {
                "success": True,
                "output_path": str(output_path_obj.absolute()),
                "titles_exported": len(titles),
                "file_size_kb": output_path_obj.stat().st_size / 1024,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

            logger.info("data_exported", **result)
            return result

        except Exception as e:
            logger.error("export_failed", error=str(e))
            raise

        finally:
            if session:
                session.close()

    def _query_titles_with_dimensions(self, session: Session) -> List[Dict[str, Any]]:
        """
        Query titles with all dimension data joined.

        Returns:
            List of title dicts with nested genres, directors, actors, countries, platforms
        """
        try:
            # Query all titles
            titles_sql = text("""
                SELECT
                    title_id,
                    url_id,
                    title,
                    year,
                    director,
                    actors,
                    link,
                    date_added,
                    date_scraped,
                    created_at,
                    updated_at
                FROM csfd_vod.fact_titles
                ORDER BY date_scraped DESC
            """)

            result = session.execute(titles_sql)
            titles = []

            for row in result:
                title_id = row[0]
                title_dict = {
                    "title_id": title_id,
                    "url_id": row[1],
                    "title": row[2],
                    "year": row[3],
                    "director": row[4],
                    "actors": row[5],
                    "link": row[6],
                    "date_added": row[7].isoformat() if row[7] else None,
                    "date_scraped": row[8].isoformat() if row[8] else None,
                    "created_at": row[9].isoformat() if row[9] else None,
                    "updated_at": row[10].isoformat() if row[10] else None,
                    "genres": self._query_dimension(session, "dim_genres", "genre", title_id),
                    "directors": self._query_dimension(session, "dim_directors", "director", title_id),
                    "actors_list": self._query_dimension(session, "dim_actors", "actor", title_id),
                    "countries": self._query_dimension(session, "dim_countries", "country", title_id),
                    "platforms": self._query_dimension(session, "dim_vods", "vod_platform", title_id),
                }
                titles.append(title_dict)

            logger.info("titles_queried", count=len(titles))
            return titles

        except Exception as e:
            logger.error("titles_query_failed", error=str(e))
            raise

    def _query_dimension(self, session: Session, table: str, column: str, title_id: int) -> List[str]:
        """
        Query a dimension table for a title.

        Args:
            session: Database session
            table: Table name (e.g., dim_genres)
            column: Column name (e.g., genre)
            title_id: Title ID to filter by

        Returns:
            List of dimension values
        """
        try:
            sql = text(f"SELECT {column} FROM csfd_vod.{table} WHERE title_id = :title_id ORDER BY {column}")
            result = session.execute(sql, {"title_id": title_id})
            return [row[0] for row in result]

        except Exception as e:
            logger.error("dimension_query_failed", table=table, title_id=title_id, error=str(e))
            return []

    def _compute_statistics(self, session: Session) -> Dict[str, Any]:
        """
        Compute aggregate statistics.

        Returns:
            Dict with statistics
        """
        try:
            stats = {
                "total_genres": 0,
                "total_directors": 0,
                "total_actors": 0,
                "total_countries": 0,
                "total_platforms": 0,
                "date_range": [None, None],
                "genres_by_count": [],
                "countries_by_count": [],
                "platforms_by_count": [],
                "years_by_count": [],
                "decade_distribution": [],
            }

            # Count distinct genres
            result = session.execute(text("SELECT COUNT(DISTINCT genre) FROM csfd_vod.dim_genres"))
            stats["total_genres"] = result.scalar() or 0

            # Count distinct directors
            result = session.execute(text("SELECT COUNT(DISTINCT director) FROM csfd_vod.dim_directors"))
            stats["total_directors"] = result.scalar() or 0

            # Count distinct actors
            result = session.execute(text("SELECT COUNT(DISTINCT actor) FROM csfd_vod.dim_actors"))
            stats["total_actors"] = result.scalar() or 0

            # Count distinct countries
            result = session.execute(text("SELECT COUNT(DISTINCT country) FROM csfd_vod.dim_countries"))
            stats["total_countries"] = result.scalar() or 0

            # Count distinct platforms
            result = session.execute(text("SELECT COUNT(DISTINCT vod_platform) FROM csfd_vod.dim_vods"))
            stats["total_platforms"] = result.scalar() or 0

            # Date range
            result = session.execute(
                text("SELECT MIN(date_added), MAX(date_added) FROM csfd_vod.fact_titles")
            )
            row = result.fetchone()
            if row and row[0] and row[1]:
                stats["date_range"] = [
                    row[0].isoformat() if row[0] else None,
                    row[1].isoformat() if row[1] else None,
                ]

            # Top genres
            result = session.execute(
                text("""
                    SELECT genre, COUNT(*) as count
                    FROM csfd_vod.dim_genres
                    GROUP BY genre
                    ORDER BY count DESC
                    LIMIT 20
                """)
            )
            stats["genres_by_count"] = [{"name": row[0], "count": row[1]} for row in result]

            # Top countries
            result = session.execute(
                text("""
                    SELECT country, COUNT(*) as count
                    FROM csfd_vod.dim_countries
                    GROUP BY country
                    ORDER BY count DESC
                    LIMIT 15
                """)
            )
            stats["countries_by_count"] = [{"name": row[0], "count": row[1]} for row in result]

            # Top platforms
            result = session.execute(
                text("""
                    SELECT vod_platform, COUNT(*) as count
                    FROM csfd_vod.dim_vods
                    GROUP BY vod_platform
                    ORDER BY count DESC
                    LIMIT 10
                """)
            )
            stats["platforms_by_count"] = [{"name": row[0], "count": row[1]} for row in result]

            # Titles by year
            result = session.execute(
                text("""
                    SELECT year, COUNT(*) as count
                    FROM csfd_vod.fact_titles
                    WHERE year IS NOT NULL
                    GROUP BY year
                    ORDER BY year DESC
                    LIMIT 50
                """)
            )
            stats["years_by_count"] = [{"year": row[0], "count": row[1]} for row in result]

            # Decade distribution
            result = session.execute(
                text("""
                    SELECT
                        CONCAT((year / 10) * 10, 's') as decade,
                        COUNT(*) as count
                    FROM csfd_vod.fact_titles
                    WHERE year IS NOT NULL
                    GROUP BY (year / 10)
                    ORDER BY (year / 10) DESC
                """)
            )
            stats["decade_distribution"] = [{"decade": row[0], "count": row[1]} for row in result]

            logger.info("statistics_computed", stats=stats)
            return stats

        except Exception as e:
            logger.error("statistics_computation_failed", error=str(e))
            raise
