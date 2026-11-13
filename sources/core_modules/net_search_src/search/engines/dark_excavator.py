"""
search/engines/dark_excavator.py
Excavator Tor onion search engine scraper.
Dedicated crawler for Excavator deep web search engine.
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
        tor_timeout = effective_tor_timeout(query.timeout, minimum=15.0)
        hecos_logger.info(f"[SEARCH:EXCAVATOR] Querying Excavator via Tor: '{query.query}' at {search_url} (timeout={tor_timeout}s)...")

        seen_urls = set()
        max_pages = 2 if query.limit > 22 else 1
        try:
            for page_num in range(1, max_pages + 1):
                if len(results) >= query.limit:
                    break
                # Excavator HTML uses name="query", support both query and q
                params = {"query": query.query, "q": query.query}
                if page_num > 1:
                    params["p"] = str(page_num)
                resp = http_client.get(search_url, network="tor", params=params, timeout=tor_timeout)
                if resp.status_code != 200:
                    break
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")

                added_this_page = 0
                is_files_mode = (getattr(query, "mode", "") or "").lower() == "files"
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    href_lower = href.lower()
                    if not href or href in seen_urls:
                        continue
                    # Exclude self-references, sponsored ad trackers, and non-onion navigation
                    if "2fd6cemt4g" in href_lower or "2fd6uvfdwh" in href_lower:
                        continue
                    if "clickid=" in href_lower or "aff_id=" in href_lower or "/ad/" in href_lower or "utm_source=excavator" in href_lower:
                        continue
                    if ".onion" not in href_lower:
                        continue

                    ad_ancestor = a.find_parent(
                        lambda tag: any(
                            tok in (" ".join(tag.get("class") or []) + " " + str(tag.get("id") or "")).lower()
                            for tok in ("sponsor", "ad-box", "adbox", "banner", "promo", "ads")
                        )
                    )
                    if ad_ancestor:
                        continue

                    title = a.get_text(strip=True)
                    if not title or title.lower() in ["advertise", "add url", "about", "terms", "next", "previous"]:
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
                        category="files" if is_files_mode else "onion",
                        network="tor"
                    ))
                    added_this_page += 1
                    if len(results) >= query.limit:
                        break
                if added_this_page == 0:
                    break

            hecos_logger.info(f"[SEARCH:EXCAVATOR] Found {len(results)} results.")
        except Exception as e:
            hecos_logger.warning(f"[SEARCH:EXCAVATOR] Query failed: {e}")

        return results
