"""File-based HTML cache keyed by URL hash."""

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

from csfd_vod.logger import get_logger

logger = get_logger(__name__)


class HTMLCache:
    """
    Persist raw HTML to disk so scraping and parsing can run independently.

    Layout:
        cache/
            html/
                {md5[:8]}.html   # raw HTML per URL
            urls.json            # URL → hash index for human inspection
    """

    def __init__(self, cache_dir: str = "cache"):
        self.html_dir = Path(cache_dir) / "html"
        self.index_path = Path(cache_dir) / "urls.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def has(self, url: str) -> bool:
        """Return True if HTML for this URL is already cached."""
        return self._html_path(url).exists()

    def get(self, url: str) -> Optional[str]:
        """Return cached HTML string, or None if not cached."""
        path = self._html_path(url)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def save(self, url: str, html: str) -> None:
        """Save HTML to disk and update the URL index."""
        self.html_dir.mkdir(parents=True, exist_ok=True)
        hash_key = self._url_hash(url)
        self._html_path(url).write_text(html, encoding="utf-8")
        self._update_index(url, hash_key)
        logger.info("cache_saved", url=url, hash=hash_key)

    def all_urls(self) -> List[str]:
        """Return all URLs that have cached HTML."""
        return list(self._load_index().keys())

    def delete(self, url: str) -> bool:
        """Remove cached HTML for url. Returns True if entry existed."""
        path = self._html_path(url)
        existed = path.exists()
        if existed:
            path.unlink()
        index = self._load_index()
        if url in index:
            del index[url]
            self.index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
        return existed

    def count(self) -> int:
        """Return number of cached pages."""
        return len(self.all_urls())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _url_hash(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()[:8]

    def _html_path(self, url: str) -> Path:
        return self.html_dir / f"{self._url_hash(url)}.html"

    def _load_index(self) -> Dict[str, str]:
        if self.index_path.exists():
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        return {}

    def _update_index(self, url: str, hash_key: str) -> None:
        index = self._load_index()
        index[url] = hash_key
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
