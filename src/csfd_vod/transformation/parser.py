"""VOD title parser using BeautifulSoup."""

import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup

from csfd_vod.transformation.models import VODTitle, ParsedTitle
from csfd_vod.transformation.text import clean_text, split_services
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
            # The "(S03E05)" marker sits on its own indented line inside the <h1>.
            # It is deliberately KEPT — the season/episode parsing below reads the
            # numbers back out of the title — but it must not drag newlines with it.
            data["title"] = clean_text(title_elem.get_text(strip=True))

        # --- Alternative names — .film-header-name .film-names li ---
        # ČSFD lists every release name the title has, one <li> per country/language:
        # the country-of-origin name first, then transliterations, the original script,
        # and the English/Slovak/… releases — most of them hidden behind a "více" toggle.
        #
        # `title_en` keeps the FIRST one (the origin name, which is what the detail page
        # shows under the Czech title and what TMDB matches as the original title), but
        # taking only that one used to throw the rest away — and the English name is
        # frequently NOT first: "Hra na oliheň" kept "Ojingeo geim" while "Squid Game"
        # sat in <li> #3, "Cesta do fantazie" kept "Sen to Čihiro no kamikakuši" and
        # dropped "Spirited Away". So all of them are kept in `alt_titles`, which is what
        # search matches against. Exclude <a> link text ("více"/"méně" toggles, appended
        # by get_text).
        names = []
        for li in soup.select(".film-header-name .film-names li"):
            name = clean_text("".join(
                s for s in li.strings
                if s.strip().lower() not in ("více", "méně", "more", "")
            ))
            if name and name not in names:
                names.append(name)  # same name under 5 flags is one name
        if names:
            data["title_en"] = names[0]
            data["alt_titles"] = names

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

        # --- Genres — .genres container ---
        # CSFD only hyperlinks genres that have a dedicated /zanry/ page; secondary
        # genres (Mysteriózní, Rodinný, Stand-up, Sportovní, Reality-TV, Hudební…)
        # are rendered as bare text nodes between bullet separators. Collect BOTH the
        # <a> links and the bare text, skipping the <span class="bullet"> separators.
        genre_selector = self.selectors.get("title_page", {}).get("genre_selector", ".genres a")
        container_selector = genre_selector[:-2] if genre_selector.endswith(" a") else genre_selector
        genre_container = soup.select_one(container_selector)
        if genre_container is not None:
            parts = []
            for node in genre_container.children:
                name = getattr(node, "name", None)
                if name == "a":
                    text = node.get_text(strip=True)
                elif name is None:  # NavigableString — a bare genre or whitespace
                    text = str(node).strip()
                else:  # <span class="bullet"> and any other element = separator
                    text = ""
                if text:
                    parts.append(text)
            if parts:
                data["genres"] = " / ".join(parts)

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

        # --- Votes count — .more-modal-ratings-fanclub text "Hodnocení (131 654)" ---
        # ČSFD groups thousands with a NON-BREAKING SPACE, so a plain (\d+) stopped
        # at the first group and silently stored Forrest Gump's 131654 votes as 131.
        # Every title above 999 votes was truncated to its leading group — which
        # quietly wrecked anything ranking by popularity or obscurity. Match the
        # separators too, then keep only the digits.
        votes_elem = soup.select_one(".more-modal-ratings-fanclub")
        if votes_elem:
            votes_text = votes_elem.get_text(strip=True)
            votes_match = re.search(r"Hodnocen[íi]\D*([\d \s.,]*\d)", votes_text)
            if votes_match:
                data["votes_count"] = int(re.sub(r"\D", "", votes_match.group(1)))

        # --- Tags — .box-tags a ---
        # Skip the "více" (show-more) toggle link that lives inside .box-tags — it
        # is not a tag (it was being stored as one on ~660 titles).
        tag_elems = soup.select(".box-tags a")
        if tag_elems:
            tags = ", ".join(
                text
                for t in tag_elems
                if (text := t.get_text(strip=True)) and text.lower() not in ("více", "more")
            )
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

        # --- VOD Platforms + URLs — service links only ---
        # Scope to the services container: `.film-vod-list a` also matches the
        # section's <h3><a href="/vod/">VOD</a> heading link and the "více" toggle,
        # which are not platforms. The real services live in .box-film-vod-services.
        vod_links = soup.select(".film-vod-list .box-film-vod-services a")
        platforms = []
        vod_url_map = {}
        for a in vod_links:
            # A link occasionally carries two services at once, split across lines
            # ("Peacock /\n\t\t\tHulu"). Collapse the whitespace, then split on "/"
            # so each service is its own platform — as one blob it matches no alias
            # and no brand colour, and shows up as a bogus third "platform".
            raw = clean_text(a.get_text(strip=True))
            href = a.get("href", "")
            for name in (n.strip() for n in raw.split("/")):
                if name.lower() in ("více", "vod", ""):
                    continue
                platforms.append(name)
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

        # --- Hierarchy: root_id / csfd_id from URL segments ---
        # /film/{ROOT}-slug/{CHILD}-slug/prehled/ → child (episode/season under a serial)
        # /film/{ID}-slug/prehled/                → top-level work (root_id == csfd_id)
        # Each "/{id}-slug/" segment is an id: first = root serial, last = the entity
        # itself. (A plain "/film/(\d+)" would only see the first segment.)
        # The slug is optional: a title whose name has no alphanumerics slugifies to
        # nothing, giving a bare "/film/17338/" — the film "$". Requiring "-slug"
        # left those rows with no hierarchy ids at all.
        seg_ids = re.findall(r"/(\d+)(?:-[^/]*)?(?=/)", url)
        if seg_ids:
            data["root_id"] = int(seg_ids[0])
            data["csfd_id"] = int(seg_ids[-1])
            is_child = data["root_id"] != data["csfd_id"]
            if is_child and not data.get("title_type"):
                data["title_type"] = "epizoda"

        # --- Season / episode number ---
        # Episodes carry a "(S02E05)" or bare "(E07)" marker in the title; standalone
        # seasons carry only a season number in the URL slug or title.
        title_text = data.get("title") or ""
        se = re.search(r"S(\d+)E(\d+)", title_text)
        if se:
            data["season_no"] = int(se.group(1))
            data["episode_no"] = int(se.group(2))
        else:
            e_only = re.search(r"\(E(\d+)\)", title_text)
            if e_only:
                data["episode_no"] = int(e_only.group(1))
            if data.get("title_type") == "série":
                slug_m = re.search(r"/\d+-(?:serie|season)-(\d+)", url)
                title_m = re.search(r"[Ss](?:érie|erie|eason) (\d+)", title_text)
                if slug_m:
                    data["season_no"] = int(slug_m.group(1))
                elif title_m:
                    data["season_no"] = int(title_m.group(1))

        # --- Serial totals from the "Série (N) Epizody (M)" header ---
        # Authoritative counts the show has (single-season shows omit "Série (N)").
        for h in soup.select("h3"):
            ht = h.get_text(" ", strip=True)
            if "Epizody" in ht or "Série" in ht:
                ms = re.search(r"Série\s*\((\d+)\)", ht)
                me = re.search(r"Epizody\s*\((\d+)\)", ht)
                if ms:
                    data["season_total"] = int(ms.group(1))
                if me:
                    data["episode_total"] = int(me.group(1))
                if ms or me:
                    break

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
