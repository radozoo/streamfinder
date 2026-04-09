"""VOD title parser using BeautifulSoup."""

from typing import Dict, Any, Optional
from bs4 import BeautifulSoup

from csfd_vod.transformation.models import VODTitle, ParsedTitle
from csfd_vod.logger import get_logger


logger = get_logger(__name__)


class VODTitleParser:
    """Parse VOD title details from HTML."""

    def __init__(self, selectors: Dict[str, Any]):
        """Initialize parser with CSS selectors."""
        self.selectors = selectors

    def parse(self, html_content: str, url: str) -> Optional[VODTitle]:
        """
        Parse HTML content and extract VOD title details.

        Args:
            html_content: HTML content as string
            url: Source URL (used for deduplication)

        Returns:
            Validated VODTitle or None if parsing fails
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            raw_data = self._extract_fields(soup, url)

            if not raw_data:
                logger.warning("parse_failed_no_data", url=url)
                return None

            parsed_title = ParsedTitle(url, raw_data)
            vod_title = parsed_title.to_vod_title()

            if not vod_title:
                for error in parsed_title.errors:
                    logger.warning("parse_validation_error", url=url, error=error)
                return None

            logger.info("parse_success", url=url, title=vod_title.title)
            return vod_title

        except Exception as e:
            logger.error("parse_exception", url=url, error=str(e))
            return None

    def _extract_fields(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract fields from BeautifulSoup object."""
        data = {"url_id": url}

        # Title (mandatory)
        title_selector = self.selectors.get("title_page", {}).get("title_selector")
        if title_selector:
            title_elem = soup.select_one(title_selector)
            if title_elem:
                data["title"] = title_elem.get_text(strip=True)

        # Year (optional)
        year_selector = self.selectors.get("title_page", {}).get("year_selector")
        if year_selector:
            year_elem = soup.select_one(year_selector)
            if year_elem:
                try:
                    year_text = year_elem.get_text(strip=True)
                    # Extract number from text like "(2020)"
                    data["year"] = int("".join(c for c in year_text if c.isdigit()))
                except (ValueError, AttributeError):
                    pass

        # Genres (optional)
        genre_selector = self.selectors.get("title_page", {}).get("genre_selector")
        if genre_selector:
            genre_elems = soup.select(genre_selector)
            if genre_elems:
                genres = " / ".join(e.get_text(strip=True) for e in genre_elems)
                if genres:
                    data["genres"] = genres

        # Directors (optional)
        director_selector = self.selectors.get("title_page", {}).get("director_selector")
        if director_selector:
            director_elems = soup.select(director_selector)
            if director_elems:
                directors = ", ".join(e.get_text(strip=True) for e in director_elems)
                if directors:
                    data["director"] = directors

        # Actors (optional)
        actor_selector = self.selectors.get("title_page", {}).get("actors_selector")
        if actor_selector:
            actor_elems = soup.select(actor_selector)
            if actor_elems:
                actors = ", ".join(e.get_text(strip=True) for e in actor_elems)
                if actors:
                    data["actors"] = actors

        # Countries (optional)
        country_selector = self.selectors.get("title_page", {}).get("country_selector")
        if country_selector:
            country_elems = soup.select(country_selector)
            if country_elems:
                countries = " / ".join(e.get_text(strip=True) for e in country_elems)
                if countries:
                    data["countries"] = countries

        # VOD Platforms (optional)
        vod_selector = self.selectors.get("title_page", {}).get("vod_selector")
        if vod_selector:
            vod_elems = soup.select(vod_selector)
            if vod_elems:
                vods = ", ".join(e.get_text(strip=True) for e in vod_elems)
                if vods:
                    data["vod_platforms"] = vods

        # Link (same as url_id)
        data["link"] = url

        return data
