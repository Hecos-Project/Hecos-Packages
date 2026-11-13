"""
search/engines/media_videos.py
Multi-Platform Video Discovery & Stream Aggregator.
Aggregates video streams across YouTube, Dailymotion, PeerTube (SepiaSearch),
SearXNG Video nodes, Vimeo, the Internet Archive, and configured media stream slots.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Dict, Any

from .base import BaseEngine
from ..models import SearchQuery, SearchResult
from ..config import get_search_config

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.videos")
logger = hecos_logger


def _normalize_explicit_query(raw_query: str) -> str:
    """Expands Italian negative/explicit phrases into English keywords for international video tube APIs."""
    q = raw_query.lower()
    replacements = [
        (r"\bsenza\s+vestiti\b", "nude"),
        (r"\bsenza\s+veli\b", "nude"),
        (r"\bsenza\s+abiti\b", "nude"),
        (r"\bsenza\s+mutande\b", "nude"),
        (r"\bdonne\s+incinte\b", "pregnant"),
        (r"\bdonna\s+incinta\b", "pregnant"),
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


class MediaVideosEngine(BaseEngine):
    """Multi-platform video discovery engine."""

    def __init__(self):
        super().__init__(
            engine_id="media_videos",
            name="Multi-Platform Video Aggregator (YouTube / Dailymotion / PeerTube / Streams / Archive)",
            category="videos",
            network="clearnet",
            priority=85
        )

    def is_available(self) -> bool:
        return True

    def _fetch_dailymotion(self, query: str, limit: int, timeout: float, safe_search: bool = False, page: int = 1) -> List[SearchResult]:
        """Queries Dailymotion official REST API."""
        results: List[SearchResult] = []
        try:
            q_enc = urllib.parse.quote_plus(query)
            target = min(limit, 30)
            family_filter = "true" if safe_search else "false"
            url = (
                f"https://api.dailymotion.com/videos"
                f"?search={q_enc}&limit={target}&family_filter={family_filter}&page={max(1, page)}"
                f"&fields=id,title,url,thumbnail_720_url,thumbnail_480_url,duration,owner.screenname,views_total"
            )
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=min(timeout, 5.0)) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                items = data.get("list", [])
                for it in items:
                    v_id = it.get("id")
                    title = it.get("title")
                    v_url = it.get("url") or (f"https://www.dailymotion.com/video/{v_id}" if v_id else "")
                    thumb = it.get("thumbnail_720_url") or it.get("thumbnail_480_url") or ""
                    sec = it.get("duration", 0)
                    m = sec // 60
                    s = sec % 60
                    dur_str = f"{m}:{s:02d}" if sec else ""
                    uploader = it.get("owner.screenname") or "Dailymotion"
                    views = it.get("views_total")
                    snippet = f"Channel: {uploader}"
                    if dur_str:
                        snippet += f" | Duration: {dur_str}"
                    if views:
                        snippet += f" | Views: {views:,}"

                    if title and v_url:
                        results.append(SearchResult(
                            title=title,
                            url=v_url,
                            snippet=snippet,
                            engine="dailymotion",
                            category="videos",
                            network="clearnet",
                            media_url=v_url,
                            thumbnail_url=thumb,
                            metadata={"uploader": uploader, "duration": dur_str, "views": views, "platform": "dailymotion"}
                        ))
        except Exception as e:
            logger.debug(f"[MediaVideos:Dailymotion] Query note: {e}")
        return results

    def _fetch_peertube(self, query: str, limit: int, timeout: float, safe_search: bool = False, page: int = 1) -> List[SearchResult]:
        """Queries decentralized PeerTube SepiaSearch API."""
        results: List[SearchResult] = []
        try:
            q_enc = urllib.parse.quote_plus(query)
            target = min(limit, 25)
            start_offset = max(0, (max(1, page) - 1) * target)
            sensitive_param = "&sensitive=true" if not safe_search else "&sensitive=false"
            url = f"https://sepiasearch.org/api/v1/search/videos?search={q_enc}&count={target}&start={start_offset}{sensitive_param}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=min(timeout, 5.0)) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                items = data.get("data", [])
                for it in items:
                    title = it.get("name")
                    v_url = it.get("url")
                    thumb_path = it.get("thumbnailPath")
                    origin = it.get("account", {}).get("host") or ""
                    thumb = f"https://{origin}{thumb_path}" if (thumb_path and origin and thumb_path.startswith("/")) else (thumb_path or "")
                    sec = it.get("duration", 0)
                    dur_str = f"{sec // 60}:{sec % 60:02d}" if sec else ""
                    uploader = it.get("channel", {}).get("displayName") or it.get("account", {}).get("displayName") or "PeerTube"
                    views = it.get("views")
                    snippet = f"PeerTube ({origin}) | Channel: {uploader}"
                    if dur_str:
                        snippet += f" | {dur_str}"

                    if title and v_url:
                        results.append(SearchResult(
                            title=title,
                            url=v_url,
                            snippet=snippet,
                            engine="peertube",
                            category="videos",
                            network="clearnet",
                            media_url=v_url,
                            thumbnail_url=thumb,
                            metadata={"uploader": uploader, "duration": dur_str, "views": views, "platform": "peertube"}
                        ))
        except Exception as e:
            logger.debug(f"[MediaVideos:PeerTube] Query note: {e}")
        return results

    def _fetch_eporner(self, query: str, limit: int, timeout: float, endpoint_url: str = "", page: int = 1) -> List[SearchResult]:
        """Queries Eporner public REST API (Active when Content Filter is OFF)."""
        results: List[SearchResult] = []
        try:
            base_url = endpoint_url or "https://www.eporner.com/api/v2/video/search/"
            norm_q = _normalize_explicit_query(query)
            target_total = min(max(limit, 50), 120)
            per_page = min(target_total, 50)
            max_pages = 3 if target_total > 50 else 1
            start_page = (max(1, page) - 1) * max_pages + 1
            seen_ep: Set[str] = set()
            t_start = time.time()
            def _run_eporner_pages(q_str: str) -> None:
                for p in range(start_page, start_page + max_pages):
                    if len(results) >= target_total or (time.time() - t_start) > min(timeout, 6.0):
                        break
                    url = f"{base_url.rstrip('/')}/?query={urllib.parse.quote_plus(q_str)}&per_page={per_page}&page={p}&thumbsize=medium"
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                    with urllib.request.urlopen(req, timeout=min(timeout, 5.0)) as resp:
                        data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                        videos = data.get("videos", [])
                        if not videos:
                            break
                        for v in videos:
                            title = v.get("title")
                            v_url = v.get("url")
                            thumb = v.get("default_thumb", {}).get("src") or ""
                            views = v.get("views")
                            dur_str = v.get("length_min") or ""
                            snippet = "Stream: Eporner"
                            if dur_str:
                                snippet += f" | Duration: {dur_str} min"
                            if views:
                                snippet += f" | Views: {views:,}"

                            if title and v_url and v_url not in seen_ep:
                                seen_ep.add(v_url)
                                results.append(SearchResult(
                                    title=title,
                                    url=v_url,
                                    snippet=snippet,
                                    engine="eporner:stream",
                                    category="videos",
                                    network="clearnet",
                                    media_url=v_url,
                                    thumbnail_url=thumb,
                                    metadata={"duration": dur_str, "views": views, "platform": "eporner"}
                                ))

            _run_eporner_pages(norm_q)
            if len(results) < 10:
                words = [w for w in norm_q.split() if len(w) >= 3]
                trimmed = [w for w in words if w.lower() not in ("woman", "women", "girl", "girls", "man", "men", "video", "videos", "free", "full")]
                relaxed_q = " ".join((trimmed or words)[:2])
                if relaxed_q and relaxed_q != norm_q and (time.time() - t_start) < min(timeout, 5.5):
                    _run_eporner_pages(relaxed_q)
            hecos_logger.info(f"[MediaVideos:Eporner] Retrieved {len(results)} videos for '{norm_q}'")
        except Exception as e:
            logger.debug(f"[MediaVideos:Eporner] query error: {e}")
        return results

    def _fetch_redtube(self, query: str, limit: int, timeout: float, endpoint_url: str = "", page: int = 1) -> List[SearchResult]:
        """Queries RedTube public REST API (Active when Content Filter is OFF)."""
        results: List[SearchResult] = []
        try:
            base_url = endpoint_url or "https://api.redtube.com/"
            norm_q = _normalize_explicit_query(query)
            target_total = min(max(limit, 40), 100)
            max_pages = 3 if target_total > 40 else 1
            start_page = (max(1, page) - 1) * max_pages + 1
            seen_rt: Set[str] = set()
            t_start = time.time()
            for p in range(start_page, start_page + max_pages):
                if len(results) >= target_total or (time.time() - t_start) > min(timeout, 6.0):
                    break
                params = {
                    "data": "redtube.Videos.searchVideos",
                    "output": "json",
                    "search": norm_q,
                    "page": str(p),
                    "thumbsize": "medium"
                }
                url = f"{base_url.rstrip('/')}/?{urllib.parse.urlencode(params)}"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                with urllib.request.urlopen(req, timeout=min(timeout, 5.0)) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    videos = data.get("videos", [])
                    if not videos:
                        break
                    for item in videos:
                        v = item.get("video", {})
                        title = v.get("title")
                        v_url = v.get("url")
                        thumb = v.get("default_thumb") or ""
                        dur = v.get("duration") or ""
                        views = v.get("views")
                        snippet = "Stream: RedTube"
                        if dur:
                            snippet += f" | Duration: {dur}"
                        if views:
                            snippet += f" | Views: {views:,}"

                        if title and v_url and v_url not in seen_rt:
                            seen_rt.add(v_url)
                            results.append(SearchResult(
                                title=title,
                                url=v_url,
                                snippet=snippet,
                                engine="redtube:stream",
                                category="videos",
                                network="clearnet",
                                media_url=v_url,
                                thumbnail_url=thumb,
                                metadata={"duration": dur, "views": views, "platform": "redtube"}
                            ))
            hecos_logger.info(f"[MediaVideos:RedTube] Retrieved {len(results)} videos for '{norm_q}'")
        except Exception as e:
            logger.debug(f"[MediaVideos:RedTube] query error: {e}")
        return results

    def _fetch_searxng_videos(self, query: str, limit: int, timeout: float, safe_search: bool = False, page: int = 1) -> List[SearchResult]:
        """Queries local or fallback SearXNG instances specifically for video meta-search."""
        results: List[SearchResult] = []
        try:
            from ..components.searxng_component import SearXNGComponent
            comp = SearXNGComponent()
            if not comp.is_running() and comp.is_installed():
                comp.start()

            from .clear_searxng import _get_configured_searxng_nodes
            nodes = _get_configured_searxng_nodes()
            if not nodes:
                nodes = [{"url": "http://127.0.0.1:8889", "use_api_key": False, "api_key": ""}]

            params = {
                "q": query,
                "categories": "videos",
                "format": "json",
                "safesearch": 0 if not safe_search else 1,
                "pageno": max(1, page)
            }
            for node in nodes[:2]:
                base_url = node["url"]
                search_url = f"{base_url}/search"
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                if node.get("use_api_key") and node.get("api_key"):
                    headers["Authorization"] = f"Bearer {node['api_key']}"

                try:
                    req = urllib.request.Request(f"{search_url}?{urllib.parse.urlencode(params)}", headers=headers)
                    with urllib.request.urlopen(req, timeout=min(timeout, 5.0)) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                            for item in data.get("results", []):
                                title = item.get("title")
                                url = item.get("url")
                                eng = item.get("engine", "searxng_video")
                                thumb = item.get("thumbnail") or item.get("img_src") or ""
                                dur = item.get("length") or ""
                                author = item.get("author") or ""
                                snippet = item.get("content") or f"Platform: {eng}"
                                if author:
                                    snippet = f"Channel: {author} | {snippet}"

                                if title and url:
                                    results.append(SearchResult(
                                        title=title,
                                        url=url,
                                        snippet=snippet,
                                        engine=eng,
                                        category="videos",
                                        network="clearnet",
                                        media_url=url,
                                        thumbnail_url=thumb,
                                        metadata={"duration": dur, "author": author, "source_engine": eng}
                                    ))
                            if results:
                                break
                except Exception as ne:
                    logger.debug(f"[MediaVideos:SearXNG] Node {base_url} error: {ne}")
        except Exception as e:
            logger.debug(f"[MediaVideos:SearXNG] Meta query error: {e}")
        return results

    def _fetch_youtube(self, query: str, limit: int, timeout: float) -> List[SearchResult]:
        """Queries YouTube via yt-dlp."""
        results: List[SearchResult] = []
        try:
            import sys
            import yt_dlp
            if sys.platform == "win32":
                # Prevent yt-dlp from spawning `cmd.exe /c ver` via platform.win32_ver()
                _ytdl_mod = sys.modules.get("yt_dlp.YoutubeDL")
                if _ytdl_mod is not None and hasattr(_ytdl_mod, "windows_enable_vt_mode"):
                    _ytdl_mod.windows_enable_vt_mode = lambda: None
            target = min(limit, 25)
            ydl_opts = {
                "extract_flat": True,
                "skip_download": True,
                "quiet": True,
                "no_warnings": True,
                "playlistend": target,
                "socket_timeout": min(timeout, 8.0)
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                res = ydl.extract_info(f"ytsearch{target}:{query}", download=False)
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
                            snippet=f"YouTube | Channel: {v_uploader} | Duration: {v_dur}" if v_dur else f"YouTube | Channel: {v_uploader}",
                            engine="youtube",
                            category="videos",
                            network="clearnet",
                            media_url=v_url,
                            thumbnail_url=v_thumb,
                            metadata={"uploader": v_uploader, "duration": v_dur, "platform": "youtube"}
                        ))
        except Exception as e:
            logger.debug(f"[MediaVideos:YouTube] yt_dlp error: {e}")
        return results

    def _fetch_archive_org(self, query: str, limit: int, timeout: float, page: int = 1) -> List[SearchResult]:
        """Queries Archive.org for open movie and documentary collections."""
        results: List[SearchResult] = []
        try:
            from ..endpoints_config import get_archive_endpoint
            enabled, base_url, auth_headers = get_archive_endpoint("archive_org")
            if not enabled or not base_url:
                return results
            q_enc = urllib.parse.quote_plus(f"{query} mediatype:movies")
            target = min(limit, 15)
            sep = "&" if "?" in base_url else "?"
            url = f"{base_url}{sep}q={q_enc}&fl[]=identifier,title,description&rows={target}&page={max(1, page)}&output=json"
            req = urllib.request.Request(url, headers={"User-Agent": "Hecos/1.0", **auth_headers})
            with urllib.request.urlopen(req, timeout=min(timeout, 5.0)) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    for d in data.get("response", {}).get("docs", []):
                        ident = d.get("identifier")
                        title = d.get("title") or ident
                        desc = d.get("description", "")
                        if isinstance(desc, list):
                            desc = " ".join(desc)
                        if ident:
                            page_url = f"https://archive.org/details/{ident}"
                            results.append(SearchResult(
                                title=title,
                                url=page_url,
                                snippet=desc[:160] if desc else f"Archive.org Public Video: {ident}",
                                engine="archive_org:video",
                                category="videos",
                                network="clearnet",
                                media_url=page_url,
                                thumbnail_url=f"https://archive.org/services/img/{ident}",
                                metadata={"identifier": ident, "platform": "archive_org"}
                            ))
        except Exception as e:
            logger.debug(f"[MediaVideos:Archive] error: {e}")
        return results

    def search(self, query: SearchQuery) -> List[SearchResult]:
        """Executes parallel multi-platform video discovery."""
        is_unlimited = (query.limit is not None and query.limit <= 0)
        target_limit = 100000 if is_unlimited else max(query.limit or 250, 250)
        per_provider = max(25, target_limit // 4)

        cfg = get_search_config()
        is_local_only = query.local_only if getattr(query, "local_only", None) is not None else bool(cfg.get("local_only", False))
        q_page = max(1, getattr(query, "page", 1))

        tasks = []
        if is_local_only:
            # Privacy Shield: query strictly the local SearXNG daemon on 127.0.0.1
            tasks.append(lambda: self._fetch_searxng_videos(query.query, target_limit, query.timeout, safe_search=query.safe_search, page=q_page))
            logger.info(f"[MediaVideos:PRIVACY] Privacy shield active: only local SearXNG video category queried.")
        else:
            # Standard & Unfiltered Providers
            tasks.append(lambda: self._fetch_dailymotion(query.query, per_provider, query.timeout, safe_search=query.safe_search, page=q_page))
            tasks.append(lambda: self._fetch_peertube(query.query, per_provider, query.timeout, safe_search=query.safe_search, page=q_page))
            tasks.append(lambda: self._fetch_searxng_videos(query.query, per_provider, query.timeout, safe_search=query.safe_search, page=q_page))
            if q_page == 1:
                tasks.append(lambda: self._fetch_youtube(query.query, per_provider, query.timeout))
            tasks.append(lambda: self._fetch_archive_org(query.query, min(per_provider, 15), query.timeout, page=q_page))

            # Configured Media Stream Slots (Active when SafeSearch is OFF)
            if not query.safe_search:
                stream_limit = max(per_provider, 120)
                media_streams = cfg.get("endpoints", {}).get("media_streams", {})
                eporner_cfg = media_streams.get("eporner", {})
                if eporner_cfg.get("enabled", True):
                    ep_url = eporner_cfg.get("url", "")
                    tasks.append(lambda: self._fetch_eporner(query.query, stream_limit, query.timeout, endpoint_url=ep_url, page=q_page))

                redtube_cfg = media_streams.get("redtube", {})
                if redtube_cfg.get("enabled", True):
                    rd_url = redtube_cfg.get("url", "")
                    tasks.append(lambda: self._fetch_redtube(query.query, stream_limit, query.timeout, endpoint_url=rd_url, page=q_page))

        all_provider_results: List[List[SearchResult]] = []
        with ThreadPoolExecutor(max_workers=max(len(tasks), 1)) as pool:
            futures = [pool.submit(t) for t in tasks]
            for fut in as_completed(futures):
                try:
                    items = fut.result()
                    if items:
                        all_provider_results.append(items)
                except Exception as fe:
                    logger.debug(f"[MediaVideos] Worker error: {fe}")

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

        logger.info(f"[MediaVideos] Aggregated {len(final_results)} videos across {len(all_provider_results)} parallel sources for '{query.query}'")
        return final_results
