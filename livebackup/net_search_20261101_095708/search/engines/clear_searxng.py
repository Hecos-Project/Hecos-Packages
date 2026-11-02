"""
search/engines/clear_searxng.py
SearXNG Meta-Search engine adapter for Hecos Deep Search.
Queries native local pure-Python SearXNG daemon (auto-starting on-demand without Docker)
and falls back to trusted public nodes for 100% resilient meta-aggregation.

Engine Selection Strategy:
  - LOCAL nodes: Use `categories=` only, letting SearXNG's own settings.yml decide
    which engines run.  This unlocks all 90+ enabled engines without restriction.
  - PUBLIC fallback nodes: Also use `categories=` only since we cannot control
    their engine config anyway.
  - The Hecos engine registry (config.py → endpoints.searxng.engines) is synced
    into SearXNG's settings.yml via `update_searxng_engines()`, so SearXNG itself
    is the single source of truth for which engines are enabled.
"""
from __future__ import annotations

import logging
from typing import List, Set, Dict, Any

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
    "https://searx.be",
    "https://baresearch.org",
    "https://priv.au",
    "https://searx.tiekoetter.com",
    "https://paulgo.io",
    "https://search.sapti.me"
]

# SearXNG category mapping for Hecos search modes
MODE_TO_CATEGORIES = {
    "clear":  "general",
    "media":  "videos",
    "videos": "videos",
    "images": "images",
    "news":   "news",
    "music":  "music",
    "files":  "files",
    "it":     "it",
    "science": "science",
}


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
    """SearXNG metasearch aggregator engine (Docker-Free, Pure Python).

    Uses SearXNG `categories=` parameter instead of explicit `engines=`, allowing
    SearXNG to query ALL engines enabled in its own settings.yml.  This unlocks
    90+ engines instead of the previous 14-engine restriction.
    """

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

        cfg = get_search_config()
        is_local_only = bool(getattr(query, "local_only", None)) if getattr(query, "local_only", None) is not None else bool(cfg.get("local_only", False))

        nodes_to_try = _get_configured_searxng_nodes()
        if is_local_only:
            # Privacy Shield: Strictly restrict to local private daemons, bypass public fallback nodes
            nodes_to_try = [n for n in nodes_to_try if "127.0.0.1" in n["url"] or "localhost" in n["url"]]
            hecos_logger.info(f"[ClearSearxng:PRIVACY] Local-Only shield active: only local SearXNG nodes allowed ({len(nodes_to_try)} node)")

        local_url = nodes_to_try[0]["url"] if nodes_to_try else "http://127.0.0.1:8888"
        comp = SearXNGComponent()

        # 1. On-Demand Invisible Auto-Start if local SearXNG is not yet active
        if "127.0.0.1" in local_url or "localhost" in local_url:
            if not comp.is_running() and comp.is_installed():
                hecos_logger.info("[SEARXNG] Local daemon is not active. Starting pure-Python SearXNG invisibly in background...")
                comp.start()

        target_limit = 100000 if (query.limit is not None and query.limit <= 0) else max(query.limit, 25)

        # Resolve the SearXNG category to query based on search mode
        search_cat = MODE_TO_CATEGORIES.get(query.mode, "general")

        params = {
            "q": query.query,
            "format": "json",
            "safesearch": 0 if not query.safe_search else 1,
            "categories": search_cat
        }
        if query.time_range:
            params["time_range"] = query.time_range

        is_unlimited = (query.limit is not None and query.limit <= 0)
        max_pages = 10 if is_unlimited else min(5, max(2, (target_limit // 20) + 1))

        for node in nodes_to_try:
            if len(results) >= target_limit:
                break
            base_url = node["url"]
            search_url = f"{base_url}/search"
            headers = {}
            if node.get("use_api_key") and node.get("api_key"):
                api_key = node["api_key"]
                headers["Authorization"] = f"Bearer {api_key}"
                headers["X-API-Key"] = api_key

            node_yielded = 0
            for page in range(1, max_pages + 1):
                if len(results) >= target_limit:
                    break
                req_params = dict(params)
                if page > 1:
                    req_params["pageno"] = page

                # NOTE: We do NOT pass `engines=` parameter anymore.
                # SearXNG uses its own settings.yml (synced via Engine Registry)
                # to determine which engines run per category.  This unlocks all
                # 90+ enabled engines instead of the previous hardcoded 14.

                try:
                    hecos_logger.info(f"[ClearSearxng] Querying SearXNG node {base_url} (page={page}, cat={search_cat}, mode=all_enabled_engines) for '{query.query}'...")
                    resp = http_client.get(search_url, network="clearnet", params=req_params, headers=headers, timeout=min(query.timeout, 10.0))
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_results = data.get("results", [])
                        if not raw_results:
                            break
                        page_added = 0
                        for item in raw_results:
                            if len(results) >= target_limit:
                                break
                            title = item.get("title", "")
                            url = item.get("url", "")
                            snippet = item.get("content", "")
                            engine_source = item.get("engine", "searxng")
                            score = float(item.get("score", 1.0))
                            cat = item.get("category", search_cat)
                            thumb = item.get("thumbnail") or item.get("img_src") or item.get("thumbnail_src")

                            meta = {
                                "searx_node": base_url,
                                "source_engine": engine_source,
                                "publisher": item.get("author") or engine_source
                            }
                            if item.get("length"):
                                meta["duration"] = str(item["length"])
                            elif item.get("duration"):
                                meta["duration"] = str(item["duration"])

                            if title and url and url not in seen_urls:
                                seen_urls.add(url)
                                results.append(SearchResult(
                                    title=title,
                                    url=url,
                                    snippet=snippet,
                                    engine=f"searxng:{engine_source}",
                                    engine_id="clear_searxng",
                                    category=cat,
                                    network="clearnet",
                                    score=score,
                                    thumbnail_url=thumb,
                                    metadata=meta
                                ))
                                page_added += 1
                                node_yielded += 1

                        if page_added == 0:
                            break
                except Exception as e:
                    hecos_logger.debug(f"[ClearSearxng] Query to {base_url} page {page} note: {e}")
                    break

            if node_yielded > 0:
                hecos_logger.info(f"[ClearSearxng] Retrieved {node_yielded} aggregated results across pages from node {base_url}")
                return results

        return results
