"""
search/engines/dark_custom.py
Custom user-defined Tor onion search engines runner.
Dynamically executes searches on user-configured .onion search engines via Tor SOCKS5h.
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
    hecos_logger = logging.getLogger("browser.search.engines.custom_onion")
logger = hecos_logger


class DarkCustomEngine(BaseEngine):
    """Dynamic runner for user-configured custom .onion search engines."""

    def __init__(self):
        super().__init__(
            engine_id="dark_custom",
            name="Custom Onion Engines",
            category="onion",
            network="tor",
            priority=75
        )

    def is_available(self) -> bool:
        from ..config import get_search_config
        cfg = get_search_config()
        if not cfg.get("tor", {}).get("enabled", False):
            return False
        custom_engines = cfg.get("endpoints", {}).get("custom_onion_engines", [])
        return http_client.is_tor_online() and len(custom_engines) > 0

    def search(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        if not self.is_available():
            return results

        from ..config import get_search_config
        custom_engines = get_search_config().get("endpoints", {}).get("custom_onion_engines", [])
        if not custom_engines:
            return results

        for eng_cfg in custom_engines:
            if not eng_cfg.get("enabled", True):
                continue

            eng_name = eng_cfg.get("name", "Custom Onion")
            raw_url = eng_cfg.get("onion_url", "").strip() or eng_cfg.get("url", "").strip()
            if not raw_url and eng_cfg.get("host"):
                from ..config import build_endpoint_url
                raw_url = build_endpoint_url(
                    eng_cfg.get("protocol", "http"),
                    eng_cfg.get("host", ""),
                    eng_cfg.get("port", ""),
                    eng_cfg.get("path", "")
                )
            template = eng_cfg.get("search_template", "").strip()

            if not raw_url and not template:
                continue

            # Determine query URL
            import urllib.parse
            encoded_q = urllib.parse.quote_plus(query.query)
            if template and "{q}" in template:
                target_url = template.replace("{q}", encoded_q)
            elif template:
                target_url = f"{template}?q={encoded_q}"
            elif raw_url:
                target_url = f"{raw_url.rstrip('/')}/search?q={encoded_q}"
            else:
                continue

            headers = {}
            if eng_cfg.get("use_api_key") and eng_cfg.get("api_key"):
                key_val = str(eng_cfg.get("api_key", "")).strip()
                if key_val:
                    headers["Authorization"] = f"Bearer {key_val}"
                    headers["X-API-Key"] = key_val

            hecos_logger.info(f"[SEARCH:CUSTOM_ONION] Querying '{eng_name}' at {target_url} (Auth={'Yes' if headers else 'No'})...")

            try:
                resp = http_client.get(target_url, network="tor", headers=headers, timeout=query.timeout)
                if resp.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "lxml")

                    # Heuristic result extraction
                    count_before = len(results)
                    items = soup.find_all(["div", "li", "article"], class_=lambda c: c and any(k in str(c).lower() for k in ["result", "item", "search"]))
                    for it in items[:query.limit]:
                        a_tag = it.find("a")
                        if a_tag:
                            href = a_tag.get("href", "")
                            title = a_tag.get_text(strip=True)
                            p_tag = it.find(["p", "span", "div"], class_=lambda c: c and any(k in str(c).lower() for k in ["snippet", "desc"]))
                            snippet = p_tag.get_text(strip=True) if p_tag else ""

                            if href and (".onion" in href or href.startswith("http")):
                                results.append(SearchResult(
                                    url=href,
                                    title=title or href,
                                    snippet=snippet,
                                    engine=f"dark_{eng_name.lower().replace(' ', '_')}",
                                    category="onion",
                                    network="tor"
                                ))

                    # Fallback to direct .onion links
                    if len(results) == count_before:
                        for a in soup.find_all("a", href=True):
                            href = a["href"]
                            if ".onion" in href and not href.startswith("#"):
                                txt = a.get_text(strip=True)
                                if txt and len(txt) > 3:
                                    results.append(SearchResult(
                                        url=href,
                                        title=txt,
                                        snippet="",
                                        engine=f"dark_{eng_name.lower().replace(' ', '_')}",
                                        category="onion",
                                        network="tor"
                                    ))
                                    if len(results) >= query.limit * 2:
                                        break
            except Exception as e:
                hecos_logger.warning(f"[SEARCH:CUSTOM_ONION] Engine '{eng_name}' query failed: {e}")

        return results
