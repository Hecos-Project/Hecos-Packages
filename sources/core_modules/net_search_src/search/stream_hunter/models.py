"""
search/stream_hunter/models.py
Data models for Live Audio/Video Stream Discovery (TV/IPTV, Radio, Webcams, Raw M3U8/RTSP/Icecast).
"""
from __future__ import annotations

import hashlib
import urllib.parse
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


def make_stream_id(stream_url: str, title: str = "") -> str:
    raw = f"{(stream_url or '').strip()}|{(title or '').strip().lower()}"
    return "sh_" + hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:14]


def detect_stream_protocol(url: str, content_type: str = "", category: str = "") -> str:
    u = (url or "").lower().strip()
    ct = (content_type or "").lower()
    if u.startswith("rtsp://") or u.startswith("rtsps://"):
        return "RTSP"
    if u.startswith("rtmp://") or u.startswith("rtmps://"):
        return "RTMP"
    if u.startswith("mms://") or u.startswith("mmsh://"):
        return "MMS"
    if ".m3u8" in u or "mpegurl" in ct or "x-mpegurl" in ct or "vnd.apple.mpegurl" in ct:
        return "HLS"
    if ".mpd" in u or "dash+xml" in ct:
        return "DASH"
    if "mjpg" in u or "mjpeg" in u or "multipart/x-mixed-replace" in ct or "axis-cgi/mjpg" in u:
        return "MJPEG"
    if u.endswith(".pls") or ".pls?" in u or "scpls" in ct:
        return "PLS"
    if u.endswith(".m3u") or ".m3u?" in u:
        return "M3U"
    if any(ext in u for ext in (".mp3", ".aac", ".ogg", ".opus", ".flac", ":8000/", ":8080/", "icecast", "shoutcast")) or "audio/" in ct:
        return "ICECAST"
    if category == "radio":
        return "ICECAST"
    if category == "webcam":
        return "HLS"
    return "HLS" if category == "tv" else "DIRECT"


def extract_host_and_port(url: str) -> tuple[str, int]:
    try:
        parsed = urllib.parse.urlparse(url if "://" in url else f"https://{url}")
        host = (parsed.hostname or "").lower().strip()
        port = parsed.port
        if not port:
            scheme = (parsed.scheme or "https").lower()
            if scheme == "https":
                port = 443
            elif scheme == "rtsp":
                port = 554
            elif scheme == "rtmp":
                port = 1935
            else:
                port = 80
        return host, int(port)
    except Exception:
        return "", 80


@dataclass
class StreamItem:
    title: str
    stream_url: str
    category: str = "tv"              # "tv" | "radio" | "webcam" | "raw"
    protocol: str = "HLS"             # "HLS" | "ICECAST" | "DASH" | "RTSP" | "MJPEG" | "M3U" | "DIRECT"
    url: str = ""                     # Reference/station homepage or stream_url
    country: str = "INT"              # ISO-2 code or INT
    language: str = ""
    codec: str = ""
    bitrate: int = 0                  # kbps
    resolution: str = ""              # e.g. "1080p", "720p", "Audio", "Live Cam"
    logo: str = ""
    is_live: Optional[bool] = None    # True = verified online, False = dead, None = unprobed
    now_playing: str = ""             # ICY StreamTitle or program info
    host: str = ""
    port: int = 443
    lat: Optional[float] = None
    lon: Optional[float] = None
    source_engine: str = "streams_iptv"
    tags: List[str] = field(default_factory=list)
    id: str = ""

    def __post_init__(self):
        if not self.url:
            self.url = self.stream_url
        if not self.id:
            self.id = make_stream_id(self.stream_url, self.title)
        if not self.protocol:
            self.protocol = detect_stream_protocol(self.stream_url, "", self.category)
        if not self.host:
            self.host, self.port = extract_host_and_port(self.stream_url)
        if self.country:
            self.country = self.country.upper().strip()[:3] or "INT"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["network"] = "tor" if (self.host and self.host.endswith(".onion")) else "clear"
        return d

    def to_search_result_dict(self) -> Dict[str, Any]:
        """Formats StreamItem as a standard NetSearch result with Cyber Map metadata."""
        snippet_parts = [f"[{self.protocol}]"]
        if self.category:
            snippet_parts.append(self.category.upper())
        if self.country and self.country != "INT":
            snippet_parts.append(f"Country: {self.country}")
        if self.resolution:
            snippet_parts.append(self.resolution)
        if self.bitrate:
            snippet_parts.append(f"{self.bitrate} kbps")
        if self.codec:
            snippet_parts.append(self.codec)
        if self.now_playing:
            snippet_parts.append(f"Now Playing: {self.now_playing}")
        return {
            "id": self.id,
            "title": self.title,
            "url": self.stream_url,
            "stream_url": self.stream_url,
            "homepage_url": self.url,
            "snippet": " • ".join(snippet_parts),
            "engine": self.source_engine,
            "engine_id": self.source_engine,
            "category": f"streams_{self.category}",
            "stream_category": self.category,
            "protocol": self.protocol,
            "country": self.country,
            "language": self.language,
            "codec": self.codec,
            "bitrate": self.bitrate,
            "resolution": self.resolution,
            "thumbnail": self.logo,
            "logo": self.logo,
            "is_live": self.is_live,
            "now_playing": self.now_playing,
            "host": self.host,
            "port": self.port,
            "lat": self.lat,
            "lon": self.lon,
            "tags": self.tags,
            "network": "tor" if (self.host and self.host.endswith(".onion")) else "clear",
        }
