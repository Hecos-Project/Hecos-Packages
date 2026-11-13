"""
search/engines/dark_torch.py
Torch & Tor-Internal Onion search engine adapter.
Queries Tor hidden service search engines via Tor SOCKS5h proxy with unmoderated results.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import List

from .base import BaseEngine, effective_tor_timeout
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
        tor_timeout = effective_tor_timeout(query.timeout, minimum=15.0)
        seen_urls = set()

        # 1. Torch Hidden Service (.onion index first so Dark Web returns pure .onion hits)
        try:
            hecos_logger.info(f"[SEARCH:TORCH] Querying Torch Onion service: '{query.query}' (timeout={tor_timeout}s)...")
            params = {"P": query.query}
            resp = http_client.get(torch_onion, network="tor", params=params, timeout=tor_timeout)
            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "lxml")
                links = [a for a in soup.find_all("a", href=True) if ".onion" in a.get("href", "").lower()]
                for a in links:
                    href = a.get("href", "").strip()
                    if not href or href in seen_urls or "xmh57jrknzkhv6y" in href:
                        continue
                    title = a.get_text(strip=True)
                    if not title or len(title) < 2:
                        continue
                    seen_urls.add(href)
                    results.append(SearchResult(
                        title=title,
                        url=href,
                        snippet="Tor hidden service from Torch directory",
                        engine="torch:tor",
                        category="onion",
                        network="tor"
                    ))
                    if len(results) >= query.limit:
                        break
        except Exception as e:
            hecos_logger.debug(f"[DarkTorch] Torch onion query error: {e}")

        # 2. DuckDuckGo Onion service as supplementary unlogged Tor search
        if len(results) < query.limit:
            try:
                hecos_logger.info(f"[SEARCH:TORCH] Querying DDG Onion service: '{query.query}'...")
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

                resp = http_client.post(ddg_onion, network="tor", data=data, headers=headers, timeout=tor_timeout)
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
                            if title and final_url and final_url not in seen_urls:
                                seen_urls.add(final_url)
                                results.append(SearchResult(
                                    title=title,
                                    url=final_url,
                                    snippet=snippet,
                                    engine="ddg:tor",
                                    category="onion",
                                    network="tor"
                                ))
            except Exception as e:
                hecos_logger.debug(f"[DarkTorch] DDG Onion query note: {e}")

        hecos_logger.info(f"[SEARCH:TORCH] Found {len(results)} total results")
        return results
