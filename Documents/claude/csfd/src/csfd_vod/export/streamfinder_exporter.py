"""Streamfinder JSON exporter.

Produces 3 files for the SvelteKit static site:
  - titles_index.json   lightweight grid data (~2MB) used for Katalog + Kalendar
  - titles_detail.json  full per-title data (plot, reviews, crew, vod_urls)
  - dimensions.json     flat lookup tables (genres, tags, platforms, countries)
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from csfd_vod.logger import get_logger

logger = get_logger(__name__)

_TMDB_IMG_BASE = "https://image.tmdb.org/t/p"


def _slug(title: str, year: int | None) -> str:
    """Generate URL-safe slug: 'the-matrix-1999'."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower().strip())
    slug = slug.strip("-")
    if year:
        slug = f"{slug}-{year}"
    return slug


class StreamfinderExporter:
    """Export Streamfinder JSON data files from PostgreSQL."""

    def __init__(self, connection_string: str):
        self.engine = create_engine(connection_string, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export(self, output_dir: str) -> dict[str, Any]:
        """
        Export 3 JSON files to output_dir/.

        Returns stats dict.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        session = self.SessionLocal()
        try:
            # Bulk-load all dimension maps (title_id → [values])
            genres_map = self._load_dim(session, "dim_genres", "genre")
            tags_map = self._load_dim(session, "dim_tags", "tag")
            countries_map = self._load_dim(session, "dim_countries", "country")
            directors_map = self._load_dim(session, "dim_directors", "director")
            actors_map = self._load_dim(session, "dim_actors", "actor")
            screenwriters_map = self._load_dim(session, "dim_screenwriters", "screenwriter")
            cinematographers_map = self._load_dim(session, "dim_cinematographers", "cinematographer")
            composers_map = self._load_dim(session, "dim_composers", "composer")
            reviews_map = self._load_reviews(session)
            vods_map = self._load_vods(session)   # {title_id: [{platform, url}]}
            tmdb_map = self._load_tmdb(session)   # {title_id: {poster, backdrop, trailer}}

            titles = self._load_titles(session)

            # titles_index.json — lightweight, used for grid/calendar
            index = self._build_index(titles, genres_map, tags_map, countries_map, vods_map, tmdb_map)
            _write(out / "titles_index.json", index)

            # titles_detail.json — full per-title dict, keyed by url_id
            detail = self._build_detail(
                titles, genres_map, tags_map, countries_map, directors_map, actors_map,
                screenwriters_map, cinematographers_map, composers_map, reviews_map, vods_map, tmdb_map,
            )
            _write(out / "titles_detail.json", detail)

            # dimensions.json — sorted lists for facet panel
            dimensions = self._build_dimensions(genres_map, tags_map, countries_map, vods_map)
            _write(out / "dimensions.json", dimensions)

            stats = {
                "success": True,
                "output_dir": str(out.absolute()),
                "total_titles": len(titles),
                "files_written": ["titles_index.json", "titles_detail.json", "dimensions.json"],
                "export_timestamp": datetime.utcnow().isoformat() + "Z",
            }
            logger.info("streamfinder_export_complete", **stats)
            return stats

        except Exception as e:
            logger.error("streamfinder_export_failed", error=str(e))
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Data loaders
    # ------------------------------------------------------------------

    def _load_titles(self, session: Session) -> list[dict]:
        sql = text("""
            SELECT
                title_id, url_id, title, title_en, year, link,
                rating, votes_count, plot, image_url, title_type, parent_url,
                vod_date, distributor, runtime_min, trailer_url, age_rating,
                scraped_at, date_added
            FROM csfd_vod.fact_titles
            ORDER BY vod_date DESC NULLS LAST, title_id DESC
        """)
        cols = [
            "title_id", "url_id", "title", "title_en", "year", "link",
            "rating", "votes_count", "plot", "image_url", "title_type", "parent_url",
            "vod_date", "distributor", "runtime_min", "trailer_url", "age_rating",
            "scraped_at", "date_added",
        ]
        titles = []
        for row in session.execute(sql):
            d = dict(zip(cols, row))
            for k in ("vod_date", "scraped_at", "date_added"):
                if d[k] is not None:
                    d[k] = d[k].isoformat()
            titles.append(d)
        return titles

    def _load_dim(self, session: Session, table: str, col: str) -> dict[int, list[str]]:
        result: dict[int, list[str]] = {}
        for row in session.execute(text(f"SELECT title_id, {col} FROM csfd_vod.{table}")):
            result.setdefault(row[0], []).append(row[1])
        return result

    def _load_vods(self, session: Session) -> dict[int, list[dict]]:
        """Load VOD platforms per title as [{platform, url}]."""
        result: dict[int, list[dict]] = {}
        for row in session.execute(text("SELECT title_id, vod_platform, vod_url FROM csfd_vod.dim_vods")):
            result.setdefault(row[0], []).append({"platform": row[1], "url": row[2]})
        return result

    def _load_reviews(self, session: Session) -> dict[int, list[dict]]:
        """Load top-3 reviews per title ordered by stars DESC."""
        result: dict[int, list[dict]] = {}
        sql = text("""
            SELECT title_id, author, review_text, stars
            FROM csfd_vod.dim_reviews
            ORDER BY title_id, stars DESC NULLS LAST
        """)
        for row in session.execute(sql):
            title_id = row[0]
            if len(result.get(title_id, [])) < 3:
                result.setdefault(title_id, []).append({
                    "author": row[1],
                    "text": row[2],
                    "stars": row[3],
                })
        return result

    def _load_tmdb(self, session: Session) -> dict[int, dict]:
        """Load TMDB metadata per title."""
        result: dict[int, dict] = {}
        sql = text("SELECT title_id, tmdb_id, poster_path, backdrop_path, trailer_youtube_id FROM csfd_vod.dim_tmdb")
        for row in session.execute(sql):
            result[row[0]] = {
                "tmdb_id": row[1],
                "poster_path": row[2],
                "backdrop_path": row[3],
                "trailer_youtube_id": row[4],
            }
        return result

    # ------------------------------------------------------------------
    # Builders
    # ------------------------------------------------------------------

    def _build_index(
        self,
        titles: list[dict],
        genres_map: dict,
        tags_map: dict,
        countries_map: dict,
        vods_map: dict,
        tmdb_map: dict,
    ) -> list[dict]:
        """Lightweight index entry per title for grid/calendar views."""
        index = []
        for t in titles:
            tid = t["title_id"]
            tmdb = tmdb_map.get(tid, {})
            poster = (
                f"{_TMDB_IMG_BASE}/w500{tmdb['poster_path']}"
                if tmdb.get("poster_path")
                else t["image_url"]
            )
            index.append({
                "id": tid,
                "slug": _slug(t["title"], t["year"]),
                "title": t["title"],
                "title_en": t["title_en"],
                "year": t["year"],
                "rating": t["rating"],
                "votes_count": t["votes_count"],
                "runtime_min": t["runtime_min"],
                "title_type": t["title_type"],
                "vod_date": t["vod_date"],
                "poster": poster,
                "genres": genres_map.get(tid, []),
                "tags": tags_map.get(tid, []),
                "countries": countries_map.get(tid, []),
                "platforms": [v["platform"] for v in vods_map.get(tid, [])],
                "link": t["link"],
            })
        return index

    def _build_detail(
        self,
        titles: list[dict],
        genres_map: dict,
        tags_map: dict,
        countries_map: dict,
        directors_map: dict,
        actors_map: dict,
        screenwriters_map: dict,
        cinematographers_map: dict,
        composers_map: dict,
        reviews_map: dict,
        vods_map: dict,
        tmdb_map: dict,
    ) -> dict[str, dict]:
        """Full detail dict keyed by url_id."""
        detail: dict[str, dict] = {}
        for t in titles:
            tid = t["title_id"]
            tmdb = tmdb_map.get(tid, {})
            poster = (
                f"{_TMDB_IMG_BASE}/w500{tmdb['poster_path']}"
                if tmdb.get("poster_path")
                else t["image_url"]
            )
            backdrop = (
                f"{_TMDB_IMG_BASE}/original{tmdb['backdrop_path']}"
                if tmdb.get("backdrop_path")
                else None
            )
            trailer = tmdb.get("trailer_youtube_id") or (
                # Extract YouTube ID from detail-page trailer_url if TMDB has none
                re.search(r"v=([^&]+)", t["trailer_url"]).group(1)
                if t.get("trailer_url") and "v=" in (t["trailer_url"] or "")
                else None
            )
            detail[t["url_id"]] = {
                "id": tid,
                "slug": _slug(t["title"], t["year"]),
                "title": t["title"],
                "title_en": t["title_en"],
                "year": t["year"],
                "rating": t["rating"],
                "votes_count": t["votes_count"],
                "runtime_min": t["runtime_min"],
                "age_rating": t["age_rating"],
                "title_type": t["title_type"],
                "vod_date": t["vod_date"],
                "plot": t["plot"],
                "poster": poster,
                "backdrop": backdrop,
                "trailer_youtube_id": trailer,
                "genres": genres_map.get(tid, []),
                "tags": tags_map.get(tid, []),
                "countries": countries_map.get(tid, []),
                "directors": directors_map.get(tid, []),
                "actors": actors_map.get(tid, []),
                "screenwriters": screenwriters_map.get(tid, []),
                "cinematographers": cinematographers_map.get(tid, []),
                "composers": composers_map.get(tid, []),
                "reviews": reviews_map.get(tid, []),
                "vods": vods_map.get(tid, []),
                "link": t["link"],
            }
        return detail

    def _build_dimensions(
        self,
        genres_map: dict,
        tags_map: dict,
        countries_map: dict,
        vods_map: dict,
    ) -> dict[str, list[dict]]:
        """Sorted dimension lists for facet panels."""
        from collections import Counter

        def sorted_counts(values_per_title: dict) -> list[dict]:
            counts: Counter = Counter(v for vals in values_per_title.values() for v in vals)
            return [{"name": k, "count": v} for k, v in counts.most_common()]

        platform_counts: Counter = Counter(
            v["platform"] for vals in vods_map.values() for v in vals
        )
        return {
            "genres": sorted_counts(genres_map),
            "tags": sorted_counts(tags_map),
            "countries": sorted_counts(countries_map),
            "platforms": [{"name": k, "count": v} for k, v in platform_counts.most_common()],
        }


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
