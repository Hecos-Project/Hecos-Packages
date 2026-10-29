"""
search/engines/media_images.py
Image search engine.
Retrieves high-resolution images, thumbnails, and origin pages with multi-page depth.
"""
from __future__ import annotations

import logging
from typing import List, Set

from .base import BaseEngine
from ..models import SearchQuery, SearchResult

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.images")
logger = hecos_logger


class MediaImagesEngine(BaseEngine):
    """Image discovery engine."""

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

    def search(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        seen_urls: Set[str] = set()
        is_unlimited = (query.limit is not None and query.limit <= 0)
        target_limit = 100000 if is_unlimited else max(query.limit, 50)
        max_pages = 25 if is_unlimited else min(25, max(4, (target_limit // 30) + 1))
        safesearch_val = "off" if not query.safe_search else "moderate"

        # 1. Multi-page DDGS Images
        try:
            from ddgs import DDGS
            ddg = DDGS(timeout=query.timeout)
            for page_num in range(1, max_pages + 1):
                if len(results) >= target_limit:
                    break
                try:
                    raw = ddg.images(query.query, page=page_num, max_results=35, safesearch=safesearch_val)
                    if not raw:
                        break
                    for item in raw:
                        title = item.get("title", "")
                        image_url = item.get("image", "")
                        thumb_url = item.get("thumbnail", "")
                        source_url = item.get("url", "") or image_url
                        w = item.get("width", 0)
                        h = item.get("height", 0)

                        if image_url and image_url not in seen_urls:
                            seen_urls.add(image_url)
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
                            if len(results) >= target_limit:
                                break
                except Exception as p_err:
                    hecos_logger.debug(f"[MediaImages] Page {page_num} note: {p_err}")
                    break
            hecos_logger.info(f"[MediaImages] DDGS retrieved {len(results)} images")
        except Exception as e:
            logger.debug(f"[MediaImages] ddgs image search: {e}")

        # 2. Wikimedia Commons API (high-resolution media fallback / enrichment)
        if len(results) < target_limit:
            try:
                import requests
                from ..config import get_search_config
                url = get_search_config().get("endpoints", {}).get("archives", {}).get("wikimedia_commons") or "https://commons.wikimedia.org/w/api.php"
                params = {
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": f"File:{query.query}",
                    "gsrlimit": min(target_limit - len(results), 25),
                    "prop": "imageinfo",
                    "iiprop": "url|dimensions|mime",
                    "format": "json"
                }
                resp = requests.get(url, params=params, headers={"User-Agent": "Hecos/1.0"}, timeout=min(query.timeout, 6.0))
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
                        if orig_url and orig_url not in seen_urls:
                            seen_urls.add(orig_url)
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
                logger.debug(f"[MediaImages] Wikimedia Commons search note: {e}")

        return results
