"""VOD scraper with rate limiting and retry logic."""

import re
import random
import socket
import time
from datetime import date
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from csfd_vod.extraction.rate_limiter import RateLimiter
from csfd_vod.logger import get_logger

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logger = get_logger(__name__)


class NetworkUnavailable(RuntimeError):
    """csfd.cz cannot be reached at all — no DNS, no route, no interface.

    Raised instead of retrying, because a host that cannot even be resolved will not
    resolve on the second attempt either, and the retry ladders here are built for a
    site that answers slowly, not for one that is not there. On 2026-09-01 the 08:00
    refresh woke a sleeping laptop with no network and spent 2h16m grinding three
    months of listing pages through DNS failures — a single attempt took 17 minutes —
    then reported every month as fetch_failed. By the time the lid was opened and the
    network came back, the run's budget was gone and the day was lost. Failing in
    seconds leaves the whole day for the next attempt.
    """


class VODScraper:
    """Scrape VOD titles from csfd.cz with rate limiting and error handling."""

    def __init__(self, selectors: Dict[str, Any], rate_limiter: RateLimiter, user_agents: List[str]):
        """
        Initialize scraper.

        Args:
            selectors: CSS selectors for field extraction
            rate_limiter: RateLimiter instance for request pacing
            user_agents: List of User-Agent strings to rotate
        """
        self.selectors = selectors
        self.rate_limiter = rate_limiter
        self.user_agents = user_agents or [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        ]
        self.session = self._create_session()
        # Set the first time the plain-HTTP path is answered with the bot-check, and
        # never cleared: see _plain_http_worth_trying.
        self._plain_http_challenged = False

    # ── Bot check ─────────────────────────────────────────────────────────────
    #
    # ČSFD fronts the site with Anubis, which serves a ~7 KB interstitial that solves
    # a proof-of-work in the browser and only then redirects to the real page. Every
    # asset it references is under this path, so the marker is unmistakable and
    # survives a redesign of the page's wording.
    _CHALLENGE_MARKER = ".within.website/x/cmd/anubis"

    # How long to let that proof-of-work run. Measured: the challenge clears in a few
    # seconds, and the 5s selector wait below was simply shorter than that — on
    # 2026-09-01, 126 of 154 selector misses were a plain timeout with no navigation
    # pending, i.e. the challenge page sitting there computing while we walked away
    # from it. Twenty seconds is far past what it needs and still cheaper than the
    # browser launch the next attempt would pay.
    _CHALLENGE_TIMEOUT_MS = 20_000

    @classmethod
    def _is_challenge_page(cls, html: Optional[str]) -> bool:
        return bool(html) and cls._CHALLENGE_MARKER in html

    def _plain_http_worth_trying(self) -> bool:
        """Is the requests fallback still worth a round trip?

        Once ČSFD is challenging plain HTTP it challenges every plain request for the
        rest of the run — the fallback cannot pass a proof-of-work, having no JS. Each
        attempt then costs a rate-limiter wait and a request only to be rejected, and
        on 2026-09-01 that happened 157 times for 146 titles. Skipping it goes straight
        to the browser, which is the thing that can actually get the page.
        """
        return not self._plain_http_challenged

    def _note_plain_http_challenged(self) -> None:
        if not self._plain_http_challenged:
            logger.info("plain_http_challenged_skipping_fallback")
        self._plain_http_challenged = True

    # ── Network presence ──────────────────────────────────────────────────────
    #
    # Substrings of the errors a machine with no network produces: Playwright's
    # Chromium net errors and urllib3/requests' DNS failures. Deliberately narrow —
    # a connection RESET or a timeout is what a site under load or a bot check looks
    # like, and those must keep their retries.
    _OFFLINE_SIGNS = (
        "ERR_INTERNET_DISCONNECTED",
        "ERR_NAME_NOT_RESOLVED",
        "ERR_NETWORK_CHANGED",
        "NameResolutionError",
        "Failed to resolve",
        "Temporary failure in name resolution",
        "nodename nor servname provided",
    )

    _PROBE_HOST = "www.csfd.cz"
    _PROBE_ATTEMPTS = 3
    _PROBE_PAUSE_SECONDS = 15

    def _abort_if_offline(self, error_text: str) -> None:
        """Raise NetworkUnavailable when the error means "there is no network".

        Confirmed with a DNS probe rather than taken on the error's word: a Wi-Fi
        handover or a laptop waking up produces one resolution failure and is fine a
        moment later, and aborting a healthy run on that would be its own bug. Three
        probes over ~30s is the whole cost of being sure.
        """
        if not any(sign in error_text for sign in self._OFFLINE_SIGNS):
            return
        for attempt in range(self._PROBE_ATTEMPTS):
            try:
                socket.getaddrinfo(self._PROBE_HOST, 443)
                logger.info("network_probe_recovered", attempt=attempt + 1)
                return
            except OSError as probe_error:
                logger.warning(
                    "network_probe_failed",
                    attempt=attempt + 1, host=self._PROBE_HOST, error=str(probe_error),
                )
                if attempt < self._PROBE_ATTEMPTS - 1:
                    time.sleep(self._PROBE_PAUSE_SECONDS)
        raise NetworkUnavailable(
            f"{self._PROBE_HOST} does not resolve after {self._PROBE_ATTEMPTS} probes "
            f"— the machine has no network, not a slow site"
        )

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy."""
        session = requests.Session()

        # Configure retry strategy for transient failures
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def _get_random_user_agent(self) -> str:
        """Get a random User-Agent string."""
        return random.choice(self.user_agents)

    def scrape_vod_list(self, vod_page_url: str) -> List[str]:
        """
        Scrape list of VOD title URLs from the main VOD page.
        Uses Playwright for JavaScript-heavy pages with bot protection.

        Args:
            vod_page_url: URL of the VOD listing page

        Returns:
            List of title page URLs
        """
        logger.info("scrape_vod_list_start", url=vod_page_url, method="playwright")

        # Try with Playwright first (handles JS and bot protection)
        if PLAYWRIGHT_AVAILABLE:
            try:
                urls, _ = self._scrape_vod_list_playwright(vod_page_url)
                return urls
            except Exception as e:
                logger.warning("playwright_failed", error=str(e), fallback_to_requests=True)

        # Fallback to requests
        urls, _ = self._scrape_vod_list_requests(vod_page_url)
        return urls

    # Matches film/series/season/episode overview URLs:
    #   /film/12345-slug/prehled/                     (film or serial)
    #   /film/12345/67890-slug/prehled/               (seria or epizoda — child URL)
    _TITLE_OVERVIEW_RE = re.compile(
        r'^https://www\.csfd\.cz/film/\d+[^/]*/(?:\d+[^/]*/)?prehled/$'
    )

    def _is_title_overview_url(self, url: str) -> bool:
        """Return True only for film/series overview pages, not episodes or reviews."""
        return bool(self._TITLE_OVERVIEW_RE.match(url))

    _PAGE_NUM_RE = re.compile(r"page=(\d+)")

    def _declared_last_page(self, html: str) -> int:
        """Largest page number the listing's paginator links to — i.e. its last page.

        CSFD's paginator always includes a jump to the final page (e.g. links to
        2,3,4,5,6,20 → last page is 20). This is our completeness signal: if the
        harvest of a month stops before this page, it silently truncated the month.
        Returns 1 when there is no pagination (single-page month).

        Parsed via BeautifulSoup so `&amp;page=20` in the raw HTML is read as a real
        query param — a raw-string regex would miss the HTML-encoded ampersand and
        under-report the last page, quietly defeating the completeness guard.
        """
        soup = BeautifulSoup(html, "html.parser")
        pages = [
            int(m.group(1))
            for a in soup.select("a[href*='page=']")
            if (m := self._PAGE_NUM_RE.search(a.get("href", "")))
        ]
        return max(pages) if pages else 1

    def _extract_title_urls(self, html: str) -> List[str]:
        """Absolute /film/ URLs from a listing page's HTML (same selector as fetch)."""
        selector = self.selectors.get("vod_page", {}).get("title_link_selector", "a[href*='/film/']")
        soup = BeautifulSoup(html, "html.parser")
        out: List[str] = []
        for a in soup.select(selector):
            href = a.get("href")
            if not href:
                continue
            out.append(href if href.startswith("http") else f"https://www.csfd.cz{href}")
        return out

    def scrape_vod_month_page(self, year: int, month: int, page: int = 1) -> Tuple[List[str], str]:
        """
        Scrape film URLs from a single month-page of the VOD listing.

        Args:
            year: Calendar year (e.g. 2023)
            month: Calendar month 1-12
            page: Pagination index (1-based)

        Returns:
            Tuple of (film_urls, raw_html).
        """
        url = f"https://www.csfd.cz/vod/?year={year}&month={month}&range=month&page={page}"
        self.rate_limiter.wait()
        logger.info("scrape_month_page_start", year=year, month=month, page=page)

        if PLAYWRIGHT_AVAILABLE:
            try:
                urls, html = self._scrape_vod_list_playwright(url)
                logger.info("scrape_month_page_complete", year=year, month=month, page=page, count=len(urls))
                return urls, html
            except Exception as e:
                self._abort_if_offline(str(e))
                logger.warning("playwright_month_page_failed", year=year, month=month, page=page, error=str(e))

        urls, html = self._scrape_vod_list_requests(url)
        logger.info("scrape_month_page_complete", year=year, month=month, page=page, count=len(urls), method="requests")
        return urls, html

    # Slug for each platform's static browse listing at /vod/{slug}/ — a
    # complementary source to the dated monthly feed (see scrape_vod_all_urls'
    # docstring). This lists everything CURRENTLY on a platform regardless of
    # when it arrived, which recovers older catalog titles that never had a dated
    # VOD arrival (e.g. Dexter, Game of Thrones) and are therefore invisible to
    # the monthly harvest. Confirmed empirically to use the same real (non-phantom)
    # pagination as the monthly listing: /vod/netflix/?page=328 == ?page=327 ==
    # the paginator's own declared last page — i.e. CSFD clamps here too.
    MAJOR_VOD_PLATFORMS = [
        "netflix", "hbo-max", "disney-plus", "prime-video",
        "sky-showtime", "apple-tv", "oneplay", "prima-plus",
    ]

    # A real listing page is 185KB+; observed challenge/consent stubs (no listing,
    # just ab_detection/consent scripts) were 331 and 7207 bytes — a huge, stable
    # gap. 50KB sits in the middle with wide margin on both sides. Anything below
    # it is a failed fetch, never a legitimately empty/short page.
    _MIN_LISTING_PAGE_BYTES = 50_000

    def scrape_vod_platform_page(self, platform_slug: str, page: int = 1) -> Tuple[List[str], str]:
        """Scrape film URLs from a single page of a platform's /vod/{slug}/ listing."""
        url = f"https://www.csfd.cz/vod/{platform_slug}/?page={page}"
        self.rate_limiter.wait()
        logger.info("scrape_platform_page_start", platform=platform_slug, page=page)

        if PLAYWRIGHT_AVAILABLE:
            try:
                urls, html = self._scrape_vod_list_playwright(url)
                logger.info("scrape_platform_page_complete", platform=platform_slug, page=page, count=len(urls))
                return urls, html
            except Exception as e:
                self._abort_if_offline(str(e))
                logger.warning("playwright_platform_page_failed", platform=platform_slug, page=page, error=str(e))

        urls, html = self._scrape_vod_list_requests(url)
        logger.info("scrape_platform_page_complete", platform=platform_slug, page=page, count=len(urls), method="requests")
        return urls, html

    def scrape_vod_platform_all_urls(
        self, platform_slug: str, list_html_dir: Optional[Path] = None
    ) -> List[str]:
        """Collect all title URLs from one platform's /vod/{slug}/ browse listing.

        Same termination rule as scrape_vod_all_urls: the true end is a page whose
        items repeat the previous page (CSFD clamps out-of-range pages there too),
        never "no new URLs" alone. Populates self.incomplete_platforms with any
        platform that hit the safety cap or emptied out after real content — the
        same kind of guard as the monthly harvest's incomplete_months.
        """
        seen: set = set()
        if not hasattr(self, "incomplete_platforms"):
            self.incomplete_platforms: List[dict] = []

        if list_html_dir is not None:
            list_html_dir.mkdir(parents=True, exist_ok=True)

        page = 1
        prev_page_urls: set = set()
        last_nonempty = 0
        reason = None
        while True:
            page_path = (
                list_html_dir / f"platform_{platform_slug}_p{page:03d}.html"
                if list_html_dir is not None else None
            )
            if (
                page_path is not None and page_path.exists()
                and page_path.stat().st_size >= self._MIN_LISTING_PAGE_BYTES
            ):
                html = page_path.read_text(encoding="utf-8")
                urls = self._extract_title_urls(html)
            else:
                if page_path is not None and page_path.exists():
                    logger.warning("platform_page_cache_poisoned_refetching", path=str(page_path))
                # Retry a failed/challenge-stub fetch a few times before giving up —
                # a transient block should not be mistaken for the catalog's end.
                for attempt in range(3):
                    urls, html = self.scrape_vod_platform_page(platform_slug, page)
                    if len(html) >= self._MIN_LISTING_PAGE_BYTES:
                        break
                    logger.warning(
                        "platform_page_too_small_retry",
                        platform=platform_slug, page=page, attempt=attempt + 1, bytes=len(html),
                    )
                else:
                    reason = "fetch_failed"
                    logger.error("platform_page_fetch_failed", platform=platform_slug, page=page)
                    break
                if page_path is not None:
                    page_path.write_text(html, encoding="utf-8")
                    logger.info("platform_page_cached", path=str(page_path))

            overview_urls = [u for u in urls if self._is_title_overview_url(u)]
            page_url_set = set(overview_urls)
            if page_url_set == prev_page_urls and prev_page_urls:
                reason = "clamp"
                break
            if not page_url_set:
                reason = "empty"
                break
            last_nonempty = page
            seen.update(u for u in overview_urls if u not in seen)
            prev_page_urls = page_url_set
            page += 1
            if page > 1000:  # safety cap — largest observed platform (apple-tv) was ~553
                logger.warning("platform_harvest_page_cap_reached", platform=platform_slug)
                reason = "cap"
                break

        # Same invariant as the monthly harvest (scrape_vod_all_urls): CSFD CLAMPS
        # an out-of-range page rather than emptying it (verified empirically —
        # /vod/netflix/?page=328 == ?page=327, its own declared last page). So an
        # "empty" page reached AFTER real content (last_nonempty >= 1) is almost
        # always a FAILED FETCH (e.g. a tiny bot-protection challenge stub — one
        # such 334-byte stub silently truncated a prime-video run at page 188 of
        # a declared 192 before this was caught), not a genuine end — flag it.
        # Only "empty" at page 1 (last_nonempty == 0) is a legitimately empty
        # platform (not expected for the major platforms, but not impossible).
        # "fetch_failed" = a challenge stub survived 3 retries — never silently
        # treat that as the catalog's end either.
        suspect = reason in ("cap", "fetch_failed") or (reason == "empty" and last_nonempty >= 1)
        if suspect:
            logger.error(
                "harvest_platform_incomplete",
                platform=platform_slug, pages_fetched=last_nonempty, reason=reason,
            )
            self.incomplete_platforms.append({
                "platform": platform_slug, "pages_fetched": last_nonempty, "reason": reason,
            })

        logger.info(
            "harvest_platform_complete",
            platform=platform_slug, pages_fetched=last_nonempty, reason=reason, total_unique=len(seen),
        )
        return sorted(seen)

    def scrape_vod_all_urls(
        self,
        from_year: int = 2015,
        list_html_dir: Optional[Path] = None,
        from_month: int = 1,
        refetch_from: Optional[Tuple[int, int]] = None,
    ) -> List[str]:
        """
        Collect all VOD title URLs by iterating every month from from_year to today.

        Handles pagination within each month: keeps fetching page=N until a page
        returns no new URLs.  Deduplicates across all months.

        Args:
            from_year: First year to include (default 2015)
            list_html_dir: Optional directory to save raw list page HTML files.
                Files are named {year}_{month:02d}_p{page:02d}.html.
                Existing files are reused (resumable) unless `refetch_from` forces
                a fresh fetch for that month.
            from_month: First month of `from_year` to include (default 1). Lets the
                `update` discover step iterate only the last few months.
            refetch_from: Optional (year, month). Months at or after this point are
                re-fetched from the network even if a cached list page exists, and
                the cached page is overwritten. This is how discover picks up NEW
                releases (and new episodes of running series): the back-catalogue
                stays cached, only the recent window is refreshed. Months before it
                are still served from cache when present.

        Returns:
            Sorted list of unique film URLs.
        """
        seen: set = set()
        today = date.today()
        # Completeness report: months where we failed to reach CSFD's declared last
        # page. Empty after a healthy harvest; inspected by the caller as a guard.
        self.incomplete_months: List[dict] = []

        if list_html_dir is not None:
            list_html_dir.mkdir(parents=True, exist_ok=True)

        year, month = from_year, from_month
        while (year, month) <= (today.year, today.month):
            page = 1
            prev_page_urls: set = set()
            last_nonempty = 0     # highest page index we actually saw items on
            reason = None         # why pagination stopped: clamp | empty | cap
            while True:
                # Cache-aware: reuse an already-downloaded page, otherwise fetch it.
                # This makes a full re-harvest resumable and cheap — we only hit the
                # network for pages not yet on disk (e.g. the tail a buggy earlier
                # run never reached) instead of re-fetching thousands of good pages.
                page_path = (
                    list_html_dir / f"{year}_{month:02d}_p{page:02d}.html"
                    if list_html_dir is not None else None
                )
                # Force a fresh fetch for months in the refetch window, so discover
                # sees releases that appeared since the page was last cached.
                stale = refetch_from is not None and (year, month) >= refetch_from
                # Same stub guard the platform harvest above has had all along. It
                # was never wired into this path, and that asymmetry is what lost
                # 2026-08-30 two of its five titles: a 7,478-byte challenge page was
                # written here as if it were the month's listing, parsed to zero
                # entries, and the zero was cached in list_index as fact. A listing
                # page is the ONLY source of vod_date/distributor/platform for a
                # running serial's episode, so an empty one does not merely fail to
                # add — it erases what a good fetch had already established.
                cached_ok = (
                    page_path is not None and page_path.exists() and not stale
                    and page_path.stat().st_size >= self._MIN_LISTING_PAGE_BYTES
                )
                if cached_ok:
                    html = page_path.read_text(encoding="utf-8")
                    urls = self._extract_title_urls(html)
                else:
                    if page_path is not None and page_path.exists() and not stale:
                        logger.warning("list_page_cache_poisoned_refetching", path=str(page_path))
                    for attempt in range(3):
                        urls, html = self.scrape_vod_month_page(year, month, page)
                        if len(html) >= self._MIN_LISTING_PAGE_BYTES:
                            break
                        logger.warning(
                            "list_page_too_small_retry",
                            year=year, month=month, page=page,
                            attempt=attempt + 1, bytes=len(html),
                        )
                    else:
                        # Never cache the stub, and never let it read as "end of
                        # month" — that is how a truncated harvest looks healthy.
                        reason = "fetch_failed"
                        logger.error("list_page_fetch_failed", year=year, month=month, page=page)
                        break
                    if page_path is not None:
                        page_path.write_text(html, encoding="utf-8")
                        logger.info("list_page_cached", path=str(page_path))

                overview_urls = [u for u in urls if self._is_title_overview_url(u)]
                page_url_set = set(overview_urls)
                # Determine the real end of the month. CSFD CLAMPS an out-of-range
                # page to the last real page, so the reliable end-of-month signal is
                # a page whose items repeat the previous page — NOT the paginator's
                # "last page" number, which is a phantom (page 1 always links to a
                # far page like 20 even for a 5-page month). Do NOT stop merely on
                # "no new URLs": `seen` is global across months, so a mid-month page
                # of already-seen re-releases must not truncate the rest (the bug
                # that dropped ~12k episode URLs, e.g. every part of True Detective).
                if page_url_set == prev_page_urls and prev_page_urls:
                    reason = "clamp"   # reached the real last page
                    break
                if not page_url_set:
                    reason = "empty"   # no items — empty month, or a failed fetch
                    break
                last_nonempty = page
                seen.update(u for u in overview_urls if u not in seen)
                prev_page_urls = page_url_set
                page += 1
                if page > 500:  # safety cap against a non-terminating listing
                    logger.warning("harvest_page_cap_reached", year=year, month=month)
                    reason = "cap"
                    break

            # Completeness invariant, phrased around HOW the month ended:
            #  - "clamp": CSFD served the last page again → we reached the true end. ✓
            #  - "empty" at page 1: a month with no VOD releases. ✓
            #  - "empty" after real content: CSFD clamps rather than returning empty
            #    at the true end, so a mid-month empty page almost always means a
            #    FAILED FETCH — the month is truncated (the class of bug that lost
            #    Twin Peaks). ✗
            #  - "cap": runaway pagination. ✗
            #  - "fetch_failed": a challenge stub survived three attempts, so the
            #    month stops short of its real end through no fault of the listing. ✗
            suspect = reason in ("cap", "fetch_failed") or (reason == "empty" and last_nonempty >= 1)
            if suspect:
                logger.error(
                    "harvest_month_incomplete",
                    year=year, month=month, pages_fetched=last_nonempty, reason=reason,
                )
                self.incomplete_months.append({
                    "year": year, "month": month,
                    "pages_fetched": last_nonempty, "reason": reason,
                })

            logger.info(
                "harvest_month_complete",
                year=year, month=month,
                pages_fetched=last_nonempty, reason=reason, total_unique=len(seen),
            )

            # advance to next month
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1

        result = sorted(seen)
        if self.incomplete_months:
            logger.error("harvest_incomplete", incomplete_months=len(self.incomplete_months))
        logger.info(
            "harvest_all_complete",
            total_unique=len(result),
            incomplete_months=len(self.incomplete_months),
        )
        return result

    def _challenge_in_progress(self, page, wait_error: Exception) -> bool:
        """Is the reason the selector never appeared that Anubis is still working?

        Three places the answer can show, and all three are needed — the first version
        of this asked only the page's content and missed the commonest live case within
        minutes of shipping:

          * the interstitial is sitting there computing, so its markup is the content;
          * it has already fired and Playwright is mid-navigation to `pass-challenge`,
            in which case `page.content()` is either the old document or an error
            ("Execution context was destroyed") — but the wait's own message names the
            URL it is blocked on;
          * the page has landed on the challenge URL itself.
        """
        if self._CHALLENGE_MARKER in str(wait_error):
            return True
        try:
            if self._CHALLENGE_MARKER in (page.url or ""):
                return True
        except Exception:
            pass
        try:
            return self._is_challenge_page(page.content())
        except Exception:
            return False

    def _await_selector_through_challenge(
        self, page, selector: str, url: str, miss_event: str = "title_selector_not_found_in_page"
    ) -> bool:
        """Wait for `selector`, sitting through an Anubis challenge if that is what is
        on the page. True when the selector appeared.

        The plain five-second wait used to be the whole of this: a miss returned the
        page as a failure, the caller launched a fresh browser and met the same wall,
        and a challenged title cost two or three full navigations — 2.09 per title and
        21s each on 2026-09-01, against 1.00 and 3.5s on a healthy day. The challenge
        is not a failure though, it is a wait: the interstitial computes for a few
        seconds and then redirects itself to the page we asked for. So the short wait
        stays for the ordinary case, and a page that IS the challenge gets waited out.
        """
        try:
            page.wait_for_selector(selector, timeout=5000)
            return True
        except Exception as first_error:
            if not self._challenge_in_progress(page, first_error):
                logger.warning(miss_event, selector=selector, error=str(first_error), url=url)
                return False
            logger.info("anubis_challenge_waiting", url=url, timeout_ms=self._CHALLENGE_TIMEOUT_MS)
            try:
                page.wait_for_selector(selector, timeout=self._CHALLENGE_TIMEOUT_MS)
                logger.info("anubis_challenge_passed", url=url)
                return True
            except Exception as challenge_error:
                logger.warning(
                    "anubis_challenge_timeout",
                    url=url, timeout_ms=self._CHALLENGE_TIMEOUT_MS, error=str(challenge_error),
                )
                return False

    def _scrape_vod_list_playwright(self, vod_page_url: str) -> List[str]:
        """
        Scrape VOD list using Playwright browser automation.
        Handles JavaScript rendering and bot protection.
        """
        browser = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent=self._get_random_user_agent()
                )

                logger.info("playwright_navigate_start", url=vod_page_url)
                page.goto(vod_page_url, wait_until="networkidle", timeout=30000)

                # Wait for content to stabilize - wait for either the selector to appear
                # or timeout after waiting
                selector = self.selectors.get("vod_page", {}).get("title_link_selector")
                if not selector:
                    logger.error("selector_missing", selector_key="vod_page.title_link_selector")
                    if browser:
                        browser.close()
                    return []

                # Wait for at least one element matching the selector — through the
                # bot check if that is what came back. Unlike the title path this does
                # not bail on a miss: the caller judges the page by its size, and a
                # stub is rejected there.
                if self._await_selector_through_challenge(
                    page, selector, vod_page_url, miss_event="selector_not_found_in_page"
                ):
                    logger.info("playwright_selector_found", selector=selector)

                # Wait a bit more for dynamic loading
                time.sleep(2)

                # Get the rendered HTML
                try:
                    html_content = page.content()
                except Exception as e:
                    logger.warning("page_content_error", error=str(e))
                    # Try again after a moment
                    time.sleep(1)
                    html_content = page.content()

                soup = BeautifulSoup(html_content, "html.parser")

                title_links = soup.select(selector)
                title_urls = []

                for link in title_links:
                    href = link.get("href")
                    if href:
                        # Convert relative URLs to absolute
                        if href.startswith("http"):
                            title_urls.append(href)
                        else:
                            # Determine domain from vod_page_url
                            if "www.csfd.cz" in vod_page_url:
                                title_urls.append(f"https://www.csfd.cz{href}")
                            else:
                                title_urls.append(f"https://csfd.cz{href}")

                if browser:
                    browser.close()

                logger.info("scrape_vod_list_success", count=len(title_urls), method="playwright")
                return title_urls, html_content

        except Exception as e:
            if browser:
                try:
                    browser.close()
                except:
                    pass
            logger.error("playwright_scrape_failed", error=str(e), url=vod_page_url)
            raise

    def _scrape_title_details_playwright(self, title_url: str) -> Optional[str]:
        """
        Scrape film detail page using Playwright browser automation.
        Handles JavaScript rendering and bot protection for individual film pages.

        Args:
            title_url: URL of the film detail page

        Returns:
            Rendered HTML content as string, or None if scraping fails
        """
        browser = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent=self._get_random_user_agent()
                )

                logger.info("playwright_navigate_title_start", url=title_url)
                page.goto(title_url, wait_until="networkidle", timeout=30000)

                # Wait for mandatory title selector to appear (confirms page loaded correctly)
                selector = self.selectors.get("title_page", {}).get("title_selector")
                if not selector:
                    logger.error("selector_missing", selector_key="title_page.title_selector")
                    if browser:
                        browser.close()
                    return None

                # Wait for at least the title element, or timeout.
                #
                # A page without it is not a title page — it is a 404, a bot-check
                # interstitial or a truncated response. Returning it anyway meant the
                # caller cached an error page as a success, and `cache.has()` then
                # made the URL permanently un-retryable: 566 titles sat missing from
                # the catalog this way, every one of them under 10 KB while a real
                # page is 150 KB+. Treat it as a failed scrape so it is retried.
                if self._await_selector_through_challenge(page, selector, title_url):
                    logger.info("playwright_title_selector_found", selector=selector)
                else:
                    if browser:
                        browser.close()
                    return None

                # Wait a bit more for dynamic content to load
                time.sleep(2)

                # Get the rendered HTML
                try:
                    html_content = page.content()
                except Exception as e:
                    logger.warning("page_content_error_title", error=str(e))
                    # Try again after a moment
                    time.sleep(1)
                    html_content = page.content()

                if browser:
                    browser.close()

                logger.info("scrape_title_details_success", url=title_url, method="playwright", html_length=len(html_content))
                return html_content

        except Exception as e:
            if browser:
                try:
                    browser.close()
                except:
                    pass
            logger.error("playwright_title_scrape_failed", error=str(e), url=title_url)
            return None

    def _scrape_vod_list_requests(self, vod_page_url: str) -> List[str]:
        """
        Fallback method using requests library.
        Works for simple pages without JavaScript.
        """
        try:
            self.rate_limiter.wait()
            response = self.session.get(
                vod_page_url,
                headers={"User-Agent": self._get_random_user_agent()},
                timeout=10,
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            selector = self.selectors.get("vod_page", {}).get("title_link_selector")

            if not selector:
                logger.error("selector_missing", selector_key="vod_page.title_link_selector")
                return []

            title_links = soup.select(selector)
            title_urls = []

            for link in title_links:
                href = link.get("href")
                if href:
                    # Convert relative URLs to absolute
                    if href.startswith("http"):
                        title_urls.append(href)
                    else:
                        title_urls.append(f"https://csfd.cz{href}")

            logger.info("scrape_vod_list_success", count=len(title_urls), method="requests")
            return title_urls, response.text

        except requests.RequestException as e:
            self._abort_if_offline(str(e))
            logger.error("scrape_vod_list_failed", error=str(e), url=vod_page_url, method="requests")
            return [], ""

    # A real ČSFD title page carries the header element and is 150 KB+; the
    # bot-protection interstitial has neither. scripts/purge_failed_cache.py draws
    # the same line on the same marker, which is how the poisoned pages get found
    # after the fact — this is the same test applied before they are stored.
    _TITLE_PAGE_MARKER = "film-header"

    @classmethod
    def _is_title_page(cls, html: Optional[str]) -> bool:
        return bool(html) and cls._TITLE_PAGE_MARKER in html

    def scrape_title_details(self, title_url: str) -> Optional[str]:
        """
        Scrape HTML content for a single title page.
        Uses Playwright for JavaScript-heavy pages with bot protection.

        Args:
            title_url: URL of the title page

        Returns:
            Rendered HTML content as string, or None if all attempts fail
        """
        for attempt in range(3):
            try:
                # Try with Playwright first (handles JS and bot protection)
                if PLAYWRIGHT_AVAILABLE:
                    try:
                        self.rate_limiter.wait()
                        html_content = self._scrape_title_details_playwright(title_url)
                        # The Playwright path waits on `.film-header h1`, so it is
                        # already all but guaranteed; checked anyway so the guarantee
                        # lives in one place rather than in a selector two files away.
                        if self._is_title_page(html_content):
                            logger.info("scrape_title_details_success", url=title_url, method="playwright")
                            return html_content
                    except Exception as e:
                        self._abort_if_offline(str(e))
                        logger.warning("playwright_title_failed", error=str(e), fallback_to_requests=True)

                # Fallback to requests — unless ČSFD is already challenging plain HTTP,
                # in which case the next Playwright attempt is the only thing that can
                # get the page and this is a round trip spent to be told so again.
                if not self._plain_http_worth_trying():
                    continue
                self.rate_limiter.wait()
                response = self.session.get(
                    title_url,
                    headers={"User-Agent": self._get_random_user_agent()},
                    timeout=10,
                )
                response.raise_for_status()
                # 200 OK is not the same as "a title page". ČSFD answers plain HTTP
                # with its bot-protection interstitial — a valid, ~7 KB document that
                # every caller here then CACHES, and HTMLCache.has() only asks whether
                # a file exists, so the URL is never retried. Four titles were poisoned
                # this way on 2026-08-31 alone, one of them by purge_failed_cache
                # --refetch, the tool whose job is removing exactly this. Refusing the
                # page is strictly better than caching it: absent means retried.
                if not self._is_title_page(response.text):
                    logger.warning(
                        "title_page_not_a_title_page",
                        url=title_url, method="requests",
                        attempt=attempt + 1, bytes=len(response.text),
                    )
                    if self._is_challenge_page(response.text):
                        self._note_plain_http_challenged()
                    if attempt >= 2:
                        return None
                    continue
                logger.info("scrape_title_details_success", url=title_url, method="requests")
                return response.text

            except requests.Timeout:
                if attempt < 2:
                    wait_time = self.rate_limiter.get_backoff(attempt)
                    logger.warning(
                        "scrape_title_timeout_retry",
                        url=title_url,
                        attempt=attempt + 1,
                        wait_sec=wait_time,
                    )
                else:
                    logger.warning(
                        "scrape_title_timeout_final",
                        url=title_url,
                        attempts=3,
                    )
                    return None

            except requests.RequestException as e:
                self._abort_if_offline(str(e))
                logger.warning(
                    "scrape_title_request_error",
                    url=title_url,
                    error=str(e),
                    attempt=attempt + 1,
                )
                if attempt >= 2:
                    return None

        return None

    def _extract_title_details(self, soup: BeautifulSoup, url: str) -> Optional[Dict[str, Any]]:
        """
        Extract title details from BeautifulSoup object.

        Args:
            soup: BeautifulSoup parsed page
            url: Source URL (for deduplication)

        Returns:
            Dict with extracted fields or None if critical fields missing
        """
        data = {"url_id": url}

        # Extract title (mandatory)
        title_elem = soup.select_one(self.selectors.get("title_page", {}).get("title_selector"))
        if title_elem:
            data["title"] = title_elem.get_text(strip=True)
        else:
            logger.warning("title_extraction_failed", url=url)
            return None

        # Extract year (optional)
        year_elem = soup.select_one(self.selectors.get("title_page", {}).get("year_selector"))
        if year_elem:
            try:
                data["year"] = int(year_elem.get_text(strip=True))
            except (ValueError, AttributeError):
                data["year"] = None

        # Extract genres (optional, comma-separated)
        genre_elems = soup.select(self.selectors.get("title_page", {}).get("genre_selector", ""))
        if genre_elems:
            data["genres"] = " / ".join(e.get_text(strip=True) for e in genre_elems)

        # Extract directors (optional, comma-separated)
        director_elems = soup.select(self.selectors.get("title_page", {}).get("director_selector", ""))
        if director_elems:
            data["director"] = ", ".join(e.get_text(strip=True) for e in director_elems)

        # Extract actors (optional, comma-separated)
        actor_elems = soup.select(self.selectors.get("title_page", {}).get("actors_selector", ""))
        if actor_elems:
            data["actors"] = ", ".join(e.get_text(strip=True) for e in actor_elems)

        # Extract countries (optional, forward-slash separated)
        country_elems = soup.select(self.selectors.get("title_page", {}).get("country_selector", ""))
        if country_elems:
            data["countries"] = " / ".join(e.get_text(strip=True) for e in country_elems)

        # Extract VOD platforms (optional, comma-separated)
        vod_elems = soup.select(self.selectors.get("title_page", {}).get("vod_selector", ""))
        if vod_elems:
            data["vod_platforms"] = ", ".join(e.get_text(strip=True) for e in vod_elems)

        # Add link (same as url_id)
        data["link"] = url

        return data
