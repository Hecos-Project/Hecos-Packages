"""
search/engines/media_audio.py
Parallel Multi-Platform Audio, Music & Podcast Aggregator.
Retrieves music tracks, podcast episodes, audiobooks and historical recordings across:
  - Apple iTunes Music & Podcasts (high-resolution cover artwork, audio preview streams, metadata)
  - Internet Archive Open Audio Library (album/vinyl cover artwork, historical tracks)
  - Local SearXNG Music Engines (Genius, SoundCloud, Radio, etc.)
  - DuckDuckGo Audio (SoundCloud, Bandcamp, Mixcloud streaming)
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Dict, Any, Optional
import requests

from .base import BaseEngine
from ..models import SearchQuery, SearchResult

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.engines.audio")
logger = hecos_logger


class MediaAudioEngine(BaseEngine):
    """Audio, podcast and music discovery engine with cover artwork and preview playback."""

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
        seen_urls: Set[str] = set()

        is_unlimited = (query.limit is not None and query.limit <= 0)
        target_limit = 100000 if is_unlimited else max(query.limit, 25)
        per_source_limit = min(35, max(8, target_limit // 3))
        timeout = min(query.timeout, 7.0)
        is_local_only = bool(query.local_only)

        # ── 1. Local SearXNG Music Engine ─────────────────────────────────────
        def _fetch_searxng_music() -> List[SearchResult]:
            items: List[SearchResult] = []
            try:
                from ..config import get_search_config
                cfg = get_search_config()
                searx_cfg = cfg.get("endpoints", {}).get("searxng", {})
                local_url = searx_cfg.get("local_instance", {}).get("url") or "http://127.0.0.1:8888"
                resp = requests.get(
                    f"{local_url.rstrip('/')}/search",
                    params={
                        "q": query.query,
                        "categories": "music",
                        "format": "json",
                        "safesearch": 0 if not query.safe_search else 1
                    },
                    timeout=min(timeout, 4.0)
                )
                if resp.status_code == 200:
                    raw = resp.json().get("results", [])
                    for r in raw:
                        u = r.get("url", "")
                        t = r.get("title", "")
                        if u and t:
                            thumb = r.get("img_src") or r.get("thumbnail") or ""
                            engine_name = r.get("engine", "searxng_music")
                            items.append(SearchResult(
                                title=t,
                                url=u,
                                snippet=r.get("content", "") or f"Music track from {engine_name}",
                                engine=f"searxng:{engine_name}",
                                category="audio",
                                network="clearnet",
                                media_url=u,
                                thumbnail_url=thumb,
                                metadata={"engine": engine_name}
                            ))
            except Exception as e:
                logger.debug(f"[MediaAudio] SearXNG music query note: {e}")
            return items

        # Privacy Shield: Local-Only Mode
        if is_local_only:
            logger.info("[MediaAudio:PRIVACY] Privacy Shield active: querying local SearXNG music daemon only.")
            return _fetch_searxng_music()

        # ── 2. Apple iTunes Music API ─────────────────────────────────────────
        def _fetch_itunes_music() -> List[SearchResult]:
            items: List[SearchResult] = []
            try:
                itunes_params = {
                    "term": query.query,
                    "media": "music",
                    "limit": per_source_limit
                }
                if not query.safe_search:
                    itunes_params["explicit"] = "Yes"

                resp = requests.get(
                    "https://itunes.apple.com/search",
                    params=itunes_params,
                    headers={"User-Agent": "HecosAudio/1.0"},
                    timeout=timeout
                )
                if resp.status_code == 200:
                    data = resp.json().get("results", [])
                    for d in data:
                        track_name = d.get("trackName") or d.get("collectionName", "")
                        artist = d.get("artistName", "")
                        url = d.get("trackViewUrl") or d.get("collectionViewUrl", "")
                        preview = d.get("previewUrl", "")
                        art = d.get("artworkUrl100", "")
                        if art and "100x100bb" in art:
                            art = art.replace("100x100bb", "600x600bb")
                        genre = d.get("primaryGenreName", "")
                        album = d.get("collectionName", "")
                        year = (d.get("releaseDate") or "")[:4]

                        if track_name and url:
                            snippet_parts = []
                            if artist:
                                snippet_parts.append(f"Artist: {artist}")
                            if album and album != track_name:
                                snippet_parts.append(f"Album: {album}")
                            if genre:
                                snippet_parts.append(f"Genre: {genre}")
                            if year:
                                snippet_parts.append(f"Year: {year}")

                            items.append(SearchResult(
                                title=f"{track_name} — {artist}" if artist else track_name,
                                url=url,
                                snippet=" • ".join(snippet_parts) or "Music track on Apple Music",
                                engine="itunes:music",
                                category="audio",
                                network="clearnet",
                                media_url=preview or url,
                                thumbnail_url=art,
                                metadata={
                                    "artist": artist,
                                    "album": album,
                                    "genre": genre,
                                    "year": year,
                                    "preview_url": preview,
                                    "platform": "Apple Music"
                                }
                            ))
            except Exception as e:
                logger.debug(f"[MediaAudio] iTunes music query note: {e}")
            return items

        # ── 3. Apple iTunes Podcasts API ──────────────────────────────────────
        def _fetch_itunes_podcasts() -> List[SearchResult]:
            items: List[SearchResult] = []
            try:
                pod_params = {
                    "term": query.query,
                    "media": "podcast",
                    "limit": min(per_source_limit, 10)
                }
                if not query.safe_search:
                    pod_params["explicit"] = "Yes"

                resp = requests.get(
                    "https://itunes.apple.com/search",
                    params=pod_params,
                    headers={"User-Agent": "HecosAudio/1.0"},
                    timeout=timeout
                )
                if resp.status_code == 200:
                    data = resp.json().get("results", [])
                    for d in data:
                        podcast_name = d.get("collectionName") or d.get("trackName", "")
                        artist = d.get("artistName", "")
                        url = d.get("collectionViewUrl") or d.get("trackViewUrl", "")
                        art = d.get("artworkUrl600") or d.get("artworkUrl100", "")
                        feed = d.get("feedUrl", "")
                        genre = d.get("primaryGenreName", "")

                        if podcast_name and url:
                            items.append(SearchResult(
                                title=f"🎙️ {podcast_name}",
                                url=url,
                                snippet=f"Podcast by {artist} • {genre}" if genre else f"Podcast by {artist}",
                                engine="itunes:podcast",
                                category="audio",
                                network="clearnet",
                                media_url=feed or url,
                                thumbnail_url=art,
                                metadata={
                                    "artist": artist,
                                    "genre": genre,
                                    "feed_url": feed,
                                    "platform": "Apple Podcasts"
                                }
                            ))
            except Exception as e:
                logger.debug(f"[MediaAudio] iTunes podcasts query note: {e}")
            return items

        # ── 4. Internet Archive Open Audio Library ────────────────────────────
        def _fetch_archive_org() -> List[SearchResult]:
            items: List[SearchResult] = []
            try:
                from ..config import get_search_config
                cfg = get_search_config()
                url = cfg.get("endpoints", {}).get("archives", {}).get("archive_org") or "https://archive.org/advancedsearch.php"
                params = {
                    "q": f"{query.query} mediatype:audio",
                    "fl[]": "identifier,title,description,creator,date",
                    "rows": per_source_limit,
                    "output": "json"
                }
                resp = requests.get(url, params=params, headers={"User-Agent": "HecosAudio/1.0"}, timeout=timeout)
                if resp.status_code == 200:
                    docs = resp.json().get("response", {}).get("docs", [])
                    for d in docs:
                        ident = d.get("identifier", "")
                        title = d.get("title", "") or ident
                        desc = d.get("description", "")
                        creator = d.get("creator", "")
                        year = (d.get("date") or "")[:4]
                        if isinstance(desc, list):
                            desc = " ".join(desc)
                        if isinstance(creator, list):
                            creator = ", ".join(creator)

                        if ident:
                            page_url = f"https://archive.org/details/{ident}"
                            img_url = f"https://archive.org/services/img/{ident}"
                            snippet_text = desc[:180] if desc else f"Historical audio recording from Internet Archive (ID: {ident})"
                            if year:
                                snippet_text = f"[{year}] {snippet_text}"

                            items.append(SearchResult(
                                title=f"🎵 {title}",
                                url=page_url,
                                snippet=snippet_text,
                                engine="archive_org:audio",
                                category="audio",
                                network="clearnet",
                                media_url=page_url,
                                thumbnail_url=img_url,
                                metadata={"creator": creator, "identifier": ident, "year": year}
                            ))
            except Exception as e:
                logger.debug(f"[MediaAudio] Archive.org audio note: {e}")
            return items

        # ── 5. DuckDuckGo Streaming (SoundCloud / Bandcamp) ───────────────────
        def _fetch_ddgs_audio() -> List[SearchResult]:
            items: List[SearchResult] = []
            try:
                from ddgs import DDGS
                ddg = DDGS(timeout=timeout)
                audio_query = f"{query.query} (site:soundcloud.com OR site:bandcamp.com OR site:mixcloud.com)"
                raw = ddg.text(audio_query, max_results=min(per_source_limit, 15))
                for item in raw:
                    t = item.get("title", "")
                    u = item.get("href", "") or item.get("url", "")
                    body = item.get("body", "")
                    if t and u:
                        eng_label = "soundcloud" if "soundcloud" in u else ("bandcamp" if "bandcamp" in u else "audio_stream")
                        items.append(SearchResult(
                            title=t,
                            url=u,
                            snippet=body or f"Audio track on {eng_label}",
                            engine=eng_label,
                            category="audio",
                            network="clearnet",
                            media_url=u,
                            metadata={"platform": eng_label}
                        ))
            except Exception as e:
                logger.debug(f"[MediaAudio] DDGS audio streaming note: {e}")
            return items

        # ── Concurrent Parallel Fan-Out ───────────────────────────────────────
        fetchers = [
            _fetch_itunes_music,
            _fetch_itunes_podcasts,
            _fetch_archive_org,
            _fetch_searxng_music,
            _fetch_ddgs_audio,
        ]

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_map = {executor.submit(fn): fn.__name__ for fn in fetchers}
            for fut in as_completed(future_map):
                fn_name = future_map[fut]
                try:
                    source_items = fut.result()
                    for item in source_items:
                        norm = item.url.strip().lower().rstrip("/")
                        if norm not in seen_urls:
                            seen_urls.add(norm)
                            results.append(item)
                            if len(results) >= target_limit:
                                break
                except Exception as err:
                    logger.debug(f"[MediaAudio] Fetcher {fn_name} error: {err}")
                if len(results) >= target_limit:
                    break

        logger.info(f"[MediaAudio] Multi-source audio search returned {len(results)} items across sources.")
        return results
