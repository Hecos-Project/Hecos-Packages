"""
search/engines/clear_searxng.py
SearXNG Meta-Search engine adapter for Hecos Deep Search.
Queries native local pure-Python SearXNG daemon (auto-starting on-demand without Docker)
and falls back to trusted public nodes for 100% resilient meta-aggregation.
"""
from __future__ import annotations

import logging
from typing import List, Set

from .base import BaseEngine
from ..models import SearchQuery, SearchResult
from ..config import get_search_config
from .. import http_client
from ..components.searxng_component import SearXNGComponent

logger = logging.getLogger("browser.search.engines.searxng")

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logger

DEFAULT_PUBLIC_FALLBACK_INSTANCES = [
    "https://search.ononoki.org",
    "https://searx.be",
    "https://baresearch.org",
    "https://priv.au",
    "https://searx.tiekoetter.com"
]


def _get_configured_searxng_nodes() -> List[Dict[str, Any]]:
    """Retrieves local and resilient fallback SearXNG instances with auth metadata from configuration."""
    cfg = get_search_config()
    endpoints = cfg.get("endpoints", {}).get("searxng", {})
    local_inst = endpoints.get("local_instance") if isinstance(endpoints.get("local_instance"), dict) else {}
    local = local_inst.get("url") or endpoints.get("local_url") or cfg.get("searxng", {}).get("url", "http://127.0.0.1:8888")
    fallbacks = endpoints.get("fallbacks", [])
    if isinstance(fallbacks, str):
        fallbacks = [fb.strip() for fb in fallbacks.split(",") if fb.strip()]
    if not fallbacks:
        fallbacks = DEFAULT_PUBLIC_FALLBACK_INSTANCES

    nodes: List[Dict[str, Any]] = [{
        "url": local.rstrip("/"),
        "use_api_key": bool(local_inst.get("use_api_key", False)),
        "api_key": str(local_inst.get("api_key", "")).strip()
    }]
    for fb in fallbacks:
        if isinstance(fb, dict):
            if fb.get("enabled", True) is False:
                continue
            u = fb.get("url")
            if not u:
                from ..config import build_endpoint_url
                u = build_endpoint_url(fb.get("protocol", "https"), fb.get("host", ""), fb.get("port", ""), fb.get("path", ""))
            use_key = bool(fb.get("use_api_key", False))
            key = str(fb.get("api_key", "")).strip()
        else:
            u = str(fb)
            use_key = False
            key = ""
        if u:
            clean = u.rstrip("/")
            if clean and not any(n["url"] == clean for n in nodes):
                nodes.append({
                    "url": clean,
                    "use_api_key": use_key,
                    "api_key": key
                })

    # Also append any custom nodes configured for searxng
    custom_nodes = cfg.get("endpoints", {}).get("custom_nodes", [])
    for cn in custom_nodes:
        if isinstance(cn, dict) and cn.get("enabled", True) is not False and cn.get("url"):
            clean_cn = cn["url"].rstrip("/")
            if clean_cn and not any(n["url"] == clean_cn for n in nodes):
                nodes.append({
                    "url": clean_cn,
                    "use_api_key": bool(cn.get("use_api_key", False)),
                    "api_key": str(cn.get("api_key", "")).strip()
                })

    return nodes


def _get_configured_searxng_urls() -> List[str]:
    """Retrieves URLs of local and resilient fallback SearXNG instances."""
    return [n["url"] for n in _get_configured_searxng_nodes()]


class ClearSearxngEngine(BaseEngine):
    """SearXNG metasearch aggregator engine (Docker-Free, Pure Python)."""

    def __init__(self):
        super().__init__(
            engine_id="clear_searxng",
            name="SearXNG Meta-Aggregator",
            category="general",
            network="clearnet",
            priority=95
        )

    def is_available(self) -> bool:
        cfg = get_search_config().get("searxng", {})
        if not cfg.get("enabled", True):
            return False
        return True

    def search(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen_urls: Set[str] = set()

        nodes_to_try = _get_configured_searxng_nodes()
        local_url = nodes_to_try[0]["url"] if nodes_to_try else "http://127.0.0.1:8888"
        comp = SearXNGComponent()

        # 1. On-Demand Invisible Auto-Start if local SearXNG is not yet active
        if "127.0.0.1" in local_url or "localhost" in local_url:
            if not comp.is_running() and comp.is_installed():
                hecos_logger.info("[SEARXNG] Local daemon is not active. Starting pure-Python SearXNG invisibly in background...")
                comp.start()

        target_limit = 100000 if (query.limit is not None and query.limit <= 0) else max(query.limit, 25)

        params = {
            "q": query.query,
            "format": "json",
            "safesearch": 0 if not query.safe_search else 1,
            "categories": "general"
        }
        if query.time_range:
            params["time_range"] = query.time_range

        for node in nodes_to_try:
            if len(results) >= target_limit:
                break
            base_url = node["url"]
            search_url = f"{base_url}/search"
            # For local node, request specific fast engines to avoid captcha
            req_params = dict(params)
            if "127.0.0.1" in base_url or "localhost" in base_url:
                req_params["engines"] = "bing,yahoo,brave,wikipedia"

            headers = {}
            if node.get("use_api_key") and node.get("api_key"):
                api_key = node["api_key"]
                headers["Authorization"] = f"Bearer {api_key}"
                headers["X-API-Key"] = api_key

            try:
                hecos_logger.info(f"[ClearSearxng] Querying SearXNG node {base_url} for '{query.query}' (Auth={'Yes' if headers else 'No'})...")
                resp = http_client.get(search_url, network="clearnet", params=req_params, headers=headers, timeout=min(query.timeout, 8.0))
                if resp.status_code == 200:
                    data = resp.json()
                    raw_results = data.get("results", [])
                    page_added = 0
                    for item in raw_results:
                        if len(results) >= target_limit:
                            break
                        title = item.get("title", "")
                        url = item.get("url", "")
                        snippet = item.get("content", "")
                        engine_source = item.get("engine", "searxng")
                        score = float(item.get("score", 1.0))
                        cat = item.get("category", "general")

                        if title and url and url not in seen_urls:
                            seen_urls.add(url)
                            results.append(SearchResult(
                                title=title,
                                url=url,
                                snippet=snippet,
                                engine=f"searxng:{engine_source}",
                                category=cat,
                                network="clearnet",
                                score=score,
                                metadata={"searx_node": base_url, "source_engine": engine_source}
                            ))
                            page_added += 1

                    if results:
                        hecos_logger.info(f"[ClearSearxng] Retrieved {len(results)} aggregated results from node {base_url}")
                        return results
            except Exception as e:
                hecos_logger.debug(f"[ClearSearxng] Query to {base_url} note: {e}")

        return results
