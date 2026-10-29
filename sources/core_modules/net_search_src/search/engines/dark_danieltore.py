"""
search/engines/dark_danieltore.py
TorDex & Tor Hidden Directory search engine adapter.
Comprehensive index and directory crawler for Tor v3 hidden services.
"""
from __future__ import annotations

import logging
from typing import List

from .base import BaseEngine
from ..models import SearchQuery, SearchResult
from .. import http_client

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.daniel")
logger = hecos_logger

DEFAULT_TORDEX_ONION = "http://tordexu73joywapk2txdr54jed4imqledpcvcuf75qsas2gwdgksvnyd.onion/search"


def _get_directory_url() -> str:
    from ..config import get_search_config
    cfg = get_search_config().get("endpoints", {}).get("dark_danieltore", {})
    return cfg.get("onion_url") or DEFAULT_TORDEX_ONION


class DarkDanielEngine(BaseEngine):
    """TorDex & Tor Hidden Directory search engine."""

    def __init__(self):
        super().__init__(
            engine_id="dark_danieltore",
            name="TorDex (Tor Directory)",
            category="onion",
            network="tor",
            priority=84
        )

    def is_available(self) -> bool:
        from ..config import get_search_config
        cfg = get_search_config().get("tor", {})
        if not cfg.get("enabled", False):
            return False
        return http_client.is_tor_online()

    def search(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        if not self.is_available():
            return results

        raw_endpoint = _get_directory_url().rstrip("/")
        search_url = raw_endpoint if "/search" in raw_endpoint else f"{raw_endpoint}/search"
        params = {"q": query.query}
        hecos_logger.info(f"[SEARCH:TORDEX] Querying TorDex/Tor Directory: '{query.query}' at {search_url}...")

        try:
            resp = http_client.get(search_url, network="tor", params=params, timeout=query.timeout)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")

                seen_urls = set()
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if not href or href in seen_urls:
                        continue
                    if "tordex" in href:
                        continue
                    if ".onion" not in href:
                        continue

                    title = a.get_text(strip=True)
                    if not title or title.lower() in ["home", "search", "directory", "contact", "about"]:
                        continue

                    parent = a.find_parent(["div", "li", "p", "td", "tr"])
                    snippet = ""
                    if parent:
                        full_txt = parent.get_text(" ", strip=True)
                        if full_txt and full_txt != title:
                            snippet = full_txt[:280]

                    seen_urls.add(href)
                    results.append(SearchResult(
                        url=href,
                        title=title,
                        snippet=snippet,
                        engine=self.id,
                        category="onion",
                        network="tor"
                    ))
                    if len(results) >= query.limit:
                        break

            hecos_logger.info(f"[SEARCH:TORDEX] Found {len(results)} results.")
        except Exception as e:
            hecos_logger.warning(f"[SEARCH:TORDEX] Query failed: {e}")

        return results
