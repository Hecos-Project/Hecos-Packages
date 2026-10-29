"""
search/engines/media_videos.py
Video search engine supporting YouTube and multi-platform media.
Uses ddgs video search and yt-dlp ytsearch queries.
"""
from __future__ import annotations

import json
import shutil
import logging
import subprocess
from typing import List

from .base import BaseEngine
from ..models import SearchQuery, SearchResult

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.videos")
logger = hecos_logger


class MediaVideosEngine(BaseEngine):
    """Video search and discovery engine."""

    def __init__(self):
        super().__init__(
            engine_id="media_videos",
            name="Video Search & Streams",
            category="videos",
            network="clearnet",
            priority=80
        )

    def is_available(self) -> bool:
        import importlib.util
        return (importlib.util.find_spec("ddgs") is not None) or (importlib.util.find_spec("yt_dlp") is not None)

    def search(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        is_unlimited = (query.limit is not None and query.limit <= 0)
        target_limit = 200 if is_unlimited else max(query.limit, 40)

        # 1. Try yt_dlp Python module directly (extremely fast and reliable for video streams)
        try:
            import yt_dlp
            ydl_opts = {
                "extract_flat": True,
                "skip_download": True,
                "quiet": True,
                "no_warnings": True,
                "playlistend": target_limit,
                "socket_timeout": min(query.timeout, 10.0)
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                res = ydl.extract_info(f"ytsearch{target_limit}:{query.query}", download=False)
                entries = res.get("entries", []) if res else []
                for info in entries:
                    if not info:
                        continue
                    v_title = info.get("title", "")
                    v_id = info.get("id", "")
                    v_url = info.get("url") or (f"https://www.youtube.com/watch?v={v_id}" if v_id else "")
                    v_uploader = info.get("uploader") or info.get("channel", "")
                    v_dur = info.get("duration_string", "") or ""
                    thumbnails = info.get("thumbnails", [])
                    v_thumb = thumbnails[-1].get("url") if thumbnails else (f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg" if v_id else "")

                    if v_title and v_url:
                        results.append(SearchResult(
                            title=v_title,
                            url=v_url,
                            snippet=f"Channel: {v_uploader} | Duration: {v_dur}" if v_dur else f"Channel: {v_uploader}",
                            engine="youtube",
                            category="videos",
                            network="clearnet",
                            media_url=v_url,
                            thumbnail_url=v_thumb,
                            metadata={"uploader": v_uploader, "duration": v_dur}
                        ))
            if results:
                logger.info(f"[MediaVideos] yt_dlp returned {len(results)} videos")
                return results
        except Exception as e:
            logger.debug(f"[MediaVideos] yt_dlp module search: {e}")

        # 2. Try ddgs videos
        try:
            from ddgs import DDGS
            safesearch_val = "off" if not query.safe_search else "moderate"
            ddg = DDGS(timeout=query.timeout)
            raw = ddg.videos(query.query, max_results=query.limit, safesearch=safesearch_val)

            for item in raw:
                title = item.get("title", "")
                content_url = item.get("content", "") or item.get("url", "")
                desc = item.get("description", "")
                dur = item.get("duration", "")
                thumb = item.get("images", {}).get("medium", "") or item.get("images", {}).get("small", "")
                publisher = item.get("publisher", "")

                if title and content_url:
                    results.append(SearchResult(
                        title=title,
                        url=content_url,
                        snippet=f"[{publisher}] {desc} (Duration: {dur})" if dur else desc,
                        engine="ddgs:videos",
                        category="videos",
                        network="clearnet",
                        media_url=content_url,
                        thumbnail_url=thumb,
                        metadata={"duration": dur, "publisher": publisher}
                    ))
            if results:
                return results
        except Exception as e:
            logger.debug(f"[MediaVideos] ddgs videos query: {e}")

        # 3. Try Archive.org video API as open fallback
        try:
            import requests
            from ..config import get_search_config
            url = get_search_config().get("endpoints", {}).get("archives", {}).get("archive_org") or "https://archive.org/advancedsearch.php"
            params = {
                "q": f"{query.query} mediatype:movies",
                "fl[]": "identifier,title,description",
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
                    if isinstance(desc, list):
                        desc = " ".join(desc)
                    if ident:
                        page_url = f"https://archive.org/details/{ident}"
                        results.append(SearchResult(
                            title=title,
                            url=page_url,
                            snippet=desc[:160] if desc else f"Archive.org Video: {ident}",
                            engine="archive_org:video",
                            category="videos",
                            network="clearnet",
                            media_url=page_url,
                            thumbnail_url=f"https://archive.org/services/img/{ident}",
                            metadata={"identifier": ident}
                        ))
        except Exception as e:
            logger.debug(f"[MediaVideos] Archive.org fallback: {e}")

        return results
