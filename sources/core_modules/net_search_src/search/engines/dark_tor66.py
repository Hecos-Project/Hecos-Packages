"""
search/engines/dark_tor66.py
Tor66 Tor onion search engine scraper.
Fresh crawl indices for hidden services on modern Tor v3 network.
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
    hecos_logger = logging.getLogger("browser.search.engines.tor66")
logger = hecos_logger

DEFAULT_TOR66_ONION = "http://tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion/search"


def _get_tor66_url() -> str:
    from ..config import get_search_config
    cfg = get_search_config().get("endpoints", {}).get("dark_tor66", {})
    return cfg.get("onion_url") or DEFAULT_TOR66_ONION


class DarkTor66Engine(BaseEngine):
    """Tor66 .onion search engine."""

    def __init__(self):
        super().__init__(
            engine_id="dark_tor66",
            name="Tor66 (Dark Web)",
            category="onion",
            network="tor",
            priority=81
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

        raw_endpoint = _get_tor66_url().rstrip("/")
        search_url = raw_endpoint if "/search" in raw_endpoint else f"{raw_endpoint}/search"
        params = {"q": query.query}
        hecos_logger.info(f"[SEARCH:TOR66] Querying Tor66 via Tor: '{query.query}' at {search_url}...")

        try:
            resp = http_client.get(search_url, network="tor", params=params, timeout=query.timeout)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")

                seen_urls = set()
                # Parse all distinct onion results returned by Tor66
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if not href or href in seen_urls:
                        continue
                    # Ignore Tor66 internal links
                    if "tor66sewebg" in href:
                        continue
                    if ".onion" not in href:
                        continue

                    title = a.get_text(strip=True)
                    if not title or title.lower() in ["home", "search", "advertise", "contact", "about"]:
                        continue

                    parent = a.find_parent(["div", "li", "p", "td"])
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

            hecos_logger.info(f"[SEARCH:TOR66] Found {len(results)} results.")
        except Exception as e:
            hecos_logger.warning(f"[SEARCH:TOR66] Query failed: {e}")

        return results
