"""What the site is allowed to claim about its own freshness.

Every failure here is the same shape: the footer states a time, a visitor believes
it, and it is not true. A missing or unreadable marker must therefore read as "we
do not know" — never as a plausible date, and never as one of the other timestamps
lying around that mean something else entirely.
"""

import json
import re

from csfd_vod.refresh_state import read_refresh, write_refresh


def test_a_written_stamp_reads_back(tmp_path):
    written = write_refresh(tmp_path)
    assert read_refresh(tmp_path) == written


def test_the_stamp_is_utc_to_the_second(tmp_path):
    """It is rendered in Europe/Prague by the site, so an ambiguous stamp shifts the hour."""
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", write_refresh(tmp_path))


def test_an_explicit_time_is_kept(tmp_path):
    assert write_refresh(tmp_path, 1786093150) == "2026-08-07T08:59:10Z"


def test_no_marker_reads_as_unknown_not_as_now(tmp_path):
    """The footer hides the line entirely rather than inventing a date."""
    assert read_refresh(tmp_path) is None


def test_a_corrupt_marker_reads_as_unknown(tmp_path):
    (tmp_path / "refresh_state.json").write_text("{not json", encoding="utf-8")
    assert read_refresh(tmp_path) is None


def test_a_marker_of_the_wrong_shape_reads_as_unknown(tmp_path):
    (tmp_path / "refresh_state.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert read_refresh(tmp_path) is None


def test_a_non_string_stamp_reads_as_unknown(tmp_path):
    """A number here would reach `new Date(...)` in the browser as a different bug."""
    (tmp_path / "refresh_state.json").write_text(
        json.dumps({"last_refresh_at": 1786093150}), encoding="utf-8")
    assert read_refresh(tmp_path) is None


def test_a_later_refresh_replaces_an_earlier_one(tmp_path):
    write_refresh(tmp_path, 1786093150)
    write_refresh(tmp_path, 1786179550)
    assert read_refresh(tmp_path) == "2026-08-08T08:59:10Z"


def test_the_marker_is_created_even_if_the_cache_dir_is_not_there_yet(tmp_path):
    nested = tmp_path / "cache"
    write_refresh(nested)
    assert (nested / "refresh_state.json").exists()
