"""Which names ship to the frontend's search index.

ČSFD lists a title under every country it was released in and leads with the
country-of-origin name, so `title_en` is "Ojingeo geim" while the "Squid Game" a
user types is three <li>s further down. The exporter carries the rest of the list —
but only the names that add something, because `titles_index.json` is already 33 MB
and the same string repeats under five flags.
"""

from csfd_vod.export.streamfinder_exporter import _search_names


def title(**over):
    return {"title": "Hra na oliheň", "title_en": "Ojingeo geim", **over}


def test_keeps_the_names_search_cannot_already_reach():
    t = title(alt_titles=["Ojingeo geim", "오징어 게임", "Squid Game"])
    # title_en is matched on its own, so its repeat in the array is dropped.
    assert _search_names(t) == ["오징어 게임", "Squid Game"]


def test_drops_names_that_only_differ_by_diacritics_or_case():
    # "Cesta do fantázie" (Slovak) folds to the Czech title the card already shows.
    t = {
        "title": "Cesta do fantazie",
        "title_en": "Sen to Čihiro no kamikakuši",
        "alt_titles": ["Sen to Čihiro no kamikakuši", "Cesta do fantázie", "Spirited Away"],
    }
    assert _search_names(t) == ["Spirited Away"]


def test_collapses_the_same_name_repeated_under_many_flags():
    t = title(alt_titles=["Ojingeo geim", "Squid Game", "SQUID GAME", "Squid Game"])
    assert _search_names(t) == ["Squid Game"]


def test_no_names_when_the_page_listed_none():
    # Season/episode pages have no .film-names block at all.
    assert _search_names({"title": "Hra na oliheň- Série 3", "title_en": None}) == []
    assert _search_names(title(alt_titles=None)) == []
