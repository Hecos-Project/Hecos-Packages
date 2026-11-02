"""
search/engines/media_images.py
Image search engine.
Retrieves high-resolution images, thumbnails, and origin pages with multi-source parallel discovery.
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Dict, Any

from .base import BaseEngine
from ..models import SearchQuery, SearchResult

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.images")
logger = hecos_logger


def _normalize_explicit_query(raw_query: str) -> str:
    """Expands Italian negative phrases (e.g. 'senza vestiti') into explicit keywords for international engines."""
    q = raw_query.lower()
    replacements = [
        (r"\bsenza\s+vestiti\b", "nude naked"),
        (r"\bsenza\s+veli\b", "nude"),
        (r"\bsenza\s+abiti\b", "nude naked"),
        (r"\bsenza\s+mutande\b", "nude"),
        (r"\bdonne\s+incinte\b", "pregnant women"),
        (r"\bdonna\s+incinta\b", "pregnant woman"),
        (r"\bincinte\b", "pregnant"),
        (r"\bincinta\b", "pregnant"),
        (r"\bnuda\b", "nude"),
        (r"\bnude\b", "nude"),
        (r"\bnudi\b", "nude"),
        (r"\bspogliata\b", "naked"),
    ]
    augmented = q
    for pat, rep in replacements:
        augmented = re.sub(pat, rep, augmented)
    augmented = re.sub(r"\b(e|ed|di|con)\b", " ", augmented)
    augmented = " ".join(augmented.split())
    return augmented.strip()


class MediaImagesEngine(BaseEngine):
    """Image discovery engine with parallel multi-source aggregation and anti-bias fallback."""

    def __init__(self):
        super().__init__(
            engine_id="media_images",
            name="Image Discovery",
            category="images",
            network="clearnet",
            priority=80
        )

    def is_available(self) -> bool:
        return True

    def _fetch_ddgs(self, query_str: str, target_count: int, timeout: float, safe_search: bool) -> List[SearchResult]:
        results: List[SearchResult] = []
        try:
            from ddgs import DDGS
            ddg = DDGS(timeout=timeout)
            safesearch_val = "moderate" if safe_search else "off"
            pages = max(2, min(10, (target_count // 30) + 1))
            for page_num in range(1, pages + 1):
                try:
                    raw = ddg.images(query_str, page=page_num, max_results=35, safesearch=safesearch_val)
                    if not raw:
                        break
                    for item in raw:
                        title = item.get("title", "")
                        image_url = item.get("image", "")
                        thumb_url = item.get("thumbnail", "")
                        source_url = item.get("url", "") or image_url
                        w = item.get("width", 0)
                        h = item.get("height", 0)
                        if image_url:
                            results.append(SearchResult(
                                title=title or "Image Result",
                                url=source_url,
                                snippet=f"Image ({w}x{h}) from {item.get('source', '')}",
                                engine="ddgs:images",
                                category="images",
                                network="clearnet",
                                media_url=image_url,
                                thumbnail_url=thumb_url or image_url,
                                metadata={"width": w, "height": h}
                            ))
                            if len(results) >= target_count:
                                break
                except Exception as pe:
                    logger.debug(f"[MediaImages:DDGS] Page {page_num} note: {pe}")
                    break
        except Exception as e:
            logger.debug(f"[MediaImages:DDGS] error: {e}")
        return results

    def _fetch_searxng(self, query_str: str, target_count: int, timeout: float, safe_search: bool) -> List[SearchResult]:
        results: List[SearchResult] = []
        try:
            import requests
            from ..config import get_search_config
            from ..components.searxng_component import SearXNGComponent
            comp = SearXNGComponent()
            if not comp.is_running() and comp.is_installed():
                comp.start()

            cfg = get_search_config()
            searx_cfg = cfg.get("endpoints", {}).get("searxng", {})
            local_url = searx_cfg.get("local_instance", {}).get("url") or "http://127.0.0.1:8888"

            resp = requests.get(
                f"{local_url.rstrip('/')}/search",
                params={
                    "q": query_str,
                    "categories": "images",
                    "format": "json",
                    "safesearch": 0 if not safe_search else 1
                },
                timeout=min(timeout, 6.0)
            )
            if resp.status_code == 200:
                raw_images = resp.json().get("results", [])
                for item in raw_images:
                    img_url = item.get("img_src") or item.get("url", "")
                    source_page = item.get("url") or img_url
                    thumb = item.get("thumbnail_src") or item.get("thumbnail") or img_url
                    title = item.get("title", "") or "Image Result"
                    eng = item.get("engine", "searxng_images")
                    w = item.get("width", 0)
                    h = item.get("height", 0)
                    if img_url:
                        results.append(SearchResult(
                            title=title,
                            url=source_page,
                            snippet=f"Image ({w}x{h}) via {eng}",
                            engine=f"searxng:{eng}",
                            category="images",
                            network="clearnet",
                            media_url=img_url,
                            thumbnail_url=thumb,
                            metadata={"width": w, "height": h, "source_engine": eng}
                        ))
                        if len(results) >= target_count:
                            break
        except Exception as e:
            logger.debug(f"[MediaImages:SearXNG] error: {e}")
        return results

    def _fetch_wikimedia(self, query_str: str, target_count: int, timeout: float) -> List[SearchResult]:
        results: List[SearchResult] = []
        try:
            import requests
            from ..config import get_search_config
            url = get_search_config().get("endpoints", {}).get("archives", {}).get("wikimedia_commons") or "https://commons.wikimedia.org/w/api.php"
            params = {
                "action": "query",
                "generator": "search",
                "gsrsearch": f"File:{query_str}",
                "gsrlimit": min(target_count, 30),
                "prop": "imageinfo",
                "iiprop": "url|dimensions|mime",
                "format": "json"
            }
            resp = requests.get(url, params=params, headers={"User-Agent": "Hecos/1.0"}, timeout=min(timeout, 6.0))
            if resp.status_code == 200:
                pages = resp.json().get("query", {}).get("pages", {})
                for page_id, info in pages.items():
                    title = info.get("title", "").replace("File:", "")
                    imginfo = info.get("imageinfo", [{}])[0]
                    orig_url = imginfo.get("url")
                    thumb = imginfo.get("thumburl") or orig_url
                    desc_url = imginfo.get("descriptionurl") or orig_url
                    w = imginfo.get("width", 0)
                    h = imginfo.get("height", 0)
                    if orig_url:
                        results.append(SearchResult(
                            title=title,
                            url=desc_url,
                            snippet=f"Wikimedia Commons ({w}x{h})",
                            engine="commons:image",
                            category="images",
                            network="clearnet",
                            media_url=orig_url,
                            thumbnail_url=thumb,
                            metadata={"width": w, "height": h}
                        ))
        except Exception as e:
            logger.debug(f"[MediaImages:Wikimedia] error: {e}")
        return results

    def search(self, query: SearchQuery) -> List[SearchResult]:
        is_unlimited = (query.limit is not None and query.limit <= 0)
        target_limit = 100000 if is_unlimited else max(query.limit or 250, 250)
        per_provider = max(50, target_limit // 3)

        tasks = []
        # Task 1: SearXNG Images (local daemon with Yandex, Google, Bing, etc.)
        tasks.append(lambda: self._fetch_searxng(query.query, per_provider, query.timeout, safe_search=query.safe_search))

        # Task 2: DDGS Images
        tasks.append(lambda: self._fetch_ddgs(query.query, per_provider, query.timeout, safe_search=query.safe_search))

        # Task 3: If safe_search is False and query contains Italian explicit indicators, also query normalized tokens
        if not query.safe_search:
            normalized_q = _normalize_explicit_query(query.query)
            if normalized_q != query.query.lower().strip():
                tasks.append(lambda: self._fetch_searxng(normalized_q, per_provider, query.timeout, safe_search=False))

        # Task 4: Wikimedia Commons
        tasks.append(lambda: self._fetch_wikimedia(query.query, min(per_provider, 25), query.timeout))

        all_provider_results: List[List[SearchResult]] = []
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = [pool.submit(t) for t in tasks]
            for fut in as_completed(futures):
                try:
                    res = fut.result()
                    if res:
                        all_provider_results.append(res)
                except Exception as e:
                    logger.debug(f"[MediaImages] Provider task error: {e}")

        # Balanced round-robin interleaving
        final_results: List[SearchResult] = []
        seen_urls: Set[str] = set()

        max_len = max((len(r) for r in all_provider_results), default=0)
        for i in range(max_len):
            for provider_list in all_provider_results:
                if i < len(provider_list):
                    item = provider_list[i]
                    if item.url not in seen_urls and item.media_url not in seen_urls:
                        seen_urls.add(item.url)
                        if item.media_url:
                            seen_urls.add(item.media_url)
                        final_results.append(item)
                        if len(final_results) >= target_limit:
                            break
            if len(final_results) >= target_limit:
                break

        logger.info(f"[MediaImages] Retrieved {len(final_results)} images across {len(all_provider_results)} parallel providers for '{query.query}'")
        return final_results
