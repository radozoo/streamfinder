"""Which service a title says you can watch it on.

A work and its episodes are two separate rows on ČSFD /vod, and neither is reliably
the complete one. The exporter used to pick one and throw the other away, which is
how an episode of Klara — announced on /vod as an HBO Max release — ended up offering
a "Sledovat na Lepší.TV" button, because Lepší.TV is what the serial's own page lists.
1,181 episodes were shown a platform they are not on, and 443 serials hid one their
own episodes carry.

These pin the rule that replaced it: merge, never discard, and let the priority order
decide what leads. Every case here is one where dropping a side loses a true answer.
"""

from csfd_vod.export.streamfinder_exporter import (
    _child_platforms,
    _child_vods,
    _merge_vods,
    _root_platforms,
    _root_vods,
    _sort_platforms,
)

SERIAL = {"title_id": 10, "csfd_id": 100, "root_id": 100}
EPISODE = {"title_id": 11, "csfd_id": 111, "root_id": 100}
TITLES = [SERIAL, EPISODE]


def vods(*pairs):
    return [{"platform": p, "url": u} for p, u in pairs]


# --- the ordering the merge relies on ----------------------------------------

def test_a_real_service_leads_an_iptv_reseller():
    """The whole fix rests on this: merging is only safe if the primary sorts first."""
    assert _sort_platforms(["Lepší.TV", "HBO Max"])[0] == "HBO Max"


def test_an_unknown_platform_sorts_last_rather_than_first():
    assert _sort_platforms(["Netflix", "Some New Thing"]) == ["Netflix", "Some New Thing"]


def test_duplicates_collapse():
    assert _sort_platforms(["Netflix", "Netflix"]) == ["Netflix"]


# --- what each side contributes ----------------------------------------------

def test_the_serial_offers_its_platforms_to_its_episodes():
    m = {10: vods(("Lepší.TV", "u"))}
    assert _root_platforms(TITLES, m) == {100: ["Lepší.TV"]}


def test_the_episodes_offer_theirs_to_the_serial():
    m = {11: vods(("HBO Max", None))}
    assert _child_platforms(TITLES, m) == {100: ["HBO Max"]}


def test_a_serial_does_not_offer_itself_as_its_own_child():
    """root_id == csfd_id marks the top-level row; counting it as a child would make
    the merge a no-op that looks like it works."""
    assert _child_platforms([SERIAL], {10: vods(("Netflix", None))}) == {}


# --- the merge itself ---------------------------------------------------------

def test_the_episodes_own_platform_is_not_discarded():
    """The reported bug, in one line: Klara S02E01 is on HBO Max, its serial row says
    Lepší.TV, and the button offered Lepší.TV."""
    own, inherited = vods(("HBO Max", None)), vods(("Lepší.TV", "serial-url"))
    merged = _merge_vods(own, inherited)
    assert [v["platform"] for v in merged] == ["HBO Max", "Lepší.TV"]


def test_the_serials_platform_is_not_discarded_either():
    """The mirror case the old rule got right and which must keep working: an episode
    whose own /vod row is only a reseller still shows the show's real service."""
    merged = _merge_vods(vods(("Telly", None)), vods(("Netflix", "u")))
    assert sorted(v["platform"] for v in merged) == ["Netflix", "Telly"]


def test_the_episodes_own_link_wins_over_the_serials():
    """Both name Netflix; the episode's link points at the episode."""
    merged = _merge_vods(vods(("Netflix", "episode-url")), vods(("Netflix", "serial-url")))
    assert merged == [{"platform": "Netflix", "url": "episode-url"}]


def test_a_platform_is_never_listed_twice():
    merged = _merge_vods(vods(("Netflix", "a")), vods(("Netflix", "b"), ("Max", "c")))
    assert [v["platform"] for v in merged] == ["Netflix", "Max"]


def test_merging_nothing_changes_nothing():
    own = vods(("Netflix", "a"))
    assert _merge_vods(own, []) == own
    assert _merge_vods([], own) == own


# --- the serial's own page has to agree with its card -------------------------

def test_the_serial_page_offers_what_its_card_advertises():
    """The card merges its episodes' platforms in; without the same merge here, the
    card would say HBO Max and the page it opens would offer only the reseller."""
    m = {10: vods(("Lepší.TV", "u")), 11: vods(("HBO Max", None))}
    card = _sort_platforms([v["platform"] for v in m[10]] + _child_platforms(TITLES, m)[100])
    page = _merge_vods(m[10], _child_vods(TITLES, m)[100])
    assert card[0] == "HBO Max"
    assert _sort_platforms([v["platform"] for v in page])[0] == card[0]


def test_child_vods_keeps_each_platform_once_across_many_episodes():
    ep2 = {"title_id": 12, "csfd_id": 112, "root_id": 100}
    m = {11: vods(("HBO Max", "a")), 12: vods(("HBO Max", "b"), ("Netflix", "c"))}
    got = _child_vods([SERIAL, EPISODE, ep2], m)
    assert [v["platform"] for v in got[100]] == ["HBO Max", "Netflix"]
