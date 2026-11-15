"""
search/stream_hunter/m3u_parser.py
Universal parser & fetcher for .m3u, .m3u8, and .pls playlists.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Dict, List

import requests

from .models import StreamItem, detect_stream_protocol


def parse_m3u_content(content: str, source_url: str = "", default_category: str = "tv") -> List[StreamItem]:
    """
    Universal parser for .m3u, .m3u8, and .pls playlists.
    Handles both master HLS playlists (#EXT-X-STREAM-INF) and IPTV channel lists (#EXTINF).
    """
    if not content:
        return []

    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    results: List[StreamItem] = []

    if any(ln.lower().startswith("[playlist]") for ln in lines[:5]):
        pls_urls: Dict[str, str] = {}
        pls_titles: Dict[str, str] = {}
        for ln in lines:
            m_file = re.match(r"^File(\d+)=(.+)$", ln, re.IGNORECASE)
            if m_file:
                pls_urls[m_file.group(1)] = m_file.group(2).strip()
            m_title = re.match(r"^Title(\d+)=(.+)$", ln, re.IGNORECASE)
            if m_title:
                pls_titles[m_title.group(1)] = m_title.group(2).strip()
        for idx, u in pls_urls.items():
            t = pls_titles.get(idx) or f"PLS Stream #{idx}"
            results.append(StreamItem(
                title=t,
                stream_url=u,
                url=source_url or u,
                category="radio" if default_category == "radio" else default_category,
                protocol=detect_stream_protocol(u, "", default_category),
                source_engine="streams_m3u_parser",
            ))
        return results

    pending_title = ""
    pending_logo = ""
    pending_group = ""
    pending_country = "INT"
    pending_res = ""
    pending_bw = 0

    for ln in lines:
        if ln.startswith("#EXTINF:"):
            m_logo = re.search(r'tvg-logo="([^"]+)"', ln, re.IGNORECASE)
            pending_logo = m_logo.group(1).strip() if m_logo else ""
            m_group = re.search(r'group-title="([^"]+)"', ln, re.IGNORECASE)
            pending_group = m_group.group(1).strip() if m_group else ""
            m_country = re.search(r'tvg-country="([^"]+)"', ln, re.IGNORECASE)
            pending_country = m_country.group(1).strip().upper()[:2] if m_country else "INT"
            pending_title = ln.split(",", 1)[1].strip() if "," in ln else "Live Stream"
        elif ln.startswith("#EXT-X-STREAM-INF:"):
            m_res = re.search(r"RESOLUTION=(\d+x\d+)", ln, re.IGNORECASE)
            pending_res = m_res.group(1) if m_res else ""
            m_bw = re.search(r"BANDWIDTH=(\d+)", ln, re.IGNORECASE)
            pending_bw = int(int(m_bw.group(1)) / 1000) if m_bw else 0
            if not pending_title:
                pending_title = f"HLS Variant ({pending_res or 'Auto'})"
        elif not ln.startswith("#"):
            stream_u = ln
            if source_url and not stream_u.startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://")):
                stream_u = urllib.parse.urljoin(source_url, stream_u)
            if stream_u.startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://")):
                title = pending_title or stream_u.split("/")[-1].split("?")[0] or "Live Stream"
                cat = default_category
                grp_lower = pending_group.lower()
                if "radio" in grp_lower or "music" in grp_lower or "audio" in grp_lower:
                    cat = "radio"
                elif "cam" in grp_lower or "weather" in grp_lower:
                    cat = "webcam"
                results.append(StreamItem(
                    title=title,
                    stream_url=stream_u,
                    url=source_url or stream_u,
                    category=cat,
                    protocol=detect_stream_protocol(stream_u, "", cat),
                    country=pending_country,
                    resolution=pending_res,
                    bitrate=pending_bw,
                    logo=pending_logo,
                    source_engine="streams_m3u_parser",
                    tags=[pending_group] if pending_group else [],
                ))
            pending_title = ""
            pending_logo = ""
            pending_group = ""
            pending_country = "INT"
            pending_res = ""
            pending_bw = 0

    return results


def fetch_and_parse_m3u(url: str, timeout: float = 6.0) -> List[StreamItem]:
    """Fetches a remote .m3u / .m3u8 / .pls playlist URL and expands its channels."""
    try:
        headers = {"User-Agent": "VLC/3.0.20 LibVLC/3.0.20"}
        resp = requests.get(url, headers=headers, timeout=timeout, stream=True)
        raw_bytes = b""
        for chunk in resp.iter_content(chunk_size=16384):
            raw_bytes += chunk
            if len(raw_bytes) > 512 * 1024:
                break
        resp.close()
        text = raw_bytes.decode("utf-8", errors="ignore")
        items = parse_m3u_content(text, source_url=url, default_category="tv")
        if not items and url.startswith(("http://", "https://", "rtsp://")):
            items = [
                StreamItem(
                    title=url.split("/")[-1].split("?")[0] or "Direct Stream",
                    stream_url=url,
                    url=url,
                    category="raw",
                    protocol=detect_stream_protocol(url, resp.headers.get("Content-Type", ""), "raw"),
                    source_engine="streams_m3u_parser",
                )
            ]
        return items
    except Exception:
        return []
