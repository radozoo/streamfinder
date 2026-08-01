"""TMDB enrichment: fetches poster_path, backdrop_path, trailer_youtube_id per title."""

import time
import unicodedata
from typing import Optional

import requests
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from csfd_vod.logger import get_logger

logger = get_logger(__name__)

_TMDB_BASE = "https://api.themoviedb.org/3"
_RATE_LIMIT_DELAY = 0.27  # ~3.7 req/s → safely under 40 req/10s free tier limit

# Which TMDB endpoint a ČSFD title_type belongs to. TMDB splits its catalog in two
# and the wrong half does not return "no match" — it returns a confident WRONG one,
# which is why the enricher was restricted to films until /search/tv existed here.
# Episodes and seasons are absent on purpose: they inherit their serial's artwork.
_TV_TYPES = frozenset({"seriál", "pořad"})
_MOVIE_TYPES = frozenset({"film", "tv film", "koncert", "divadelní záznam", "studentský film"})
_ENRICHABLE = _TV_TYPES | _MOVIE_TYPES

# How long a fruitless search stays believed. TMDB does grow, so a miss is not
# permanent — but re-asking on every run is what made the last enrich spend 1 285 of
# its 1 295 lookups on questions already answered.
_MISS_RETRY_DAYS = 30

# How far the two catalogs may disagree on a title's year before we stop believing
# it is the same work. 2 covers the systematic domestic-vs-international premiere
# gap with room to spare, without letting a remake of the same name through.
_YEAR_TOLERANCE = 2


def _fold(s: str) -> str:
    """Lowercase, strip diacritics and punctuation — 'S čerty nejsou žerty!' → 'scertynejsouzerty'."""
    stripped = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return "".join(c for c in stripped.lower() if c.isalnum())


