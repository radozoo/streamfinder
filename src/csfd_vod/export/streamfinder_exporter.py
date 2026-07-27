"""Streamfinder JSON exporter.

Produces these outputs for the SvelteKit static site:
  - titles_index.json   lightweight grid data (~3MB) used for Katalog + Kalendar
  - detail/{id}-{slug}.json  one full per-title file (plot, reviews, crew, vod_urls),
    fetched on demand — a single combined titles_detail.json outgrew 60MB and every
    page (including the single-title route) was downloading all of it just to read
    one entry.
  - dimensions.json     flat lookup tables (genres, tags, platforms, countries, top crew)
  - crew_index.json     crew lookup table for lazy-loaded filtering (~26k entries)
"""

import json
import re
import shutil
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
    if year is not None:
        slug = f"{slug}-{year}"
    return slug


def _poster_url(t: dict, tmdb_map: dict) -> str | None:
    """TMDB poster if enriched, else the ČSFD image."""
    tmdb = tmdb_map.get(t["title_id"], {})
    if tmdb.get("poster_path"):
        return f"{_TMDB_IMG_BASE}/w500{tmdb['poster_path']}"
    return t["image_url"]


def _root_posters(titles: list[dict], tmdb_map: dict) -> dict[int, str]:
    """Map root_id → the top-level work's poster, so posterless episodes/seasons
    can inherit their serial's artwork."""
    return {
        t["root_id"]: _poster_url(t, tmdb_map)
        for t in titles
        if t["root_id"] is not None and t["root_id"] == t["csfd_id"]
    }


# Show the primary streaming service first; Czech IPTV re-streamers
# (SledovaniTV, Lepší.TV, Telly) rank last so they never mask HBO Max/Netflix/etc.
_PLATFORM_PRIORITY = {
    name: i
    for i, name in enumerate([
        "Netflix", "HBO Max", "Max", "Disney+", "Apple TV+", "Apple TV",
        "Prime Video", "Prime", "Paramount+", "SkyShowtime", "Crunchyroll",
        "Canal+", "Hulu", "Peacock", "Showtime", "AMC+", "MGM+", "Discovery+",
        "BBC iPlayer", "ITVX", "Acorn TV", "Movistar+", "Viaplay", "WOW Presents Plus",
        "prima+", "Voyo", "YouTube", "YouTube Movies", "YouTube Premium",
        "Oneplay", "iVysílání", "Stream.cz", "Televize Seznam", "MALL.TV", "JOJ Play",
        "Rakuten.tv", "DAFilms", "KVIFF.TV", "Telly", "SledovaniTV", "Lepší.TV",
    ])
}


def _sort_platforms(names: list[str]) -> list[str]:
    """De-dup and order platforms so the primary service leads."""
    seen: list[str] = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return sorted(seen, key=lambda n: _PLATFORM_PRIORITY.get(n, 900))


def _root_platforms(titles: list[dict], vods_map: dict) -> dict[int, list[str]]:
    """Map root_id → the top-level work's platforms, so episodes with no platform of
    their own inherit their serial's (they drop on the same service)."""
    out: dict[int, list[str]] = {}
    for t in titles:
        if t["root_id"] is not None and t["root_id"] == t["csfd_id"]:
            plats = [v["platform"] for v in vods_map.get(t["title_id"], [])]
            if plats:
                out[t["root_id"]] = plats
    return out


def _root_vods(titles: list[dict], vods_map: dict) -> dict[int, list[dict]]:
    """Map root_id → the top-level work's [{platform, url}] list (for episode modals)."""
    out: dict[int, list[dict]] = {}
    for t in titles:
        if t["root_id"] is not None and t["root_id"] == t["csfd_id"]:
            v = vods_map.get(t["title_id"])
            if v:
                out[t["root_id"]] = v
    return out


