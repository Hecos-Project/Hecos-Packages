"""
search/stream_hunter/providers_tv.py
Live TV & IPTV stream discovery provider:
1. Built-in resilient FTA TV catalog (from catalog_tv.py).
2. Cached IPTV-Org public index (channels + streams JSON API).
3. Re-exports .m3u/.m3u8/.pls parser helpers from m3u_parser.py for compatibility.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

import requests

from .catalog_tv import BUILTIN_TV_STREAMS
from .m3u_parser import fetch_and_parse_m3u, parse_m3u_content
from .models import StreamItem, detect_stream_protocol

_CACHE_LOCK = threading.Lock()
_IPTV_MEM_CACHE: Optional[List[Dict[str, Any]]] = None
_IPTV_MEM_TS: float = 0.0
_CACHE_TTL_SEC = 86400.0  # 24 hours


def _get_cache_dir() -> str:
    base = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "stream_hunter_cache")
    )
    os.makedirs(base, exist_ok=True)
    return base


def _load_or_fetch_iptv_org(local_only: bool = False) -> List[Dict[str, Any]]:
    """Loads cached IPTV-Org merged streams or fetches them if allowed."""
    global _IPTV_MEM_CACHE, _IPTV_MEM_TS
    now = time.time()
    with _CACHE_LOCK:
        if _IPTV_MEM_CACHE is not None and (now - _IPTV_MEM_TS) < _CACHE_TTL_SEC:
            return _IPTV_MEM_CACHE

    cache_file = os.path.join(_get_cache_dir(), "iptv_org_merged.json")
    if os.path.isfile(cache_file):
        try:
            age = now - os.path.getmtime(cache_file)
            if age < _CACHE_TTL_SEC or local_only:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list) and data:
                    with _CACHE_LOCK:
                        _IPTV_MEM_CACHE = data
                        _IPTV_MEM_TS = now
                    return data
        except Exception:
            pass

    if local_only:
        return []

    try:
        headers = {"User-Agent": "HecosNetSearch/1.1 (+https://hecos.local)"}
        r_streams = requests.get("https://iptv-org.github.io/api/streams.json", headers=headers, timeout=7.0)
        if r_streams.status_code != 200:
            return []
        streams_raw = r_streams.json()

        ch_map: Dict[str, Dict[str, Any]] = {}
        try:
            r_ch = requests.get("https://iptv-org.github.io/api/channels.json", headers=headers, timeout=7.0)
            if r_ch.status_code == 200:
                for ch in r_ch.json():
                    cid = ch.get("id")
                    if cid:
                        ch_map[cid] = {
                            "name": ch.get("name") or cid,
                            "country": ch.get("country") or "INT",
                            "categories": ch.get("categories") or [],
                            "website": ch.get("website") or "",
                        }
        except Exception:
            pass

        merged: List[Dict[str, Any]] = []
        for st in streams_raw:
            s_url = (st.get("url") or "").strip()
            if not s_url or not s_url.startswith(("http://", "https://", "rtsp://", "rtmp://")):
                continue
            cid = st.get("channel") or ""
            ch_info = ch_map.get(cid, {})
            title = st.get("title") or ch_info.get("name") or cid or s_url.split("/")[-1]
            country = ch_info.get("country") or (cid.split(".")[-1].upper() if "." in cid else "INT")
            cats = ch_info.get("categories") or []
            merged.append({
                "title": title,
                "stream_url": s_url,
                "url": ch_info.get("website") or s_url,
                "country": country[:2].upper() if country else "INT",
                "resolution": st.get("quality") or "",
                "tags": cats + ([cid.lower()] if cid else []),
            })
            if len(merged) >= 5000:
                break

        if merged:
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(merged, f, ensure_ascii=False)
            except Exception:
                pass
            with _CACHE_LOCK:
                _IPTV_MEM_CACHE = merged
                _IPTV_MEM_TS = now
        return merged
    except Exception:
        return []


_FILLER_TOKENS = {
    "tv", "live", "stream", "streaming", "diretta", "canale",
    "channel", "all", "*", "hd", "fta", "online", "watch", "guarda",
}


def search_tv_streams(
    query: str,
    country: str = "",
    limit: int = 40,
    local_only: bool = False,
) -> List[StreamItem]:
    """Searches built-in FTA TV channels + cached IPTV-Org global streams with relevance ranking."""
    q_clean = (query or "").strip().lower()
    tokens = [t for t in re.split(r"\s+", q_clean) if t and t not in _FILLER_TOKENS]
    clean_phrase = " ".join(tokens)
    country_filter = (country or "").strip().upper()

    scored_results: List[tuple[float, int, StreamItem]] = []
    seen_urls = set()
    seq_idx = 0

    def _score_entry(entry: Dict[str, Any], is_builtin: bool = False) -> float:
        if country_filter and country_filter != "ALL" and entry.get("country", "").upper() != country_filter:
            return -1.0
        if not tokens:
            return 50.0 if is_builtin else 10.0

        title_low = str(entry.get("title", "")).lower()
        tags_low = " ".join(str(t).lower() for t in (entry.get("tags") or []))
        country_low = str(entry.get("country", "")).lower()
        lang_low = str(entry.get("language", "")).lower()
        meta_text = f"{title_low} {tags_low} {country_low} {lang_low}"
        haystack = f"{meta_text} {str(entry.get('stream_url', '')).lower()}"

        score = 0.0
        if clean_phrase and clean_phrase in title_low:
            score += 120.0
        elif clean_phrase and clean_phrase.replace(" ", "") in title_low.replace(" ", ""):
            score += 100.0

        if all(tok in meta_text for tok in tokens):
            score += 70.0
            for tok in tokens:
                if re.search(rf"\b{re.escape(tok)}\b", title_low):
                    score += 20.0
                elif tok in title_low:
                    score += 10.0
        elif all(tok in haystack for tok in tokens):
            score += 35.0
        else:
            # Partial match only for significant tokens (>= 3 chars) in title/tags
            long_matched = [tok for tok in tokens if len(tok) >= 3 and tok in meta_text]
            if not long_matched or len(tokens) > 1:
                return -1.0
            score += 15.0 * len(long_matched)

        if is_builtin:
            score += 12.0
        return score

    def _append_raw(raw: Dict[str, Any], score: float) -> None:
        nonlocal seq_idx
        su = raw["stream_url"]
        if su in seen_urls:
            return
        seen_urls.add(su)
        seq_idx += 1
        scored_results.append((
            score,
            -seq_idx,
            StreamItem(
                title=raw["title"],
                stream_url=su,
                url=raw.get("url") or su,
                category="tv",
                protocol=detect_stream_protocol(su, "", "tv"),
                country=raw.get("country", "INT"),
                language=raw.get("language", ""),
                codec=raw.get("codec", ""),
                resolution=raw.get("resolution", ""),
                bitrate=int(raw.get("bitrate", 0)),
                logo=raw.get("logo", ""),
                source_engine="streams_iptv",
                tags=list(raw.get("tags") or []),
            ),
        ))

    for raw in BUILTIN_TV_STREAMS:
        sc = _score_entry(raw, is_builtin=True)
        if sc >= 0:
            _append_raw(raw, sc)

    for raw in _load_or_fetch_iptv_org(local_only=local_only):
        if len(scored_results) >= max(limit * 3, 120):
            break
        sc = _score_entry(raw, is_builtin=False)
        if sc >= 0:
            _append_raw(raw, sc)

    if not scored_results and not country_filter:
        for raw in BUILTIN_TV_STREAMS[:min(limit, 10)]:
            _append_raw(raw, 1.0)

    scored_results.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scored_results[:limit]]


__all__ = ["BUILTIN_TV_STREAMS", "parse_m3u_content", "fetch_and_parse_m3u", "search_tv_streams"]
