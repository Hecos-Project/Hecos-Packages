"""
search/engines/dark_haystak.py
Haystak Tor onion search engine scraper.
Indexes pages on the Tor dark web using modern V3 architecture.
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
    hecos_logger = logging.getLogger("browser.search.engines.haystak")
logger = hecos_logger

DEFAULT_HAYSTAK_ONION = "http://haystak5njsmn2hqkewecpaxetahtwhsbsa64jom2k22z5afxhnpxfid.onion"


def _get_haystak_url() -> str:
    """Retrieves Haystak onion endpoint from configuration."""
    from ..config import get_search_config
    cfg = get_search_config().get("endpoints", {}).get("dark_haystak", {})
    return cfg.get("onion_url") or DEFAULT_HAYSTAK_ONION


class DarkHaystakEngine(BaseEngine):
    """Haystak .onion search engine."""

    def __init__(self):
        super().__init__(
            engine_id="dark_haystak",
            name="Haystak (Dark Web)",
            category="onion",
            network="tor",
            priority=80
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

        params = {"q": query.query}
        from ..config import get_engine_auth_headers
        auth_headers = get_engine_auth_headers("dark_haystak", "onion")
        if "X-API-Key" in auth_headers:
            params["key"] = auth_headers["X-API-Key"]

        onion_url = _get_haystak_url().rstrip("/")
        search_urls = [onion_url, f"{onion_url}/search"]
        hecos_logger.info(f"[SEARCH:HAYSTAK] Querying Haystak via Tor: '{query.query}' at {onion_url} (Auth={'Yes' if auth_headers else 'No'})...")

        for s_url in search_urls:
            try:
                resp = http_client.get(s_url, network="tor", params=params, headers=auth_headers, timeout=min(query.timeout, 10.0))
                if resp.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "lxml")

                    seen = set()
                    for it in soup.find_all("div", class_="result"):
                        a_tag = it.find("a")
                        if a_tag and a_tag.get("href"):
                            href = a_tag["href"].strip()
                            if ".onion" in href and href not in seen:
                                title = a_tag.get_text(strip=True) or href
                                snippet_tag = it.find("p") or it.find("div", class_="snippet")
                                snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
                                seen.add(href)
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

                    if not results:
                        for a in soup.find_all("a", href=True):
                            href = a["href"].strip()
                            if ".onion" in href and "haystak" not in href and href not in seen:
                                title = a.get_text(strip=True)
                                if title:
                                    seen.add(href)
                                    results.append(SearchResult(
                                        title=title,
                                        url=href,
                                        snippet="",
                                        engine=self.id,
                                        category="onion",
                                        network="tor"
                                    ))
                                    if len(results) >= query.limit:
                                        break
                if results:
                    break
            except Exception as e:
                hecos_logger.debug(f"[DarkHaystak] Query failed on {s_url}: {e}")

        hecos_logger.info(f"[SEARCH:HAYSTAK] Found {len(results)} results.")
        return results
