"""VOD title parser using BeautifulSoup."""

import re
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
        """Extract fields from BeautifulSoup object using CSFD HTML structure."""
        data = {"url_id": url}

        # Title (mandatory) — .film-header h1
        title_selector = self.selectors.get("title_page", {}).get("title_selector")
        if title_selector:
            title_elem = soup.select_one(title_selector)
            if title_elem:
                data["title"] = title_elem.get_text(strip=True)

        # Year + Country (optional) — both from .origin text
        # Structure: "USA <bullet> (2021–2026) <bullet> 24 h ..."
        origin = soup.select_one(".origin")
        if origin:
            origin_text = origin.get_text()
            # Year: first 4-digit year found (start year for series)
            years = re.findall(r"(?:19|20)\d{2}", origin_text)
            if years:
                data["year"] = int(years[0])
            # Country: text before the first "(" (strip bullets/whitespace)
            country_raw = re.split(r"[\(\d]", origin_text)[0]
            country = re.sub(r"\s+", " ", country_raw).strip()
            if country:
                data["countries"] = country

        # Genres (optional) — .genres a
        genre_selector = self.selectors.get("title_page", {}).get("genre_selector")
        if genre_selector:
            genre_elems = soup.select(genre_selector)
            if genre_elems:
                genres = " / ".join(e.get_text(strip=True) for e in genre_elems)
                if genres:
                    data["genres"] = genres

        # Directors (optional) — <h4>Režie:</h4> sibling <a> links
        h4_rezii = soup.find("h4", string="Režie:")
        if h4_rezii:
            directors = [a.get_text(strip=True) for a in h4_rezii.parent.select("a") if a.get_text(strip=True).lower() != "více"]
            if directors:
                data["director"] = ", ".join(directors)

        # Actors (optional) — <h4>Hrají:</h4> sibling <a> links
        h4_hraji = soup.find("h4", string="Hrají:")
        if h4_hraji:
            actors = [a.get_text(strip=True) for a in h4_hraji.parent.select("a") if a.get_text(strip=True).lower() != "více"]
            if actors:
                data["actors"] = ", ".join(actors)

        # VOD Platforms (optional) — .film-vod-list a (exclude "více" = "more" link)
        vod_links = soup.select(".film-vod-list a")
        platforms = [a.get_text(strip=True) for a in vod_links if a.get_text(strip=True).lower() not in ("více", "")]
        if platforms:
            data["vod_platforms"] = ", ".join(platforms)

        # Link (same as url_id)
        data["link"] = url

        return data
