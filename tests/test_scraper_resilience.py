"""What the scraper does when ČSFD challenges it, and when there is no network.

Both behaviours cost a whole day of catalog on 2026-09-01, in opposite ways:

  * the Anubis interstitial was treated as a dead page after a five-second wait, so
    every challenged title paid two or three full browser launches to meet the same
    wall — 2.09 navigations per title at 21s each, against 1.00 at 3.5s on a healthy
    day, and the run was killed at 146 of 200 titles;
  * a DNS failure was retried like a slow site, so a laptop that woke with no network
    ground three months of listing pages for 2h16m and reported them all as
    fetch_failed — one single attempt took 17 minutes.
"""

import socket

import pytest
import requests

from csfd_vod.extraction.rate_limiter import RateLimiter
from csfd_vod.extraction.scraper import NetworkUnavailable, VODScraper


SELECTORS = {
    "title_page": {"title_selector": ".film-header h1"},
    "vod_page": {"title_link_selector": ".article-content a"},
}

# The real interstitial, trimmed: what identifies it is the path every one of its
# assets is served from.
CHALLENGE_HTML = (
    "<html><head><title>Making sure you're not a bot!</title>"
    '<link rel="stylesheet" href="/.within.website/x/cmd/anubis/static/css/custom.css">'
    '</head><body><div id="anubis-main">Proof-of-Work</div></body></html>'
)
TITLE_HTML = '<html><body><div class="film-header"><h1>Hra na oliheň</h1></div></body></html>'


def make_scraper():
    return VODScraper(SELECTORS, RateLimiter(delay_ms=0, jitter_ms=0), ["UA"])


# The real wait error when Anubis has fired and Playwright is mid-redirect. Taken
# verbatim from logs/refresh/2026-09-01T*.log — this is the shape the first version of
# the challenge detection missed, because page.content() at that moment is either the
# old document or an exception, and only the error message names the challenge.
MID_REDIRECT_ERROR = (
    "Page.wait_for_selector: Timeout 5000ms exceeded.\nCall log:\n"
    "  - waiting for locator(\"a[href*='/film/']\") to be visible\n"
    '    - waiting for" https://www.csfd.cz/.within.website/x/cmd/anubis/api/pass-challenge'
    "?id=01a05cf0-6f54-7316-882c-3c1f75a5ba14&response=000007ef&nonce=5337888&red…\" "
    "navigation to finish...\n"
)


class FakePage:
    """A Playwright page that misses the selector until it is waited on long enough."""

    def __init__(self, content, clears_after_ms=None, url="https://www.csfd.cz/x/", error=None):
        self._content = content
        self._clears_after_ms = clears_after_ms
        self.url = url
        self._error = error
        self.waits = []

    def content(self):
        if self._content is None:
            raise RuntimeError("Execution context was destroyed, most likely because of a navigation")
        return self._content

    def wait_for_selector(self, selector, timeout):
        self.waits.append(timeout)
        if self._clears_after_ms is not None and timeout >= self._clears_after_ms:
            return object()
        raise TimeoutError(self._error or f"Timeout {timeout}ms exceeded waiting for {selector}")


# ── the bot check is a wait, not a failure ────────────────────────────────────

def test_a_challenge_page_is_waited_out_instead_of_thrown_away():
    page = FakePage(CHALLENGE_HTML, clears_after_ms=VODScraper._CHALLENGE_TIMEOUT_MS)
    assert make_scraper()._await_selector_through_challenge(page, ".film-header h1", "u")
    # Short wait first (the ordinary page pays nothing), then the long one.
    assert page.waits == [5000, VODScraper._CHALLENGE_TIMEOUT_MS]


def test_a_page_that_is_not_the_challenge_still_fails_on_the_short_wait():
    # A 404 or a truncated response must not buy 20 extra seconds.
    page = FakePage("<html><body>nothing here</body></html>")
    assert not make_scraper()._await_selector_through_challenge(page, ".film-header h1", "u")
    assert page.waits == [5000]


def test_a_challenge_that_never_clears_is_a_failure():
    page = FakePage(CHALLENGE_HTML)  # never clears
    assert not make_scraper()._await_selector_through_challenge(page, ".film-header h1", "u")
    assert page.waits == [5000, VODScraper._CHALLENGE_TIMEOUT_MS]


def test_the_challenge_is_recognised_by_its_asset_path():
    assert VODScraper._is_challenge_page(CHALLENGE_HTML)
    assert not VODScraper._is_challenge_page(TITLE_HTML)
    assert not VODScraper._is_challenge_page(None)


# ── the plain-HTTP fallback gives up once it is challenged ────────────────────

def test_plain_http_is_abandoned_for_the_rest_of_the_run_once_challenged():
    s = make_scraper()
    assert s._plain_http_worth_trying()
    s._note_plain_http_challenged()
    assert not s._plain_http_worth_trying()


