"""
search/engines/dark_tor66.py
Tor66 Tor onion search engine scraper.
Fresh crawl indices for hidden services on modern Tor v3 network.
"""
from __future__ import annotations

import logging
from typing import List

from .base import BaseEngine, effective_tor_timeout
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
        tor_timeout = effective_tor_timeout(query.timeout, minimum=16.0)
        hecos_logger.info(f"[SEARCH:TOR66] Querying Tor66 via Tor: '{query.query}' at {search_url} (timeout={tor_timeout}s)...")

        seen_urls = set()
        max_pages = 3 if query.limit > 25 else 1
        try:
            for page_num in range(1, max_pages + 1):
                if len(results) >= query.limit:
                    break
                params = {"q": query.query}
                if page_num > 1:
                    params["page"] = str(page_num)

                resp = http_client.get(search_url, network="tor", params=params, timeout=tor_timeout)
                if resp.status_code != 200:
                    break
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")

                added_this_page = 0
                # Parse all distinct onion results returned by Tor66
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if not href or href in seen_urls:
                        continue
                    # Ignore Tor66 internal links
                    if "tor66sewebg" in href or ".onion" not in href.lower():
                        continue

                    title = a.get_text(strip=True)
                    if not title or title.lower() in ["home", "search", "advertise", "contact", "about", "next", "previous"]:
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
                    added_this_page += 1
                    if len(results) >= query.limit:
                        break
                if added_this_page == 0:
                    break

            hecos_logger.info(f"[SEARCH:TOR66] Found {len(results)} results.")
        except Exception as e:
            hecos_logger.warning(f"[SEARCH:TOR66] Query failed: {e}")

        return results
