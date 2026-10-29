"""
search/engines/dark_onionland.py
Onion Search Engine (OSE) adapter.
Indexes Dark Web .onion sites via high-speed clearnet gateway and Tor v3 hidden service.
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
    hecos_logger = logging.getLogger("browser.search.engines.onionland")
logger = hecos_logger

DEFAULT_ONIONLAND_CLEAR = "https://onionsearchengine.com/search.php"
DEFAULT_ONIONLAND_ONION = "http://37djtvjcpiprohcrlyvlhfil45kdlfizsyvilqskgvdrafn5mocz4cid.onion/search.php"


def _get_onionland_urls() -> tuple[str, str]:
    """Retrieves Onion Search Engine endpoints from configuration."""
    from ..config import get_search_config
    cfg = get_search_config().get("endpoints", {}).get("dark_onionland", {})
    clear = cfg.get("clearnet_url") or DEFAULT_ONIONLAND_CLEAR
    onion = cfg.get("onion_url") or DEFAULT_ONIONLAND_ONION
    return clear, onion


class DarkOnionlandEngine(BaseEngine):
    """Onion Search Engine (Dark Web / Tor)."""

    def __init__(self):
        super().__init__(
            engine_id="dark_onionland",
            name="Onion Search Engine",
            category="onion",
            network="tor",
            priority=82
        )

    def is_available(self) -> bool:
        from ..config import get_search_config
        cfg = get_search_config().get("tor", {})
        if not cfg.get("enabled", False):
            return False
        return True

    def search(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        clear_url, onion_url = _get_onionland_urls()
        tor_online = http_client.is_tor_online()
        params = {"q": query.query}

        # Try fast clearnet gateway first, fallback to Tor onion
        endpoints = [(clear_url, "clearnet")]
        if tor_online:
            endpoints.append((onion_url, "tor"))

        for url, net in endpoints:
            try:
                hecos_logger.info(f"[SEARCH:ONIONLAND] Querying Onion Search Engine via {net}: '{query.query}'...")
                resp = http_client.get(url, network=net, params=params, timeout=query.timeout)
                if resp.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "lxml")

                    seen_urls = set()
                    for a in soup.find_all("a", href=True):
                        href = a["href"].strip()
                        if not href or href in seen_urls:
                            continue
                        if ".onion" not in href or "report_page" in href:
                            continue

                        title = a.get_text(strip=True)
                        if not title:
                            continue

                        parent = a.find_parent(["div", "li", "article"])
                        snippet = ""
                        if parent:
                            p = parent.find(["p", "span"])
                            if p and p.get_text(strip=True) != title:
                                snippet = p.get_text(strip=True)[:280]
                            else:
                                full_txt = parent.get_text(" ", strip=True)
                                if full_txt and full_txt != title:
                                    snippet = full_txt[:280]

                        seen_urls.add(href)
                        results.append(SearchResult(
                            title=title,
                            url=href,
                            snippet=snippet,
                            engine=self.id,
                            category="onion",
                            network="tor"
                        ))
                        if len(results) >= query.limit:
                            break

                if results:
                    break
            except Exception as e:
                hecos_logger.debug(f"[DarkOnionland] Query failed via {net}: {e}")

        hecos_logger.info(f"[SEARCH:ONIONLAND] Found {len(results)} results.")
        return results
