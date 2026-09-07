"""Every day a title was released, not just the one that happened to win.

ČSFD lists a running serial's root again each week a new episode drops, and lists a
film again when it reaches a second platform. `fact_titles.vod_date` holds one date,
picked by merge_list_metadata's first-wins scan over listing files sorted by name —
and because ČSFD orders a month's pages newest-date-first, the winner was the NEWEST
date in the OLDEST month. Vigil's 2026 return lost to a 2023 listing, Colisión's
premiere lost to its own last episode, and the Kalendár was short 3,977 (day, title)
releases across 258 of the last 365 days.

These pin the two halves of the fix: the rows the listings turn into, and the rule
deciding when the export has to carry them separately from `vod_date`.
"""

from csfd_vod.export.streamfinder_exporter import _differs
from csfd_vod.loading.postgres_loader import event_rows
from csfd_vod.transformation.ids import csfd_id, root_id, segment_ids


def page(*entries):
    return {"2026_09_p01.html": list(entries)}


def entry(url, date, platforms=None, **kw):
    return {"film_url": url, "vod_date": date, "platforms": platforms, **kw}


EPISODE = "https://www.csfd.cz/film/1153107-the-walking-dead-dead-city/1881746-hourglass/prehled/"
ROOT = "https://www.csfd.cz/film/1896692-kolizia/prehled/"
SLUGLESS = "https://www.csfd.cz/film/17338/prehled/"


class TestIdentity:
    """A URL identifies an entity by its LAST /{id}-slug/ segment, not its first."""

    def test_an_episode_is_not_its_serial(self):
        assert csfd_id(EPISODE) == 1881746
        assert root_id(EPISODE) == 1153107

    def test_a_top_level_work_is_its_own_root(self):
        assert csfd_id(ROOT) == root_id(ROOT) == 1896692

    def test_the_slug_is_optional(self):
        # The film "$" slugifies to nothing. Requiring "-slug" left it with no ids.
        assert segment_ids(SLUGLESS) == [17338]

    def test_nothing_identifiable_is_none_not_a_crash(self):
        assert csfd_id("") is None
        assert csfd_id("https://www.csfd.cz/vod/") is None


class TestEventRows:
    def test_each_date_of_a_weekly_serial_becomes_its_own_row(self):
        rows, _ = event_rows({
            "2026_09_p01.html": [entry(ROOT, "2026-09-28", ["HBO Max"])],
            "2026_09_p06.html": [entry(ROOT, "2026-09-07", ["HBO Max"])],
        })
        assert sorted(r["vod_date"] for r in rows) == ["2026-09-07", "2026-09-28"]

    def test_the_same_release_listed_on_two_pages_is_one_row(self):
        rows, _ = event_rows({
            "a.html": [entry(ROOT, "2026-09-07", ["HBO Max"])],
            "b.html": [entry(ROOT, "2026-09-07", ["HBO Max"])],
        })
        assert len(rows) == 1

    def test_two_platforms_on_one_day_are_two_rows(self):
        rows, _ = event_rows(page(entry(ROOT, "2026-09-07", ["Netflix", "Prime Video"])))
        assert {r["platform"] for r in rows} == {"Netflix", "Prime Video"}

    def test_a_release_with_no_platform_still_gets_its_date(self):
        # The date is what the calendar needs. The platform is the detail, and '' not
        # NULL because Postgres treats NULLs as distinct in the unique index.
        rows, _ = event_rows(page(entry(ROOT, "2026-09-07", None)))
        assert [r["platform"] for r in rows] == [""]

    def test_undated_catalog_entries_are_skipped_not_dropped_silently(self):
        # ~31k of 68k entries: a platform's browse listing names titles with no dated
        # arrival at all. Counted, so a real parsing failure cannot hide among them.
        rows, skipped = event_rows(page(entry(ROOT, None), entry(EPISODE, "2026-09-06")))
        assert len(rows) == 1 and skipped == 1

    def test_distributor_and_type_ride_along(self):
        rows, _ = event_rows(page(
            entry(ROOT, "2026-09-07", ["HBO Max"], distributor="HBO Max", list_type="seriál")))
        assert rows[0]["distributor"] == "HBO Max" and rows[0]["list_type"] == "seriál"


class TestExportCondition:
    """When the index has to carry vod_events beside vod_date."""

    def test_a_single_release_matching_vod_date_says_nothing_new(self):
        # ~46k titles. Carrying it would be pure payload for no information.
        assert not _differs([["2026-09-07", "HBO Max"]], "2026-09-07")

    def test_more_dates_than_vod_date_can_hold(self):
        assert _differs([["2026-09-07", "HBO Max"], ["2026-09-14", "HBO Max"]], "2026-09-07")

    def test_a_release_whose_row_has_no_vod_date(self):
        # Four titles ship exactly like this. A "more than one event" test would keep
        # leaving them off the calendar entirely, as it always had.
        assert _differs([["2025-11-15", "Netflix"]], None)

    def test_no_events_at_all(self):
        assert not _differs([], "2026-09-07")
        assert not _differs([], None)