def _names_match(query: str, result: dict, exact: bool = False) -> bool:
    """Does a TMDB result plausibly carry the name we searched for?

    Compared against the QUERY that produced it, not the Czech title: for series we
    search the original title first, so that is what the result should look like.

    Non-exact mode allows one name to contain the other, for the sequel numbers and
    article differences the two catalogs spell differently ("Ordinace v růžové
    zahradě" / "Ordinace v růžové zahradě 2"), but only when the lengths are
    comparable. That length ratio is what keeps "MOST!" away from "FBI: Most Wanted"
    — and it also, correctly, refuses "Zaklínač" for the spin-off "Zaklínač: Rod
    krve", which is a different show rather than a spelling of the same one.
    """
    q = _fold(query)
    if not q:
        return False
    for key in ("name", "original_name", "title", "original_title"):
        cand = _fold(result.get(key) or "")
        if not cand:
            continue
        if cand == q:
            return True
        if exact:
            continue
        if (q in cand or cand in q) and min(len(q), len(cand)) / max(len(q), len(cand)) >= 0.6:
            return True
    return False


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

            for i, (title_id, title, title_en, year, title_type) in enumerate(titles):
                try:
                    result = self._enrich_one(session, title_id, title, title_en, year, title_type)
                    # Commit per title so one failure (e.g. a duplicate TMDB match)
                    # can be rolled back in isolation without poisoning the rest of
                    # the run with InFailedSqlTransaction.
                    session.commit()
                    if result:
                        stats["enriched"] += 1
                    else:
                        stats["skipped"] += 1

                    if (i + 1) % 50 == 0:
                        logger.info("tmdb_enrich_progress", done=i + 1, total=len(titles))

                    time.sleep(_RATE_LIMIT_DELAY)

                except Exception as e:
                    session.rollback()
                    logger.warning("tmdb_enrich_error", title_id=title_id, title=title, error=str(e))
                    stats["failed"] += 1

            logger.info("tmdb_enrich_complete", **stats)
            return stats

        finally:
            session.close()

    def _load_pending(self, session: Session, limit: Optional[int], force: bool) -> list:
        """Load titles that need TMDB enrichment.

        Ordered by votes_count so that if a run is cut short by a limit or an
        interruption, what got enriched is what most people will actually see.
        """
        if force:
            sql = text("""
                SELECT title_id, title, title_en, year, title_type
                FROM csfd_vod.fact_titles
                WHERE title_type = ANY(:types)
                ORDER BY votes_count DESC NULLS LAST
                LIMIT :limit
            """)
        else:
            # Skip titles searched recently and not found — see _MISS_RETRY_DAYS.
            sql = text("""
                SELECT f.title_id, f.title, f.title_en, f.year, f.title_type
                FROM csfd_vod.fact_titles f
                LEFT JOIN csfd_vod.dim_tmdb t USING (title_id)
                LEFT JOIN csfd_vod.tmdb_misses m USING (title_id)
                WHERE f.title_type = ANY(:types)
                  AND t.tmdb_id IS NULL
                  AND (m.title_id IS NULL
                       OR m.last_tried_at < CURRENT_TIMESTAMP - make_interval(days => :retry_days))
                ORDER BY f.votes_count DESC NULLS LAST
                LIMIT :limit
            """)
        rows = session.execute(
            sql,
            {
                "limit": limit or 99999,
                "types": sorted(_ENRICHABLE),
                "retry_days": _MISS_RETRY_DAYS,
            },
        ).fetchall()
        return rows

    def _record_miss(self, session: Session, title_id: int) -> None:
        session.execute(
            text("""
                INSERT INTO csfd_vod.tmdb_misses (title_id)
                VALUES (:title_id)
                ON CONFLICT (title_id) DO UPDATE SET
                    attempts = csfd_vod.tmdb_misses.attempts + 1,
                    last_tried_at = CURRENT_TIMESTAMP
            """),
            {"title_id": title_id},
        )

    def _enrich_one(
        self,
        session: Session,
        title_id: int,
        title: str,
        title_en: Optional[str],
        year: Optional[int],
        title_type: Optional[str],
    ) -> bool:
        """Search TMDB and upsert dim_tmdb. Returns True if match found."""
        is_tv = title_type in _TV_TYPES

        # Films: the Czech title first — ČSFD's distributor names match TMDB's Czech
        # release titles well. Series: the original title first, because TMDB indexes
        # series under it and localises less consistently.
        queries = [title_en, title] if is_tv else [title, title_en]
        for query in filter(None, queries):
            result = self._search(query, year, is_tv)
            if result:
                break
        else:
            self._record_miss(session, title_id)
            return False

        tmdb_id = result["id"]
        poster_path = result.get("poster_path")
        backdrop_path = result.get("backdrop_path")
        trailer_id = self._get_trailer(tmdb_id, is_tv)

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

    def _search(self, query: str, year: Optional[int], is_tv: bool) -> Optional[dict]:
        """Search TMDB for a movie or a series. Returns best match or None.

        The year is used as a FILTER on the results, never as a query parameter.
        TMDB's `year`/`first_air_date_year` match exactly, and the two catalogs
        disagree by a year as a rule rather than an exception: ČSFD dates by the
        domestic premiere, TMDB by international release. Spalovač mrtvol is 1968
        here and 1969 there; Postřižiny 1980 and 1981; S čerty nejsou žerty 1984
        and 1985. Passing the year returned nothing for all of them — that is a
        large share of the films that looked permanently unmatchable, and they are
        the most-watched ones.

        So: ask without the year, then accept the first candidate within
        _YEAR_TOLERANCE. Same precision, without the off-by-one blind spot.
        """
        kind = "tv" if is_tv else "movie"
        date_field = "first_air_date" if is_tv else "release_date"
        try:
            resp = self._session.get(
                f"{_TMDB_BASE}/search/{kind}", params={"query": query}, timeout=10
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except requests.RequestException as e:
            logger.warning("tmdb_search_failed", query=query, kind=kind, error=str(e))
            return None

        if not results:
            return None

        in_window = [
            r
            for r in results[:10]
            if not year
            or (
                (r.get(date_field) or "")[:4].isdigit()
                and abs(int((r.get(date_field) or "")[:4]) - year) <= _YEAR_TOLERANCE
            )
        ]
        if not in_window:
            # Results exist but none is from anywhere near the right year — more
            # likely a different work of the same name than our year being wrong.
            return None

        # The year window alone is not enough. TMDB ranks by popularity, so a short
        # or common title pulls in a big unrelated show: the Czech series "MOST!"
        # matched "FBI: Most Wanted" (2020, inside the window). Require the names to
        # actually correspond, and prefer an exact one when several qualify.
        named = [r for r in in_window if _names_match(query, r)]
        if not named:
            return None
        return next((r for r in named if _names_match(query, r, exact=True)), named[0])

    def _get_trailer(self, tmdb_id: int, is_tv: bool = False) -> Optional[str]:
        """Fetch YouTube trailer key for a TMDB movie or series ID."""
        try:
            kind = "tv" if is_tv else "movie"
            resp = self._session.get(f"{_TMDB_BASE}/{kind}/{tmdb_id}/videos", timeout=10)
            resp.raise_for_status()
            for v in resp.json().get("results", []):
                if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser"):
                    return v["key"]
        except requests.RequestException:
            pass
        return None
