"""
search/engines/dark_torch.py
Torch & Tor-Internal Onion search engine adapter.
Queries Tor hidden service search engines via Tor SOCKS5h proxy with unmoderated results.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import List

from .base import BaseEngine
from ..models import SearchQuery, SearchResult
from .. import http_client

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.torch")
logger = hecos_logger

DEFAULT_TORCH_ONION = "http://xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion/cgi-bin/omega/omega"
DEFAULT_DDG_ONION = "https://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion/html/"


def _get_torch_urls() -> tuple[str, str]:
    """Retrieves Torch and DDG onion service endpoints from configuration."""
    from ..config import get_search_config
    cfg = get_search_config().get("endpoints", {}).get("dark_torch", {})
    ddg = cfg.get("ddg_onion") or DEFAULT_DDG_ONION
    torch = cfg.get("torch_onion") or DEFAULT_TORCH_ONION
    return ddg, torch


class DarkTorchEngine(BaseEngine):
    """Tor Internal & Torch .onion search engine."""

    def __init__(self):
        super().__init__(
            engine_id="dark_torch",
            name="Torch & Tor Hidden Search",
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

        ddg_onion, torch_onion = _get_torch_urls()

        # 1. Official DuckDuckGo Onion service (100% routed through Tor, completely unlogged, unfiltered)
        try:
            hecos_logger.info(f"[SEARCH:TORCH] Querying Tor-Internal Onion service: '{query.query}'...")
            ddg_origin = ddg_onion.rstrip("/")
            if "/html" in ddg_origin:
                ddg_origin = ddg_origin.split("/html")[0]
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0",
                "Referer": f"{ddg_origin}/",
                "Origin": ddg_origin,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            # kp="-2" disables SafeSearch content moderation
            data = {"q": query.query, "b": "", "kp": "-2" if not query.safe_search else "1"}

            resp = http_client.post(ddg_onion, network="tor", data=data, headers=headers, timeout=min(query.timeout, 18.0))
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")
                nodes = soup.find_all("div", class_="result")
                for node in nodes:
                    if len(results) >= query.limit:
                        break
                    if "result--ad" in node.get("class", []):
                        continue
                    a_tag = node.find("a", class_="result__a")
                    snip_tag = node.find("a", class_="result__snippet")
                    if a_tag:
                        raw_href = a_tag.get("href", "")
                        if "uddg=" in raw_href:
                            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                            final_url = parsed.get("uddg", [raw_href])[0]
                        else:
                            final_url = raw_href

                        title = a_tag.get_text(strip=True)
                        snippet = snip_tag.get_text(strip=True) if snip_tag else ""
                        if title and final_url:
                            results.append(SearchResult(
                                title=title,
                                url=final_url,
                                snippet=snippet,
                                engine="torch:tor",
                                category="onion",
                                network="tor"
                            ))
                if results:
                    hecos_logger.info(f"[SEARCH:TORCH] Tor-Internal Onion returned {len(results)} results")
                    return results
        except Exception as e:
            hecos_logger.debug(f"[DarkTorch] Tor Onion query note: {e}")

        # 2. Torch fallback
        try:
            params = {"P": query.query}
            resp = http_client.get(torch_onion, network="tor", params=params, timeout=min(query.timeout, 12.0))
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")
                links = [a for a in soup.find_all("a") if ".onion" in a.get("href", "")]
                for a in links[:query.limit]:
                    href = a.get("href", "")
                    title = a.get_text(strip=True)
                    if href and ".onion" in href:
                        results.append(SearchResult(
                            title=title or "Onion Service",
                            url=href,
                            snippet="Tor hidden service from Torch directory",
                            engine="torch:tor",
                            category="onion",
                            network="tor"
                        ))
        except Exception as e:
            hecos_logger.debug(f"[DarkTorch] Torch fallback error: {e}")

        return results