def _child_platforms(titles: list[dict], vods_map: dict) -> dict[int, list[str]]:
    """Map root_id → union of its children's platforms, so a serial with no platform
    of its own (never listed on /vod as a whole) still shows where its episodes air."""
    out: dict[int, list[str]] = {}
    for t in titles:
        rid = t["root_id"]
        if rid is not None and rid != t["csfd_id"]:  # a child (episode/season)
            for v in vods_map.get(t["title_id"], []):
                bucket = out.setdefault(rid, [])
                if v["platform"] not in bucket:
                    bucket.append(v["platform"])
    return out


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
        Export 4 JSON files to output_dir/.

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
            kviff_ids = self._load_kviff_flags(session)

            titles = self._load_titles(session)

            # Work↔Release hierarchy + per-serial aggregates (season/episode counts,
            # cadence, release timeline) derived from root_id/csfd_id.
            root_title_id, serial_agg, episodes_map = self._build_hierarchy(titles, vods_map)

            # Build crew lookup and per-title crew ID mapping
            crew_list, title_crew_map = self._load_crew(
                directors_map, actors_map, screenwriters_map, cinematographers_map, composers_map,
            )

            # crew_index.json — lazy-loaded crew lookup for filtering
            _write(out / "crew_index.json", crew_list)

            # titles_index.json — lightweight, used for grid/calendar (now includes crew_ids)
            index = self._build_index(
                titles, genres_map, tags_map, countries_map, vods_map, tmdb_map,
                title_crew_map, root_title_id, serial_agg, kviff_ids,
            )
            _write(out / "titles_index.json", index)

            # detail/{title_id}-{slug}.json — one file per title, fetched on demand
            detail = self._build_detail(
                titles, genres_map, tags_map, countries_map, directors_map, actors_map,
                screenwriters_map, cinematographers_map, composers_map, reviews_map, vods_map, tmdb_map,
                episodes_map, serial_agg, root_title_id,
            )
            _write_detail_shards(out / "detail", detail)

            # dimensions.json — sorted lists for facet panel (now includes top crew)
            dimensions = self._build_dimensions(genres_map, tags_map, countries_map, vods_map, crew_list)
            _write(out / "dimensions.json", dimensions)

            stats = {
                "success": True,
                "output_dir": str(out.absolute()),
                "total_titles": len(titles),
                "crew_entries": len(crew_list),
                "detail_files": len(detail),
                "files_written": ["titles_index.json", f"detail/ ({len(detail)} files)", "dimensions.json", "crew_index.json"],
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
                scraped_at, date_added,
                csfd_id, root_id, season_no, episode_no, season_total, episode_total
            FROM csfd_vod.fact_titles
            ORDER BY vod_date DESC NULLS LAST, title_id DESC
        """)
        cols = [
            "title_id", "url_id", "title", "title_en", "year", "link",
            "rating", "votes_count", "plot", "image_url", "title_type", "parent_url",
            "vod_date", "distributor", "runtime_min", "trailer_url", "age_rating",
            "scraped_at", "date_added",
            "csfd_id", "root_id", "season_no", "episode_no", "season_total", "episode_total",
        ]
        titles = []
        for row in session.execute(sql):
            d = dict(zip(cols, row))
            for k in ("vod_date", "scraped_at", "date_added"):
                if d[k] is not None:
                    d[k] = d[k].isoformat()
            titles.append(d)
        return self._dedupe(titles)

    # A title page overview URL: /film/{id}[-slug]/[{id}[-slug]/]prehled/ , no query.
    _OVERVIEW_RE = re.compile(r"^https://www\.csfd\.cz/film/\d+[^/?]*/(?:\d+[^/?]*/)?prehled/$")
    # Pre-air placeholder episode slugs CSFD later renames (episode-5 → pamet).
    _PLACEHOLDER_RE = re.compile(r"/\d+-(?:episode|epizoda)-\d+/prehled/$")

    def _dedupe(self, titles: list[dict]) -> list[dict]:
        """Collapse rows that denote the same ČSFD title, and drop non-title junk.

        Two failure modes this guards against (both seen in the DB):
          - **Slug drift** — ČSFD renames an episode/film slug over time
            (episode-5 → pamet, the-miniature-wife → miniaturni-manzelka). Because
            url_id carries the slug, the loader inserts a *second* row for the same
            csfd_id, so the catalog/calendar shows the title twice.
          - **Non-overview rows** — old data where a /recenze/ or ?comment= URL got
            stored as a title.

        csfd_id is ČSFD's stable identity, so rows sharing one are the same title:
        keep the richest (rated > unrated, more votes, has a date, real slug over a
        placeholder, newest as a tiebreak). This is a belt-and-suspenders net at the
        export boundary — the DB is also cleaned and the loader collapses by csfd_id,
        but nothing that reaches the site should ever render a title twice.
        """
        def rank(d: dict) -> tuple:
            url = d["url_id"] or ""
            return (
                1 if d["rating"] is not None else 0,
                d["votes_count"] or 0,
                1 if d["vod_date"] else 0,
                0 if self._PLACEHOLDER_RE.search(url) else 1,
                d["title_id"] or 0,
            )

        best: dict = {}
        passthrough: list[dict] = []
        for d in titles:
            url = d["url_id"] or ""
            if not self._OVERVIEW_RE.match(url):
                continue  # drop /recenze/, ?comment=, and other non-title rows
            cid = d["csfd_id"]
            if cid is None:
                passthrough.append(d)  # no stable id → can't dedupe, keep as-is
                continue
            if cid not in best or rank(d) > rank(best[cid]):
                best[cid] = d
        return list(best.values()) + passthrough

    def _load_dim(self, session: Session, table: str, col: str) -> dict[int, list[str]]:
        result: dict[int, list[str]] = {}
        for row in session.execute(text(f"SELECT title_id, {col} FROM csfd_vod.{table}")):
            result.setdefault(row[0], []).append(row[1])
        return result

    def _load_vods(self, session: Session) -> dict[int, list[dict]]:
        """Load VOD platforms per title as [{platform, url}].

        "VOD" is a generic ČSFD category, not a real streaming service — it is
        always emitted alongside the actual platform (Netflix, HBO Max, …), so
        it is dropped here to keep cards, filters and detail clean.
        """
        result: dict[int, list[dict]] = {}
        for row in session.execute(text("SELECT title_id, vod_platform, vod_url FROM csfd_vod.dim_vods")):
            if row[1] == "VOD":
                continue
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

    def _load_kviff_flags(self, session: Session) -> set[int]:
        """Title ids whose plot or a review mentions KVIFF / Karlovy Vary — the
        Czech A-list festival, a high-precision arthouse signal (unlike genre or
        rating, an actual curatorial fact about the film). Scans ALL reviews, not
        just the top-3 kept in reviews_map, since a KVIFF mention is rare and easy
        to miss if it isn't the highest-starred one."""
        sql = text("""
            SELECT title_id FROM csfd_vod.fact_titles WHERE plot ~* 'kviff|karlov[ýy]\\s*var'
            UNION
            SELECT title_id FROM csfd_vod.dim_reviews WHERE review_text ~* 'kviff|karlov[ýy]\\s*var'
        """)
        return {row[0] for row in session.execute(sql)}

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

    def _load_crew(
        self,
        directors_map: dict[int, list[str]],
        actors_map: dict[int, list[str]],
        screenwriters_map: dict[int, list[str]],
        cinematographers_map: dict[int, list[str]],
        composers_map: dict[int, list[str]],
    ) -> tuple[list[dict], dict[int, list[int]]]:
        """Build crew lookup and per-title crew ID mapping.

        Returns:
            (crew_list, title_crew_map)
            - crew_list: [{id, name, role, count}] sorted by count desc, filtered to 2+ appearances
            - title_crew_map: {title_id: [crew_id, ...]} for titles_index.json
        """
        from collections import Counter

        _ROLE_MAP = {
            "directors": "rezie",
            "actors": "herec",
            "screenwriters": "scenar",
            "cinematographers": "kamera",
            "composers": "hudba",
        }

        # Count (name, role) occurrences across all titles
        name_role_counts: Counter = Counter()
        role_sources = {
            "directors": directors_map,
            "actors": actors_map,
            "screenwriters": screenwriters_map,
            "cinematographers": cinematographers_map,
            "composers": composers_map,
        }
        for role_key, dim_map in role_sources.items():
            role = _ROLE_MAP[role_key]
            for names in dim_map.values():
                for name in names:
                    name_role_counts[(name, role)] += 1

        # Filter to 2+ appearances, assign IDs, sort by count desc
        crew_list: list[dict] = []
        crew_id_lookup: dict[tuple[str, str], int] = {}
        for idx, ((name, role), count) in enumerate(name_role_counts.most_common()):
            if count < 2:
                break
            crew_id = idx + 1
            crew_list.append({"id": crew_id, "name": name, "role": role, "count": count})
            crew_id_lookup[(name, role)] = crew_id

        # Build per-title crew_ids mapping
        title_crew_map: dict[int, list[int]] = {}
        for role_key, dim_map in role_sources.items():
            role = _ROLE_MAP[role_key]
            for title_id, names in dim_map.items():
                for name in names:
                    cid = crew_id_lookup.get((name, role))
                    if cid is not None:
                        title_crew_map.setdefault(title_id, []).append(cid)

        return crew_list, title_crew_map

    # ------------------------------------------------------------------
    # Builders
    # ------------------------------------------------------------------

    def _build_hierarchy(self, titles: list[dict], vods_map: dict):
        """Derive Work↔Release links and per-serial aggregates.

        Returns (root_title_id, serial_agg, episodes_map):
          root_title_id[root_id] = title_id of the top-level row for that root
          serial_agg[root_id]    = {season_count, episode_count, first_vod_date,
                                     last_vod_date, is_running, cadence_days}
          episodes_map[root_id]  = sorted release list for the modal timeline
        """
        from datetime import date, timedelta
        from statistics import median

        def _d(s):
            return date.fromisoformat(s) if s else None

        global_max = max((_d(t["vod_date"]) for t in titles if t["vod_date"]), default=None)

        root_title_id: dict[int, int] = {}
        children: dict[int, list[dict]] = {}
        for t in titles:
            rid, cid = t["root_id"], t["csfd_id"]
            if rid is None:
                continue
            if cid == rid:
                root_title_id[rid] = t["title_id"]
            else:
                children.setdefault(rid, []).append(t)

        serial_agg: dict[int, dict] = {}
        episodes_map: dict[int, list[dict]] = {}
        for rid, kids in children.items():
            seasons = [k["season_no"] for k in kids if k["season_no"]]
            serie_rows = [k for k in kids if k["title_type"] == "série"]
            ep_rows = [k for k in kids if k["title_type"] == "epizoda" or k["episode_no"]]
            if seasons:
                season_count = max(seasons)
            elif serie_rows:
                season_count = len(serie_rows)
            else:
                season_count = 1  # has episodes but no season markers → assume one season
            ep_dates = sorted(_d(k["vod_date"]) for k in ep_rows if k["vod_date"])
            gaps = [(b - a).days for a, b in zip(ep_dates, ep_dates[1:])]
            serial_agg[rid] = {
                "season_count": season_count,
                "episode_count": len(ep_rows),
                "first_vod_date": ep_dates[0].isoformat() if ep_dates else None,
                "last_vod_date": ep_dates[-1].isoformat() if ep_dates else None,
                "is_running": bool(
                    ep_dates and global_max and ep_dates[-1] >= global_max - timedelta(days=21)
                ),
                "cadence_days": round(median(gaps)) if gaps else None,
            }
            episodes_map[rid] = [
                {
                    "season_no": k["season_no"],
                    "episode_no": k["episode_no"],
                    "vod_date": k["vod_date"],
                    "title": k["title"].split("\n")[0].strip(),
                    "platforms": [v["platform"] for v in vods_map.get(k["title_id"], [])],
                }
                for k in sorted(
                    ep_rows,
                    key=lambda k: (k["season_no"] or 0, k["episode_no"] or 0, k["vod_date"] or ""),
                )
            ]
        return root_title_id, serial_agg, episodes_map

    def _build_index(
        self,
        titles: list[dict],
        genres_map: dict,
        tags_map: dict,
        countries_map: dict,
        vods_map: dict,
        tmdb_map: dict,
        title_crew_map: dict[int, list[int]],
        root_title_id: dict[int, int],
        serial_agg: dict[int, dict],
        kviff_ids: set[int],
    ) -> list[dict]:
        """Lightweight index entry per title for grid/calendar views."""
        root_poster = _root_posters(titles, tmdb_map)
        root_platforms = _root_platforms(titles, vods_map)
        child_platforms = _child_platforms(titles, vods_map)
        # Rating inheritance sources: a brand-new episode has no rating of its own,
        # so it borrows the season's, else the serial's (see _inherited_rating).
        root_rating: dict[int, int] = {}
        season_rating: dict[tuple, int] = {}
        for t in titles:
            rid = t["root_id"]
            if rid is None or t["rating"] is None:
                continue
            if rid == t["csfd_id"]:
                root_rating[rid] = t["rating"]
            elif t["title_type"] == "série" and t["season_no"] is not None:
                season_rating[(rid, t["season_no"])] = t["rating"]
        index = []
        for t in titles:
            tid = t["title_id"]
            rid = t["root_id"]
            is_toplevel = rid is not None and rid == t["csfd_id"]
            poster = _poster_url(t, tmdb_map)
            if not poster and not is_toplevel:
                poster = root_poster.get(rid)  # episode/season inherits serial artwork
            platforms = [v["platform"] for v in vods_map.get(tid, [])]
            if is_toplevel:
                # A serial never listed on /vod as a whole shows where its episodes air.
                if not platforms:
                    platforms = child_platforms.get(rid, [])
            else:
                # An episode belongs to its show — the serial's platform list is
                # fuller and primary-first; fall back to the episode's own only if
                # the serial has none (its /vod entry is often just an IPTV reseller).
                platforms = root_platforms.get(rid) or platforms
            platforms = _sort_platforms(platforms)
            entry = {
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
                "platforms": platforms,
                "crew_ids": title_crew_map.get(tid, []),
                "link": t["link"],
                # hierarchy — Work vs. Release
                "root_id": rid,
                "root_title_id": root_title_id.get(rid) if not is_toplevel else None,
                "is_toplevel": is_toplevel,
                "season_no": t["season_no"],
                "episode_no": t["episode_no"],
            }
            if tid in kviff_ids:
                entry["kviff"] = True
            # A fresh episode/season with no rating of its own borrows one to show,
            # clearly marked as inherited so it never poses as the episode's own score.
            if not is_toplevel and t["rating"] is None:
                inh = self._inherited_rating(rid, t["season_no"], root_rating, season_rating)
                if inh is not None:
                    entry["inherited_rating"], entry["inherited_from"] = inh
            # Serial shape on the top-level work card (season/episode counts, running).
            if is_toplevel:
                shape = self._serial_shape(t, serial_agg)
                if shape:
                    entry.update(shape)
            index.append(entry)
        return index

    @staticmethod
    def _inherited_rating(rid, season_no, root_rating: dict, season_rating: dict) -> tuple | None:
        """A non-top-level row's fallback rating: season first, then serial.
        Returns (rating, source) where source is 'série' or 'seriál', or None."""
        if season_no is not None and (rid, season_no) in season_rating:
            return season_rating[(rid, season_no)], "série"
        if rid in root_rating:
            return root_rating[rid], "seriál"
        return None

    def _serial_shape(self, t: dict, serial_agg: dict) -> dict | None:
        """Card shape for a top-level work. Season/episode counts prefer the
        authoritative page totals ("Série (N) Epizody (M)") and fall back to what we
        scraped from VOD; running/cadence always reflect the VOD releases."""
        agg = serial_agg.get(t["root_id"], {})
        season_count = t["season_total"] or agg.get("season_count")
        episode_count = t["episode_total"] or agg.get("episode_count")
        if not season_count and not episode_count and not agg:
            return None
        return {
            "season_count": season_count,
            "episode_count": episode_count,
            "is_running": agg.get("is_running", False),
            "cadence_days": agg.get("cadence_days"),
            "first_vod_date": agg.get("first_vod_date"),
            "last_vod_date": agg.get("last_vod_date"),
        }

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
        episodes_map: dict[int, list[dict]],
        serial_agg: dict[int, dict],
        root_title_id: dict[int, int],
    ) -> dict[str, dict]:
        """Full detail dict keyed by '{title_id}-{slug}'."""
        root_poster = _root_posters(titles, tmdb_map)
        root_vods = _root_vods(titles, vods_map)
        detail: dict[str, dict] = {}
        for t in titles:
            tid = t["title_id"]
            rid = t["root_id"]
            is_toplevel = rid is not None and rid == t["csfd_id"]
            tmdb = tmdb_map.get(tid, {})
            poster = _poster_url(t, tmdb_map)
            if not poster and not is_toplevel:
                poster = root_poster.get(rid)  # episode/season inherits serial artwork
            vods = vods_map.get(tid, [])
            if not is_toplevel:
                vods = root_vods.get(rid) or vods  # episode shows its show's services
            vods = sorted(vods, key=lambda v: _PLATFORM_PRIORITY.get(v["platform"], 900))
            backdrop = (
                f"{_TMDB_IMG_BASE}/original{tmdb['backdrop_path']}"
                if tmdb.get("backdrop_path")
                else None
            )
            yt_match = re.search(r"v=([^&#]+)", t.get("trailer_url") or "")
            trailer = tmdb.get("trailer_youtube_id") or (yt_match.group(1) if yt_match else None)
            slug = _slug(t["title"], t["year"])
            detail[f"{tid}-{slug}"] = {
                "id": tid,
                "slug": slug,
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
                "vods": vods,
                "link": t["link"],
                # hierarchy — Work vs. Release
                "root_id": rid,
                "root_title_id": root_title_id.get(rid) if not is_toplevel else None,
                "is_toplevel": is_toplevel,
                "season_no": t["season_no"],
                "episode_no": t["episode_no"],
            }
            # Release timeline + serial shape on the top-level work.
            if is_toplevel:
                shape = self._serial_shape(t, serial_agg)
                if shape:
                    detail[f"{tid}-{slug}"].update(shape)
                if rid in episodes_map:
                    detail[f"{tid}-{slug}"]["episodes"] = episodes_map[rid]
        return detail

    def _build_dimensions(
        self,
        genres_map: dict,
        tags_map: dict,
        countries_map: dict,
        vods_map: dict,
        crew_list: list[dict],
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
            "crew": [{"name": c["name"], "role": c["role"], "count": c["count"]} for c in crew_list[:50]],
        }


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _write_detail_shards(dir_path: Path, detail: dict[str, dict]) -> None:
    """One JSON file per title, keyed by filename '{title_id}-{slug}.json'. The
    directory is rebuilt from scratch each export so a slug-drift rename (a title's
    filename changing between runs) can't leave a stale orphaned file behind."""
    if dir_path.exists():
        shutil.rmtree(dir_path)
    dir_path.mkdir(parents=True)
    for key, entry in detail.items():
        _write(dir_path / f"{key}.json", entry)
