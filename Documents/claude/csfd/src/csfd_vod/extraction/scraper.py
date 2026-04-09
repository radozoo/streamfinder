"""VOD scraper with rate limiting and retry logic."""

import random
from typing import List, Optional, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from csfd_vod.extraction.rate_limiter import RateLimiter
from csfd_vod.logger import get_logger


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

        Args:
            vod_page_url: URL of the VOD listing page

        Returns:
            List of title page URLs
        """
        logger.info("scrape_vod_list_start", url=vod_page_url)

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

            logger.info("scrape_vod_list_success", count=len(title_urls))
            return title_urls

        except requests.RequestException as e:
            logger.error("scrape_vod_list_failed", error=str(e), url=vod_page_url)
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
