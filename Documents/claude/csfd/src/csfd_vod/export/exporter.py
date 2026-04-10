"""Data exporter: Queries PostgreSQL and writes pre-aggregated JSON files."""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from csfd_vod.logger import get_logger

logger = get_logger(__name__)

_TITLE_COLS = [
    "title_id", "url_id", "title", "title_en", "year", "link",
    "rating", "plot", "image_url", "title_type", "parent_url",
    "vod_date", "distributor", "premiere_detail", "reviews", "scraped_at", "date_added",
]


class DataExporter:
    """Export VOD data from PostgreSQL to pre-aggregated JSON files."""

    def __init__(self, connection_string: str):
        self.engine = create_engine(connection_string, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export(self, output_dir: str) -> dict[str, Any]:
        """
        Export all JSON files to output_dir/.

        Writes 10 files:
          summary.json, genres.json, directors.json, actors.json,
          countries.json, platforms.json, tags.json,
          rating_distribution.json, vod_by_month.json, top_titles.json

        Returns dict with export statistics.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        session = self.SessionLocal()
        try:
            # 9 bulk dimension queries (no N+1)
            genres_map = self._load_dim(session, "dim_genres", "genre")
            actors_map = self._load_dim(session, "dim_actors", "actor")
            directors_map = self._load_dim(session, "dim_directors", "director")
            countries_map = self._load_dim(session, "dim_countries", "country")
            platforms_map = self._load_dim(session, "dim_vods", "vod_platform")
            tags_map = self._load_dim(session, "dim_tags", "tag")
            screenwriters_map = self._load_dim(session, "dim_screenwriters", "screenwriter")
            cinematographers_map = self._load_dim(session, "dim_cinematographers", "cinematographer")
            composers_map = self._load_dim(session, "dim_composers", "composer")

            # 1 title query
            titles = self._load_titles(session)

            files_written = []

            # summary.json
            summary = self._build_summary(titles, genres_map, actors_map, directors_map, countries_map, platforms_map)
            self._write(out / "summary.json", summary)
            files_written.append("summary.json")

            # top-N lists from dimension maps (genres, actors, directors, countries, platforms, tags)
            dim_exports = [
                ("genres.json",    genres_map,    30),
                ("actors.json",    actors_map,    30),
                ("directors.json", directors_map, 30),
                ("countries.json", countries_map, 50),
                ("platforms.json", platforms_map, 50),
                ("tags.json",      tags_map,      50),
            ]
            for filename, dim_map, limit in dim_exports:
                counts = Counter(v for vals in dim_map.values() for v in vals)
                data = [{"name": k, "count": v} for k, v in counts.most_common(limit)]
                self._write(out / filename, data)
                files_written.append(filename)

            # rating_distribution.json
            self._write(out / "rating_distribution.json", self._rating_distribution(titles))
            files_written.append("rating_distribution.json")

            # vod_by_month.json
            self._write(out / "vod_by_month.json", self._vod_by_month(session))
            files_written.append("vod_by_month.json")

            # top_titles.json
            self._write(out / "top_titles.json", self._top_titles(titles, genres_map, platforms_map))
            files_written.append("top_titles.json")

            result = {
                "success": True,
                "output_dir": str(out.absolute()),
                "files_written": files_written,
                "total_titles": len(titles),
            }
            logger.info("export_complete", **result)
            return result

        except Exception as e:
            logger.error("export_failed", error=str(e))
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_dim(self, session: Session, table: str, col: str) -> dict[int, list[str]]:
        """Load entire dimension table in one query. Returns {title_id: [values]}."""
        result: dict[int, list[str]] = {}
        for row in session.execute(text(f"SELECT title_id, {col} FROM csfd_vod.{table}")):
            result.setdefault(row[0], []).append(row[1])
        return result

    def _load_titles(self, session: Session) -> list[dict[str, Any]]:
        """Load all titles in one query. Returns list of dicts."""
        sql = text(f"""
            SELECT {', '.join(_TITLE_COLS)}
            FROM csfd_vod.fact_titles
            ORDER BY vod_date DESC NULLS LAST, title_id DESC
        """)
        titles = []
        for row in session.execute(sql):
            d = dict(zip(_TITLE_COLS, row))
            # Serialize date/datetime to ISO strings
            for k in ("vod_date", "scraped_at", "date_added"):
                if d[k] is not None:
                    d[k] = d[k].isoformat()
            titles.append(d)
        return titles

    def _build_summary(
        self,
        titles: list[dict],
        genres_map: dict,
        actors_map: dict,
        directors_map: dict,
        countries_map: dict,
        platforms_map: dict,
    ) -> dict[str, Any]:
        rated = [t["rating"] for t in titles if t["rating"] is not None]
        type_counts: Counter = Counter(t["title_type"] for t in titles if t["title_type"])
        return {
            "export_timestamp": datetime.utcnow().isoformat() + "Z",
            "total_titles": len(titles),
            "total_films": type_counts.get("film", 0),
            "total_serials": type_counts.get("seriál", 0),
            "total_genres": len({v for vals in genres_map.values() for v in vals}),
            "total_directors": len({v for vals in directors_map.values() for v in vals}),
            "total_actors": len({v for vals in actors_map.values() for v in vals}),
            "total_countries": len({v for vals in countries_map.values() for v in vals}),
            "total_platforms": len({v for vals in platforms_map.values() for v in vals}),
            "avg_rating": round(sum(rated) / len(rated), 1) if rated else None,
            "title_type_counts": [{"name": k, "count": v} for k, v in type_counts.most_common()],
        }

    def _rating_distribution(self, titles: list[dict]) -> list[dict[str, Any]]:
        """Count titles per 10-point rating bucket (0-10, 10-20, ..., 90-100)."""
        buckets: dict[str, int] = {f"{i}-{i + 10}": 0 for i in range(0, 100, 10)}
        for t in titles:
            if t["rating"] is not None:
                start = min((t["rating"] // 10) * 10, 90)
                buckets[f"{start}-{start + 10}"] += 1
        return [{"bucket": k, "count": v} for k, v in buckets.items()]

    def _vod_by_month(self, session: Session) -> list[dict[str, Any]]:
        """Count new VOD arrivals per month for last 36 months."""
        sql = text("""
            SELECT TO_CHAR(vod_date, 'YYYY-MM') AS month, COUNT(*) AS count
            FROM csfd_vod.fact_titles
            WHERE vod_date IS NOT NULL
              AND vod_date >= CURRENT_DATE - INTERVAL '36 months'
            GROUP BY 1
            ORDER BY 1
        """)
        return [{"month": row[0], "count": row[1]} for row in session.execute(sql)]

    def _top_titles(
        self,
        titles: list[dict],
        genres_map: dict[int, list[str]],
        platforms_map: dict[int, list[str]],
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Top N titles by rating, enriched with genres and platforms."""
        rated = sorted(
            (t for t in titles if t["rating"] is not None),
            key=lambda t: t["rating"],
            reverse=True,
        )
        return [
            {
                "title": t["title"],
                "title_en": t["title_en"],
                "year": t["year"],
                "rating": t["rating"],
                "vod_date": t["vod_date"],
                "distributor": t["distributor"],
                "image_url": t["image_url"],
                "title_type": t["title_type"],
                "link": t["link"],
                "genres": genres_map.get(t["title_id"], []),
                "platforms": platforms_map.get(t["title_id"], []),
            }
            for t in rated[:limit]
        ]

    @staticmethod
    def _write(path: Path, data: Any) -> None:
        """Write data as pretty-printed JSON."""
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
