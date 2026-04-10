"""Parser for VOD list pages (monthly listings)."""

import re
from datetime import date
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup

from csfd_vod.logger import get_logger


logger = get_logger(__name__)

_CSFD_BASE = "https://www.csfd.cz"

# "V nabídce od 5. 4. 2026" or "V nabidce od 14.01.2015"
_VOD_DATE_RE = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})")


class VODListParser:
    """Parse VOD list pages for vod_date, list_type, distributor per film URL."""

    def parse(self, html: str, source: str = "") -> List[Dict[str, Any]]:
        """
        Parse a single list page HTML and return per-film metadata.

        Args:
            html: Raw HTML of the list page
            source: Optional source filename/label for logging

        Returns:
            List of dicts with keys: film_url, vod_date, list_type, distributor
        """
        soup = BeautifulSoup(html, "html.parser")
        results = []
        current_date: Optional[date] = None

        for elem in soup.select(".box-sub-header, article.article"):
            classes = elem.get("class", [])

            if "box-sub-header" in classes or elem.select_one(".date-title"):
                date_elem = elem.select_one(".date-title") or elem
                current_date = self._parse_vod_date(date_elem.get_text(strip=True))
                continue

            # article.article — one film entry
            entry = self._parse_article(elem)
            if entry.get("film_url"):
                entry["vod_date"] = current_date
                results.append(entry)

        logger.info("list_page_parsed", source=source, entries=len(results))
        return results

    def _parse_vod_date(self, text: str) -> Optional[date]:
        """Parse 'V nabídce od D. M. YYYY' or similar into a date."""
        m = _VOD_DATE_RE.search(text)
        if m:
            try:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                pass
        return None

    def _parse_article(self, article) -> Dict[str, Any]:
        """Extract film_url, list_type, distributor from a single article element."""
        entry: Dict[str, Any] = {
            "film_url": None,
            "list_type": None,
            "distributor": None,
        }

        # Film URL — .article-img a[href]
        link_elem = article.select_one(".article-img a[href]")
        if link_elem:
            href = link_elem["href"]
            entry["film_url"] = href if href.startswith("http") else f"{_CSFD_BASE}{href}"

        # Type — second .info inside .film-title-info ("epizoda", "serial", etc.)
        info_elems = article.select(".film-title-info .info")
        if len(info_elems) >= 2:
            type_text = info_elems[1].get_text(strip=True).lower()
            if type_text:
                entry["list_type"] = type_text
        elif len(info_elems) == 1:
            # Single .info may still carry type if it says "serial"/"epizoda"
            type_text = info_elems[0].get_text(strip=True).lower()
            if type_text in ("serial", "epizoda", "série"):
                entry["list_type"] = type_text

        # Distributor — <p> containing "Distributor:"
        for p in article.select("p"):
            text = p.get_text(strip=True)
            if "Distributor:" in text or "distributor:" in text.lower():
                parts = text.split(":", 1)
                if len(parts) == 2:
                    entry["distributor"] = parts[1].strip() or None
                break

        return entry
