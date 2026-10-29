"""
search/engines/dark_excavator.py
Excavator Tor onion search engine scraper.
Dedicated crawler for Excavator deep web search engine.
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
    hecos_logger = logging.getLogger("browser.search.engines.excavator")
logger = hecos_logger

DEFAULT_EXCAVATOR_ONION = "http://2fd6cemt4gmccflhm6imvdfvli3nf7zn6rfrwpsy7uhxrgbypvwf5fad.onion/search"


def _get_excavator_url() -> str:
    from ..config import get_search_config
    cfg = get_search_config().get("endpoints", {}).get("dark_excavator", {})
    return cfg.get("onion_url") or DEFAULT_EXCAVATOR_ONION


class DarkExcavatorEngine(BaseEngine):
    """Excavator .onion search engine."""

    def __init__(self):
        super().__init__(
            engine_id="dark_excavator",
            name="Excavator (Tor)",
            category="onion",
            network="tor",
            priority=85
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

        raw_endpoint = _get_excavator_url().rstrip("/")
        search_url = raw_endpoint if "/search" in raw_endpoint else f"{raw_endpoint}/search"
        # Excavator HTML uses name="query", support both query and q
        params = {"query": query.query, "q": query.query}
        hecos_logger.info(f"[SEARCH:EXCAVATOR] Querying Excavator via Tor: '{query.query}' at {search_url}...")

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
                    # Exclude self-references and non-onion navigation
                    if "2fd6cemt4g" in href or "2fd6uvfdwh" in href:
                        continue
                    if ".onion" not in href:
                        continue

                    title = a.get_text(strip=True)
                    if not title or title.lower() in ["advertise", "add url", "about", "terms"]:
                        continue

                    # Try to extract surrounding snippet
                    parent = a.find_parent(["div", "p", "li", "article"])
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

            hecos_logger.info(f"[SEARCH:EXCAVATOR] Found {len(results)} results.")
        except Exception as e:
            hecos_logger.warning(f"[SEARCH:EXCAVATOR] Query failed: {e}")

        return results
