#!/usr/bin/env python3
"""Collapse duplicate ČSFD titles and drop non-title junk rows.

Two failure modes this repairs (see docs/csfd-scraping-rules.md §"Slug drift"):

  1. Slug drift — ČSFD renames a film/episode slug over time
     (…/1622613-episode-5/prehled/ → …/1622613-pamet/prehled/,
      …/1723354-the-miniature-wife/… → …/1723354-miniaturni-manzelka/…).
     Because url_id carries the slug, the loader inserts a *second* row for the
     same csfd_id, and the catalog/calendar then shows the title twice.
  2. Non-overview rows — legacy data where a /recenze/ or ?comment= URL got
     stored as a title.

csfd_id is ČSFD's stable identity, so rows sharing one are the same title. We
keep the richest (rated > unrated, more votes, has a VOD date, a real slug over a
pre-air placeholder, newest as a tiebreak) and remove the rest — from the DB
(dimensions cascade), the HTML cache, and cache/vod_urls.json, so a later
`parse` can't resurrect the stale row.

Usage:
    python3 scripts/dedupe_titles.py            # dry run — report only
    python3 scripts/dedupe_titles.py --apply    # perform the cleanup

Also importable: `dedupe(loader, cache, cache_dir, apply=True) -> dict`, which
`csfd_vod.main update` calls so every update self-heals.
"""
import argparse
import json
from pathlib import Path

from sqlalchemy import text

# Same overview shape the exporter guard uses: /film/{id}[-slug]/[{id}[-slug]/]prehled/
_OVERVIEW = r'^https://www\.csfd\.cz/film/\d+[^/?]*/(\d+[^/?]*/)?prehled/$'
# A pre-air placeholder episode slug (episode-5 / epizoda-10) ČSFD later renames.
_PLACEHOLDER = r'/\d+-(episode|epizoda)-\d+/prehled/$'

# Rank rows within a csfd_id; row_number 1 is the keeper, the rest are removed.
_RANKED_LOSERS = text(f"""
    WITH ranked AS (
        SELECT title_id, url_id,
            row_number() OVER (
                PARTITION BY csfd_id
                ORDER BY (rating IS NOT NULL) DESC,
                         coalesce(votes_count, 0) DESC,
                         (vod_date IS NOT NULL) DESC,
                         (url_id ~ '{_PLACEHOLDER}') ASC,
                         title_id DESC
            ) AS rn
        FROM csfd_vod.fact_titles
        WHERE csfd_id IS NOT NULL
          AND url_id ~ '{_OVERVIEW}'
    )
    SELECT title_id, url_id FROM ranked WHERE rn > 1
""")

# Rows whose url_id is not a title-overview page at all (/recenze/, ?comment=, …).
_NON_OVERVIEW = text(f"SELECT title_id, url_id FROM csfd_vod.fact_titles WHERE url_id !~ '{_OVERVIEW}'")


def _remove_rows(session, title_ids: list[int]) -> None:
    if not title_ids:
        return
    session.execute(
        text("DELETE FROM csfd_vod.fact_titles WHERE title_id = ANY(:ids)"),
        {"ids": title_ids},
    )


def dedupe(loader, cache=None, cache_dir: str | None = None, apply: bool = False) -> dict:
    """Find (and optionally remove) duplicate/junk title rows.

    Returns a summary dict: counts + a small sample, and the removed url_ids.
    When apply=True and a cache/cache_dir is given, also deletes the stale HTML
    and prunes cache/vod_urls.json so `parse` won't re-insert them.
    """
    session = loader.SessionLocal()
    try:
        dup = [(r[0], r[1]) for r in session.execute(_RANKED_LOSERS)]
        junk = [(r[0], r[1]) for r in session.execute(_NON_OVERVIEW)]
        removed = dup + junk
        removed_ids = [tid for tid, _ in removed]
        removed_urls = [u for _, u in removed]

        summary = {
            "dup_slug_drift": len(dup),
            "non_overview": len(junk),
            "total_removed": len(removed),
            "sample": removed_urls[:15],
        }

        if apply and removed_ids:
            _remove_rows(session, removed_ids)
            session.commit()
            # Prune the HTML cache and the master URL list so a re-parse of the
            # cache cannot bring the stale rows back.
            if cache is not None:
                for u in removed_urls:
                    cache.delete(u)
            if cache_dir is not None:
                vp = Path(cache_dir) / "vod_urls.json"
                if vp.exists():
                    urls = json.loads(vp.read_text(encoding="utf-8"))
                    pruned = [u for u in urls if u not in set(removed_urls)]
                    if len(pruned) != len(urls):
                        vp.write_text(json.dumps(pruned, indent=2, ensure_ascii=False), encoding="utf-8")
            summary["applied"] = True
        else:
            summary["applied"] = False
        return summary
    finally:
        session.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Perform the cleanup (default: dry run)")
    args = ap.parse_args()

    from csfd_vod.config import load_config_from_env
    from csfd_vod.loading.postgres_loader import PostgresLoader
    from csfd_vod.cache import HTMLCache

    config = load_config_from_env()
    loader = PostgresLoader(config.database.connection_string)
    cache = HTMLCache(config.cache_dir)
    try:
        res = dedupe(loader, cache=cache, cache_dir=config.cache_dir, apply=args.apply)
    finally:
        loader.close()

    mode = "APPLIED" if res["applied"] else "DRY RUN (no changes) — pass --apply to execute"
    print(f"=== dedupe_titles: {mode} ===")
    print(f"  slug-drift duplicates : {res['dup_slug_drift']}")
    print(f"  non-overview junk rows: {res['non_overview']}")
    print(f"  total rows removed    : {res['total_removed']}")
    if res["sample"]:
        print("  sample of removed url_ids:")
        for u in res["sample"]:
            print(f"    - {u}")


if __name__ == "__main__":
    main()
