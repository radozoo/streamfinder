"""VOD scraper with rate limiting and retry logic."""

import re
import random
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

    # A real listing page is hundreds of KB; a bot-protection challenge stub (no
    # listing, just an `ab_detection` script) observed at 334 bytes. Anything this
    # small is a failed fetch, not a legitimately empty/short page.
    _MIN_LISTING_PAGE_BYTES = 5000

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
                if page_path is not None and page_path.exists() and not stale:
                    html = page_path.read_text(encoding="utf-8")
                    urls = self._extract_title_urls(html)
                else:
                    urls, html = self.scrape_vod_month_page(year, month, page)
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
            suspect = reason == "cap" or (reason == "empty" and last_nonempty >= 1)
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

                # Wait for at least one element matching the selector, or timeout
                try:
                    page.wait_for_selector(selector, timeout=5000)
                    logger.info("playwright_selector_found", selector=selector)
                except Exception as e:
                    logger.warning("selector_not_found_in_page", selector=selector, error=str(e))

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

                # Wait for at least the title element, or timeout
                try:
                    page.wait_for_selector(selector, timeout=5000)
                    logger.info("playwright_title_selector_found", selector=selector)
                except Exception as e:
                    logger.warning("title_selector_not_found_in_page", selector=selector, error=str(e))

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
            logger.error("scrape_vod_list_failed", error=str(e), url=vod_page_url, method="requests")
            return [], ""

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
                        if html_content:
                            logger.info("scrape_title_details_success", url=title_url, method="playwright")
                            return html_content
                    except Exception as e:
                        logger.warning("playwright_title_failed", error=str(e), fallback_to_requests=True)

                # Fallback to requests
                self.rate_limiter.wait()
                response = self.session.get(
                    title_url,
                    headers={"User-Agent": self._get_random_user_agent()},
                    timeout=10,
                )
                response.raise_for_status()
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