def test_a_challenged_title_stops_asking_plain_http_and_goes_back_to_the_browser(monkeypatch):
    """The fallback has no JS, so it cannot pass a proof-of-work — ever. Asking it
    again costs a round trip to be told so: 157 times for 146 titles on 2026-09-01."""
    s = make_scraper()
    monkeypatch.setattr(VODScraper, "_scrape_title_details_playwright", lambda self, url: None)

    plain_calls = []

    class Response:
        status_code = 200
        text = CHALLENGE_HTML

        def raise_for_status(self):
            pass

    def fake_get(url, **kwargs):
        plain_calls.append(url)
        return Response()

    monkeypatch.setattr(s.session, "get", fake_get)
    monkeypatch.setattr("csfd_vod.extraction.scraper.PLAYWRIGHT_AVAILABLE", True)

    assert s.scrape_title_details("https://www.csfd.cz/film/1-x/prehled/") is None
    # Three attempts, but plain HTTP is only asked once — the first rejection is enough.
    assert len(plain_calls) == 1


# ── no network is not a slow site ────────────────────────────────────────────

@pytest.mark.parametrize(
    "error_text",
    [
        "Page.goto: net::ERR_INTERNET_DISCONNECTED at https://www.csfd.cz/vod/",
        "net::ERR_NAME_NOT_RESOLVED",
        'HTTPSConnectionPool(host=\'www.csfd.cz\', port=443): Max retries exceeded '
        '(Caused by NameResolutionError("Failed to resolve \'www.csfd.cz\'"))',
    ],
)
def test_an_offline_error_aborts_instead_of_retrying(monkeypatch, error_text):
    s = make_scraper()
    monkeypatch.setattr(s, "_PROBE_ATTEMPTS", 2)
    monkeypatch.setattr(s, "_PROBE_PAUSE_SECONDS", 0)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(socket.gaierror(8, "nodename nor servname provided")))
    with pytest.raises(NetworkUnavailable):
        s._abort_if_offline(error_text)


def test_a_single_dns_blip_does_not_abort_a_healthy_run(monkeypatch):
    """A Wi-Fi handover produces one resolution failure. Aborting the day on that
    would be its own bug, so the verdict comes from a probe, not from the message."""
    s = make_scraper()
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [("ok",)])
    s._abort_if_offline("net::ERR_NAME_NOT_RESOLVED")  # returns, does not raise


@pytest.mark.parametrize(
    "error_text",
    [
        "Page.goto: Timeout 30000ms exceeded",
        "net::ERR_CONNECTION_RESET",
        "HTTPSConnectionPool: Read timed out",
        "429 Too Many Requests",
    ],
)
def test_a_site_that_is_merely_slow_or_hostile_keeps_its_retries(monkeypatch, error_text):
    s = make_scraper()

    def explode(*a, **k):
        raise AssertionError("must not probe DNS for an error that is not offline")

    monkeypatch.setattr(socket, "getaddrinfo", explode)
    s._abort_if_offline(error_text)


def test_a_listing_page_fetch_that_is_offline_aborts_the_harvest(monkeypatch):
    s = make_scraper()
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(socket.gaierror(8, "no")))
    monkeypatch.setattr(s, "_PROBE_ATTEMPTS", 1)

    def offline_get(*a, **k):
        raise requests.ConnectionError(
            'NameResolutionError("Failed to resolve \'www.csfd.cz\'")'
        )

    monkeypatch.setattr(s.session, "get", offline_get)
    with pytest.raises(NetworkUnavailable):
        s._scrape_vod_list_requests("https://www.csfd.cz/vod/?year=2026&month=9&page=1")


# ── the challenge shows in three different places ─────────────────────────────

def test_a_challenge_already_redirecting_is_recognised_from_the_wait_error():
    """The case live traffic found minutes after the first version shipped: the
    interstitial has fired, Playwright is navigating to pass-challenge, and the page's
    content is gone. Only the wait's own message names the challenge."""
    page = FakePage(
        None,  # content() raises — the execution context is being torn down
        clears_after_ms=VODScraper._CHALLENGE_TIMEOUT_MS,
        error=MID_REDIRECT_ERROR,
    )
    assert make_scraper()._await_selector_through_challenge(page, ".film-header h1", "u")
    assert page.waits == [5000, VODScraper._CHALLENGE_TIMEOUT_MS]


def test_a_challenge_is_recognised_from_the_landed_url():
    page = FakePage(
        "<html>something else entirely</html>",
        clears_after_ms=VODScraper._CHALLENGE_TIMEOUT_MS,
        url="https://www.csfd.cz/.within.website/x/cmd/anubis/api/pass-challenge?id=1",
    )
    assert make_scraper()._await_selector_through_challenge(page, ".film-header h1", "u")


def test_a_torn_down_page_with_no_challenge_anywhere_is_still_a_failure():
    page = FakePage(None, url="https://www.csfd.cz/film/1-x/prehled/")
    assert not make_scraper()._await_selector_through_challenge(page, ".film-header h1", "u")
    assert page.waits == [5000]
