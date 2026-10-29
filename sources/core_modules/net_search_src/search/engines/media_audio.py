"""
search/engines/media_audio.py
Audio and music search engine.
Discovers podcasts, songs, and voice tracks from audio platforms.
"""
from __future__ import annotations

import logging
from typing import List

from .base import BaseEngine
from ..models import SearchQuery, SearchResult

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.audio")
logger = hecos_logger


class MediaAudioEngine(BaseEngine):
    """Audio and soundtrack discovery engine."""

    def __init__(self):
        super().__init__(
            engine_id="media_audio",
            name="Audio & Podcasts",
            category="audio",
            network="clearnet",
            priority=75
        )

    def is_available(self) -> bool:
        return True

    def search(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        audio_query = f"{query.query} (site:soundcloud.com OR site:archive.org/details/audio OR site:bandcamp.com OR podcast)"

        # 1. DDGS Audio Aggregation
        try:
            from ddgs import DDGS
            ddg = DDGS(timeout=query.timeout)
            raw = ddg.text(audio_query, max_results=query.limit)
            for item in raw:
                title = item.get("title", "")
                url = item.get("href", "") or item.get("url", "")
                body = item.get("body", "")
                if title and url:
                    results.append(SearchResult(
                        title=title,
                        url=url,
                        snippet=body,
                        engine="audio_aggregator",
                        category="audio",
                        network="clearnet",
                        media_url=url
                    ))
            if results:
                return results
        except Exception as e:
            logger.debug(f"[MediaAudio] Audio search failed: {e}")

        # 2. Archive.org Open Audio & Podcast Library fallback
        try:
            import requests
            from ..config import get_search_config
            url = get_search_config().get("endpoints", {}).get("archives", {}).get("archive_org") or "https://archive.org/advancedsearch.php"
            params = {
                "q": f"{query.query} mediatype:audio",
                "fl[]": "identifier,title,description,creator",
                "rows": query.limit,
                "output": "json"
            }
            resp = requests.get(url, params=params, headers={"User-Agent": "Hecos/1.0"}, timeout=min(query.timeout, 5.0))
            if resp.status_code == 200:
                docs = resp.json().get("response", {}).get("docs", [])
                for d in docs:
                    ident = d.get("identifier", "")
                    title = d.get("title", "") or ident
                    desc = d.get("description", "")
                    creator = d.get("creator", "Audio Track")
                    if isinstance(desc, list):
                        desc = " ".join(desc)
                    if isinstance(creator, list):
                        creator = ", ".join(creator)
                    if ident:
                        page_url = f"https://archive.org/details/{ident}"
                        results.append(SearchResult(
                            title=title,
                            url=page_url,
                            snippet=desc[:160] if desc else f"Audio by {creator}",
                            engine="archive_org:audio",
                            category="audio",
                            network="clearnet",
                            media_url=page_url,
                            metadata={"creator": creator, "identifier": ident}
                        ))
        except Exception as e:
            logger.debug(f"[MediaAudio] Archive.org fallback: {e}")

        return results
