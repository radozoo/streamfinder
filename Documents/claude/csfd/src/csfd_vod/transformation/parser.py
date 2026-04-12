"""VOD title parser using BeautifulSoup."""

import json
import re
from datetime import datetime, timezone
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

    def _extract_crew(self, soup: BeautifulSoup, label: str) -> Optional[str]:
        """Extract crew names by h4 label (e.g. 'Scénář:', 'Kamera:', 'Hudba:')."""
        h4 = soup.find("h4", string=label)
        if h4:
            names = [
                a.get_text(strip=True)
                for a in h4.parent.select("a")
                if a.get_text(strip=True).lower() not in ("více", "")
            ]
            return ", ".join(names) if names else None
        return None

    def _extract_fields(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract all 18 fields from detail page HTML."""
        data = {"url_id": url, "link": url}

        # --- Title (mandatory) — .film-header h1 ---
        title_selector = self.selectors.get("title_page", {}).get("title_selector", ".film-header h1")
        title_elem = soup.select_one(title_selector)
        if title_elem:
            data["title"] = title_elem.get_text(strip=True)

        # --- English/original title — .film-header-name .film-names li (first <li>) ---
        # Exclude <a> link text (e.g. "více" expand link appended by get_text)
        names_list = soup.select(".film-header-name .film-names li")
        if names_list:
            li = names_list[0]
            title_en = "".join(
                s for s in li.strings
                if s.strip().lower() not in ("více", "more", "")
            ).strip()
            data["title_en"] = title_en or None

        # --- Year + Country + Runtime — all from .origin text ---
        # Structure: "USA / Velká Británie, (2021–2026), 24 h ..."
        origin = soup.select_one(".origin")
        if origin:
            origin_text = origin.get_text()
            # Year: first 4-digit year
            years = re.findall(r"(?:19|20)\d{2}", origin_text)
            if years:
                data["year"] = int(years[0])
            # Country: text before the first digit or "(" (strip bullets/whitespace)
            country_raw = re.split(r"[\(\d]", origin_text)[0]
            country = re.sub(r"[,\s]+$", "", re.sub(r"\s+", " ", country_raw).strip())
            if country:
                data["countries"] = country
            # Runtime: "3 h 19 min" → 199, "44 min" → 44, "2 h" → 120
            # Use main duration, not the per-episode range in parentheses
            main_duration = re.split(r"\(", origin_text)[0]
            hm_match = re.search(r"(\d+)\s*h\s*(\d+)\s*min", main_duration)
            h_match = re.search(r"(\d+)\s*h(?!\s*\d+\s*min)", main_duration)
            m_match = re.search(r"(\d+)\s*min", main_duration)
            if hm_match:
                data["runtime_min"] = int(hm_match.group(1)) * 60 + int(hm_match.group(2))
            elif h_match:
                data["runtime_min"] = int(h_match.group(1)) * 60
            elif m_match:
                data["runtime_min"] = int(m_match.group(1))

        # --- Genres — .genres a ---
        genre_selector = self.selectors.get("title_page", {}).get("genre_selector", ".genres a")
        genre_elems = soup.select(genre_selector)
        if genre_elems:
            genres = " / ".join(e.get_text(strip=True) for e in genre_elems)
            if genres:
                data["genres"] = genres

        # --- Director — <h4>Režie:</h4> sibling <a> links ---
        director = self._extract_crew(soup, "Režie:")
        if director:
            data["director"] = director

        # --- Script — <h4>Scénář:</h4> ---
        script = self._extract_crew(soup, "Scénář:")
        if script:
            data["script"] = script

        # --- Camera — <h4>Kamera:</h4> ---
        camera = self._extract_crew(soup, "Kamera:")
        if camera:
            data["camera"] = camera

        # --- Music — <h4>Hudba:</h4> ---
        music = self._extract_crew(soup, "Hudba:")
        if music:
            data["music"] = music

        # --- Actors — <h4>Hrají:</h4> sibling <a> links ---
        actors = self._extract_crew(soup, "Hrají:")
        if actors:
            data["actors"] = actors

        # --- Plot — .plot-full, fallback .body--plots ---
        plot_elem = soup.select_one(".plot-full")
        if not plot_elem:
            plot_elem = soup.select_one(".body--plots")
        if plot_elem:
            plot_text = plot_elem.get_text(strip=True)
            if plot_text:
                data["plot"] = plot_text

        # --- Rating — .film-rating-average text, parse int (NULL if "? %") ---
        rating_elem = soup.select_one(".film-rating-average")
        if rating_elem:
            rating_text = rating_elem.get_text(strip=True)
            match = re.match(r"(\d+)\s*%", rating_text)
            if match:
                data["rating"] = int(match.group(1))

        # --- Votes count — .more-modal-ratings-fanclub text "Hodnocení467" ---
        votes_elem = soup.select_one(".more-modal-ratings-fanclub")
        if votes_elem:
            votes_text = votes_elem.get_text(strip=True)
            votes_match = re.search(r"Hodnocen[íi]\D*(\d+)", votes_text)
            if votes_match:
                data["votes_count"] = int(votes_match.group(1))

        # --- Tags — .box-tags a ---
        tag_elems = soup.select(".box-tags a")
        if tag_elems:
            tags = ", ".join(t.get_text(strip=True) for t in tag_elems if t.get_text(strip=True))
            if tags:
                data["tags"] = tags

        # --- Image URL — img[src*="/film/posters/"] ---
        img_elem = soup.select_one('img[src*="/film/posters/"]')
        if img_elem:
            src = img_elem.get("src")
            if src:
                if src.startswith("http"):
                    data["image_url"] = src
                elif src.startswith("//"):
                    data["image_url"] = "https:" + src
                else:
                    data["image_url"] = f"https://www.csfd.cz{src}"

        # --- VOD Platforms + URLs — .film-vod-list a ---
        vod_links = soup.select(".film-vod-list a")
        platforms = []
        vod_url_map = {}
        for a in vod_links:
            name = a.get_text(strip=True)
            if name.lower() in ("více", ""):
                continue
            platforms.append(name)
            href = a.get("href", "")
            if href and href.startswith("http"):
                vod_url_map[name] = href
        if platforms:
            data["vod_platforms"] = ", ".join(platforms)
        if vod_url_map:
            data["vod_urls"] = json.dumps(vod_url_map, ensure_ascii=False)

        # --- Trailer URL — first YouTube link on page ---
        trailer_link = soup.select_one("a[href*='youtube.com/watch']")
        if trailer_link:
            data["trailer_url"] = trailer_link.get("href")

        # --- Age rating — "od X let" in .origin or .film-info ---
        for selector in (".origin", ".film-info"):
            elem = soup.select_one(selector)
            if elem:
                age_match = re.search(r"od\s+(\d+)\s+let", elem.get_text())
                if age_match:
                    data["age_rating"] = f"od {age_match.group(1)} let"
                    break

        # --- Premiere detail — .updated-box-content-padding containing "Na VOD od" ---
        for elem in soup.select(".updated-box-content-padding"):
            text = elem.get_text(strip=True)
            if "Na VOD od" in text or "na VOD od" in text.lower():
                data["premiere_detail"] = text
                break

        # --- Title type — .film-header-name .type span ---
        type_span = soup.select_one(".film-header-name .type")
        if type_span:
            type_text = type_span.get_text(strip=True).strip("()")
            if type_text:
                data["title_type"] = type_text.lower()

        # --- Parent URL from child URL pattern ---
        # /film/{parent_id}/{child_id}-slug/prehled/ → parent = /film/{parent_id}-slug/prehled/
        child_match = re.match(r"(https://www\.csfd\.cz/film/)(\d+)/(\d+)", url)
        if child_match:
            parent_id = child_match.group(2)
            data["parent_url"] = f"https://www.csfd.cz/film/{parent_id}/prehled/"
            if not data.get("title_type"):
                data["title_type"] = "epizoda"

        # --- Reviews (first 3, as JSON) ---
        review_articles = soup.select("article.article-review")[:3]
        reviews = []
        for rev in review_articles:
            author_el = rev.select_one("a.user-title-name")
            text_el = next(
                (p for p in rev.select("p") if len(p.get_text(strip=True)) > 20),
                None,
            )
            stars_el = rev.select_one(".stars")
            stars = None
            if stars_el:
                classes = stars_el.get("class", [])
                for cls in classes:
                    m = re.search(r"stars-(\d+)", cls)
                    if m:
                        stars = int(m.group(1))
                        break
            reviews.append({
                "author": author_el.get_text(strip=True) if author_el else None,
                "text": text_el.get_text(strip=True) if text_el else None,
                "stars": stars,
            })
        if reviews:
            data["reviews"] = json.dumps(reviews, ensure_ascii=False)

        # --- Default title_type to "film" if no type span and not a child URL ---
        if not data.get("title_type"):
            data["title_type"] = "film"

        # --- scraped_at — current timestamp (UTC) ---
        data["scraped_at"] = datetime.now(timezone.utc)

        return data
