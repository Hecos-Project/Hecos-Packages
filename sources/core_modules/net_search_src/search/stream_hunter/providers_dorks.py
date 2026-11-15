"""
search/stream_hunter/providers_dorks.py
Raw Stream & Playlist Dork Hunter (.m3u8, .m3u, .pls, .mpd, Icecast, Axis/MJPEG cams).
Queries local SearXNG metasearch daemon (privacy-preserving) to discover raw live streams on the web.
"""
from __future__ import annotations

import re
from typing import List

import requests

from .models import StreamItem, detect_stream_protocol

try:
    from ..endpoints_config import get_endpoints
except (ImportError, ValueError):
    from hecos.modules.net_search.search.endpoints_config import get_endpoints


STREAM_URL_REGEX = re.compile(
    r'(https?://[^\s"\'<>]+?\.(?:m3u8|m3u|pls|mpd|mp3|aac|ogg)(?:\?[^\s"\'<>]*)?)',
    re.IGNORECASE,
)


def search_raw_stream_dorks(
    query: str,
    subfilter: str = "all",
    limit: int = 25,
) -> List[StreamItem]:
    """
    Executes targeted stream dork queries against local SearXNG (127.0.0.1:8889)
    to discover indexed .m3u8, .m3u, .pls, Icecast, and public MJPEG camera streams.
    """
    q_clean = (query or "").strip()
    if not q_clean or q_clean == "*":
        q_clean = "live"

    if subfilter == "webcam":
        dork_q = f'{q_clean} (inurl:"mjpg/video.mjpg" OR inurl:"view/view.shtml" OR inurl:".m3u8" webcam)'
    elif subfilter == "radio":
        dork_q = f'{q_clean} (inurl:".m3u" OR inurl:".pls" OR "icecast" OR "listen.pls") radio'
    else:
        dork_q = f'{q_clean} (filetype:m3u8 OR filetype:m3u OR inurl:".m3u8" OR inurl:"playlist.m3u8")'

    endpoints = get_endpoints()
    searx_base = (endpoints.get("searxng_url") or "http://127.0.0.1:8889").rstrip("/")

    results: List[StreamItem] = []
    seen = set()

    try:
        resp = requests.get(
            f"{searx_base}/search",
            params={"q": dork_q, "format": "json", "pageno": 1},
            timeout=4.5,
        )
        if resp.status_code != 200:
            return results
        payload = resp.json()
        raw_items = payload.get("results") or []

        for item in raw_items:
            page_url = (item.get("url") or "").strip()
            title = (item.get("title") or "").strip()
            content = (item.get("content") or "").strip()
            if not page_url:
                continue

            # Extract direct stream URL either from page_url or from snippet content
            stream_url = ""
            u_lower = page_url.lower()
            if any(ext in u_lower for ext in (".m3u8", ".m3u", ".pls", ".mpd", "video.mjpg", "axis-cgi/mjpg", ":8000/", "listen.pls")):
                stream_url = page_url
            else:
                m = STREAM_URL_REGEX.search(content) or STREAM_URL_REGEX.search(page_url)
                if m:
                    stream_url = m.group(1)

            target_u = stream_url or page_url
            if target_u in seen:
                continue
            seen.add(target_u)

            proto = detect_stream_protocol(target_u, "", "raw")
            cat = "raw"
            if proto == "MJPEG" or "cam" in u_lower:
                cat = "webcam"
            elif proto in ("ICECAST", "PLS") or "radio" in u_lower:
                cat = "radio"
            elif proto == "HLS" and stream_url:
                cat = "tv"

            results.append(StreamItem(
                title=title or target_u.split("/")[-1],
                stream_url=target_u,
                url=page_url,
                category=cat,
                protocol=proto,
                source_engine="streams_dorks",
                tags=["dork", proto.lower()],
            ))
            if len(results) >= limit:
                break
    except Exception:
        pass

    return results
