"""TMDB enrichment: fetches poster_path, backdrop_path, trailer_youtube_id per title."""

import time
from typing import Optional

import requests
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from csfd_vod.logger import get_logger

logger = get_logger(__name__)

_TMDB_BASE = "https://api.themoviedb.org/3"
_RATE_LIMIT_DELAY = 0.27  # ~3.7 req/s → safely under 40 req/10s free tier limit


class TMDBEnricher:
    """Enrich fact_titles with TMDB metadata (poster, backdrop, trailer)."""

    def __init__(self, api_key: str, connection_string: str):
        self.api_key = api_key
        self.engine = create_engine(connection_string, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._session = requests.Session()
        self._session.params = {"api_key": api_key, "language": "cs"}

    def enrich(self, limit: Optional[int] = None, force: bool = False) -> dict:
        """
        Enrich titles not yet in dim_tmdb.

        Args:
            limit: Max titles to process (None = all pending)
            force: Re-enrich titles already in dim_tmdb

        Returns:
            Stats dict with enriched/skipped/failed counts.
        """
        session = self.SessionLocal()
        try:
            titles = self._load_pending(session, limit, force)
            logger.info("tmdb_enrich_start", pending=len(titles))

            stats = {"enriched": 0, "skipped": 0, "failed": 0, "total": len(titles)}

            for i, (title_id, title, title_en, year) in enumerate(titles):
                try:
                    result = self._enrich_one(session, title_id, title, title_en, year)
                    if result:
                        stats["enriched"] += 1
                    else:
                        stats["skipped"] += 1

                    if (i + 1) % 50 == 0:
                        session.commit()
                        logger.info("tmdb_enrich_progress", done=i + 1, total=len(titles))

                    time.sleep(_RATE_LIMIT_DELAY)

                except Exception as e:
                    logger.warning("tmdb_enrich_error", title_id=title_id, title=title, error=str(e))
                    stats["failed"] += 1

            session.commit()
            logger.info("tmdb_enrich_complete", **stats)
            return stats

        finally:
            session.close()

    def _load_pending(self, session: Session, limit: Optional[int], force: bool) -> list:
        """Load titles that need TMDB enrichment."""
        if force:
            sql = text("""
                SELECT title_id, title, title_en, year
                FROM csfd_vod.fact_titles
                WHERE title_type = 'film'
                ORDER BY votes_count DESC NULLS LAST
                LIMIT :limit
            """)
        else:
            sql = text("""
                SELECT f.title_id, f.title, f.title_en, f.year
                FROM csfd_vod.fact_titles f
                LEFT JOIN csfd_vod.dim_tmdb t USING (title_id)
                WHERE f.title_type = 'film' AND t.tmdb_id IS NULL
                ORDER BY f.votes_count DESC NULLS LAST
                LIMIT :limit
            """)
        rows = session.execute(sql, {"limit": limit or 99999}).fetchall()
        return rows

    def _enrich_one(
        self,
        session: Session,
        title_id: int,
        title: str,
        title_en: Optional[str],
        year: Optional[int],
    ) -> bool:
        """Search TMDB and upsert dim_tmdb. Returns True if match found."""
        # Try Czech title first, fallback to English
        for query in filter(None, [title, title_en]):
            result = self._search_movie(query, year)
            if result:
                break
        else:
            return False

        tmdb_id = result["id"]
        poster_path = result.get("poster_path")
        backdrop_path = result.get("backdrop_path")
        trailer_id = self._get_trailer(tmdb_id)

        session.execute(
            text("""
                INSERT INTO csfd_vod.dim_tmdb
                    (tmdb_id, title_id, poster_path, backdrop_path, trailer_youtube_id)
                VALUES
                    (:tmdb_id, :title_id, :poster_path, :backdrop_path, :trailer_youtube_id)
                ON CONFLICT (title_id)
                DO UPDATE SET
                    tmdb_id = EXCLUDED.tmdb_id,
                    poster_path = EXCLUDED.poster_path,
                    backdrop_path = EXCLUDED.backdrop_path,
                    trailer_youtube_id = EXCLUDED.trailer_youtube_id,
                    enriched_at = CURRENT_TIMESTAMP
            """),
            {
                "tmdb_id": tmdb_id,
                "title_id": title_id,
                "poster_path": poster_path,
                "backdrop_path": backdrop_path,
                "trailer_youtube_id": trailer_id,
            },
        )
        return True

    def _search_movie(self, query: str, year: Optional[int]) -> Optional[dict]:
        """Search TMDB for a movie. Returns best match or None."""
        params = {"query": query}
        if year:
            params["year"] = year
        try:
            resp = self._session.get(f"{_TMDB_BASE}/search/movie", params=params, timeout=10)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            return results[0] if results else None
        except requests.RequestException as e:
            logger.warning("tmdb_search_failed", query=query, error=str(e))
            return None

    def _get_trailer(self, tmdb_id: int) -> Optional[str]:
        """Fetch YouTube trailer key for a TMDB movie ID."""
        try:
            resp = self._session.get(f"{_TMDB_BASE}/movie/{tmdb_id}/videos", timeout=10)
            resp.raise_for_status()
            for v in resp.json().get("results", []):
                if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser"):
                    return v["key"]
        except requests.RequestException:
            pass
        return None
