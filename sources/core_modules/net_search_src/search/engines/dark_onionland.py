"""
search/engines/dark_onionland.py
Onion Search Engine (OSE) adapter.
Indexes Dark Web .onion sites via high-speed clearnet gateway and Tor v3 hidden service.
"""
from __future__ import annotations

import logging
from typing import List

import urllib.parse
from .base import BaseEngine, effective_tor_timeout
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

        tor_timeout = effective_tor_timeout(query.timeout, minimum=15.0)
        clear_timeout = max(float(query.timeout or 10.0), 10.0)
        max_pages = 5 if query.limit >= 30 else 2

        for url, net in endpoints:
            try:
                req_timeout = tor_timeout if net == "tor" else clear_timeout
                seen_urls = set()
                hecos_logger.info(f"[SEARCH:ONIONLAND] Querying Onion Search Engine via {net}: '{query.query}' (max_pages={max_pages})...")
                for page_num in range(1, max_pages + 1):
                    if len(results) >= query.limit:
                        break
                    page_params = dict(params)
                    if page_num > 1:
                        page_params["page"] = page_num

                    resp = http_client.get(url, network=net, params=page_params, timeout=req_timeout)
                    if resp.status_code != 200:
                        break
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "lxml")

                    added_this_page = 0
                    for a in soup.find_all("a", href=True):
                        raw_href = a["href"].strip()
                        if not raw_href:
                            continue
                        if "url=" in raw_href or "redirect=" in raw_href:
                            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                            href = parsed.get("url", parsed.get("redirect", [raw_href]))[0]
                        else:
                            href = raw_href
                        if href in seen_urls or ".onion" not in href.lower() or "report_page" in href:
                            continue

                        title = a.get_text(strip=True)
                        if not title or title.lower() in ["next", "previous", "home", "search"]:
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
                        added_this_page += 1
                        if len(results) >= query.limit:
                            break
                    if added_this_page == 0:
                        break

                if results:
                    break
            except Exception as e:
                hecos_logger.debug(f"[DarkOnionland] Query failed via {net}: {e}")

        hecos_logger.info(f"[SEARCH:ONIONLAND] Found {len(results)} results.")
        return results
