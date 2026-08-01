"""Guards for TMDB match acceptance.

Both rules here exist because a real title was matched wrongly or missed entirely.
They are pure functions on a search result, so they need no network and no database.
"""
import pytest

from csfd_vod.enrichment.tmdb_enricher import _fold, _names_match, _YEAR_TOLERANCE


class TestFold:
    def test_strips_diacritics_case_and_punctuation(self):
        assert _fold("S čerty nejsou žerty!") == _fold("s certy nejsou zerty")

    def test_keeps_digits(self):
        assert _fold("Se7en (1995)") == "se7en1995"


class TestNamesMatch:
    """The year window alone accepts wrong works — these are the cases it let through."""

    def test_rejects_a_popular_show_that_merely_contains_the_query(self):
        # The real failure: Czech series "MOST!" (2019) matched "FBI: Most Wanted"
        # (2020), which sits inside the ±2 year window.
        assert not _names_match("MOST!", {"name": "FBI: Most Wanted"})

    def test_accepts_the_original_title_under_a_translated_name(self):
        # ČSFD holds the Czech name, TMDB answers with the international one — the
        # match is on original_title, which is why every field is compared.
        assert _names_match(
            "Spalovač mrtvol", {"title": "The Cremator", "original_title": "Spalovač mrtvol"}
        )

    def test_accepts_a_query_that_is_itself_the_international_title(self):
        assert _names_match("The Witcher", {"name": "Zaklínač", "original_name": "The Witcher"})

    def test_rejects_when_no_field_resembles_the_query(self):
        # Mrazík's TMDB entry is Russian-titled; neither name resembles the query, so
        # this one is honestly a miss rather than a lucky guess.
        assert not _names_match("Mrazík", {"title": "Father Frost", "original_title": "Морозко"})

    @pytest.mark.parametrize(
        "query,name",
        [
            ("Silo", "Silo"),
            ("Ulice", "Ulice"),
            ("Ano, šéfe!", "Ano, šéfe!"),
            ("Ordinace v růžové zahradě", "Ordinace v růžové zahradě 2"),  # sequel number
        ],
    )
    def test_accepts_equal_or_near_equal_names(self, query, name):
        assert _names_match(query, {"name": name})

    def test_exact_mode_ignores_the_containment_allowance(self):
        pair = {"name": "Ordinace v růžové zahradě 2"}
        assert _names_match("Ordinace v růžové zahradě", pair)
        assert not _names_match("Ordinace v růžové zahradě", pair, exact=True)

    def test_a_spin_off_is_not_the_show_it_spun_off_from(self):
        """The length ratio does double duty: "Zaklínač" must not take the artwork of
        "Zaklínač: Rod krve", which is a different show, not a spelling variant."""
        assert not _names_match("Zaklínač", {"name": "Zaklínač: Rod krve"})

    def test_an_empty_query_never_matches(self):
        assert not _names_match("", {"name": "Cokoliv"})


def test_year_tolerance_covers_the_domestic_vs_international_gap():
    """ČSFD dates by domestic premiere, TMDB by international release, and the two
    disagree by a year as a rule: Spalovač mrtvol 1968/1969, Postřižiny 1980/1981,
    S čerty nejsou žerty 1984/1985. Passing the year to TMDB as a filter found none
    of them — that was the bulk of the 'permanently unmatchable' films."""
    assert _YEAR_TOLERANCE >= 1
