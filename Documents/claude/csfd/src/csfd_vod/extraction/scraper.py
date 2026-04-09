"""VOD scraper with rate limiting and retry logic."""

import random
import time
from typing import List, Optional, Dict, Any
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
                return self._scrape_vod_list_playwright(vod_page_url)
            except Exception as e:
                logger.warning("playwright_failed", error=str(e), fallback_to_requests=True)

        # Fallback to requests
        return self._scrape_vod_list_requests(vod_page_url)

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
                return title_urls

        except Exception as e:
            if browser:
                try:
                    browser.close()
                except:
                    pass
            logger.error("playwright_scrape_failed", error=str(e), url=vod_page_url)
            raise

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
            return title_urls

        except requests.RequestException as e:
            logger.error("scrape_vod_list_failed", error=str(e), url=vod_page_url, method="requests")
            return []

    def scrape_title_details(self, title_url: str) -> Optional[Dict[str, Any]]:
        """
        Scrape full details for a single title.

        Args:
            title_url: URL of the title page

        Returns:
            Dict with extracted fields or None if parsing fails
        """
        for attempt in range(3):
            try:
                self.rate_limiter.wait()
                response = self.session.get(
                    title_url,
                    headers={"User-Agent": self._get_random_user_agent()},
                    timeout=10,
                )
                response.raise_for_status()

                soup = BeautifulSoup(response.content, "html.parser")
                return self._extract_title_details(soup, title_url)

            except requests.Timeout:
                if attempt < 2:
                    wait_time = self.rate_limiter.get_backoff(attempt)
                    logger.warning(
                        "scrape_timeout_retry",
                        url=title_url,
                        attempt=attempt + 1,
                        wait_sec=wait_time,
                    )
                else:
                    logger.warning(
                        "scrape_timeout_final",
                        url=title_url,
                        attempts=3,
                    )
                    return None

            except requests.RequestException as e:
                logger.warning(
                    "scrape_request_error",
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
