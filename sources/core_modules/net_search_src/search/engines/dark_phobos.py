"""
search/engines/dark_phobos.py
Phobos Tor onion search engine scraper.
Fast, uncensored dark web crawler on Tor v3 network.
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
    hecos_logger = logging.getLogger("browser.search.engines.phobos")
logger = hecos_logger

DEFAULT_PHOBOS_ONION = "http://phobosxilamwcg75xt22id7aywkzol6q6rfl2flipcqoc4e4ahima5id.onion/search"


def _get_phobos_url() -> str:
    from ..config import get_search_config
    cfg = get_search_config().get("endpoints", {}).get("dark_phobos", {})
    return cfg.get("onion_url") or DEFAULT_PHOBOS_ONION


class DarkPhobosEngine(BaseEngine):
    """Phobos .onion search engine."""

    def __init__(self):
        super().__init__(
            engine_id="dark_phobos",
            name="Phobos (Tor)",
            category="onion",
            network="tor",
            priority=83
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

        raw_endpoint = _get_phobos_url().rstrip("/")
        search_url = raw_endpoint if "/search" in raw_endpoint else f"{raw_endpoint}/search"
        params = {"q": query.query}
        hecos_logger.info(f"[SEARCH:PHOBOS] Querying Phobos via Tor: '{query.query}' at {search_url}...")

        try:
            resp = http_client.get(search_url, network="tor", params=params, timeout=min(query.timeout, 10.0))
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")

                seen_urls = set()
                items = soup.find_all("div", class_=lambda c: c and any(k in str(c).lower() for k in ["result", "serp-item", "item"]))
                for it in items[:query.limit]:
                    a_tag = it.find("a")
                    if a_tag:
                        href = a_tag.get("href", "").strip()
                        title = a_tag.get_text(strip=True)
                        snippet_tag = it.find(["p", "div"], class_=lambda c: c and any(k in str(c).lower() for k in ["snippet", "desc"]))
                        snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

                        if href and (".onion" in href or href.startswith("http")) and href not in seen_urls:
                            seen_urls.add(href)
                            results.append(SearchResult(
                                url=href,
                                title=title or href,
                                snippet=snippet,
                                engine=self.id,
                                category="onion",
                                network="tor"
                            ))

                if not results:
                    for a in soup.find_all("a", href=True):
                        href = a["href"].strip()
                        if ".onion" in href and "phobos" not in href and href not in seen_urls:
                            txt = a.get_text(strip=True)
                            if txt and len(txt) > 3:
                                seen_urls.add(href)
                                results.append(SearchResult(
                                    url=href,
                                    title=txt,
                                    snippet="",
                                    engine=self.id,
                                    category="onion",
                                    network="tor"
                                ))
                                if len(results) >= query.limit:
                                    break

            hecos_logger.info(f"[SEARCH:PHOBOS] Found {len(results)} results.")
        except Exception as e:
            hecos_logger.warning(f"[SEARCH:PHOBOS] Query failed: {e}")

        return results
