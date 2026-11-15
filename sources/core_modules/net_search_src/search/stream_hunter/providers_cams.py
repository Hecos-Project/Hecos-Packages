"""
search/stream_hunter/providers_cams.py
Public Live Webcams, Traffic, Weather, Observatory & Space Feeds Provider.
Includes GPS coordinates (lat/lon) so every webcam plots accurately on the Cyber Map.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .models import StreamItem, detect_stream_protocol

BUILTIN_WEBCAM_STREAMS: List[Dict[str, Any]] = [
    {
        "title": "Axis Live Public Network Cam (MJPEG HD)",
        "stream_url": "http://158.58.130.148/mjpg/video.mjpg",
        "url": "http://158.58.130.148/",
        "protocol": "MJPEG",
        "country": "IT",
        "resolution": "720p",
        "codec": "MJPEG",
        "lat": 45.5455,
        "lon": 11.5354,
        "tags": ["italia", "mjpeg", "axis", "ipcam", "public", "webcam", "cam"],
    },
    {
        "title": "3Cat Càmeres del Temps (Panoramic & Weather Cams)",
        "stream_url": "https://directes-tv-int.3catdirectes.cat/live-content/beauties-hls/master.m3u8",
        "url": "https://www.ccma.cat/el-temps/cameres/",
        "protocol": "HLS",
        "country": "ES",
        "resolution": "1080p",
        "codec": "H.264",
        "lat": 41.3874,
        "lon": 2.1686,
        "tags": ["meteo", "weather", "panorama", "barcelona", "spain", "webcam", "cam"],
    },
    {
        "title": "Beach TV Emerald Coast Live Cams (Florida USA)",
        "stream_url": "http://media4.tripsmarter.com:1935/LiveTV/DTVHD/playlist.m3u8",
        "url": "https://www.beachtv.tv",
        "protocol": "HLS",
        "country": "US",
        "resolution": "720p",
        "codec": "H.264",
        "lat": 30.3935,
        "lon": -86.4958,
        "tags": ["usa", "florida", "beach", "coast", "ocean", "webcam", "cam"],
    },
    {
        "title": "Myrtle Beach Live Coastal & Boardwalk Cam (USA)",
        "stream_url": "http://media4.tripsmarter.com:1935/LiveTV/MTVHD/playlist.m3u8",
        "url": "https://www.beachtv.tv",
        "protocol": "HLS",
        "country": "US",
        "resolution": "720p",
        "codec": "H.264",
        "lat": 33.6891,
        "lon": -78.8867,
        "tags": ["usa", "beach", "coast", "traffic", "city", "webcam", "cam"],
    },
    {
        "title": "Panama City Beach Gulf Live Cam (USA)",
        "stream_url": "http://media4.tripsmarter.com:1935/LiveTV/BTVHD/playlist.m3u8",
        "url": "https://www.beachtv.tv",
        "protocol": "HLS",
        "country": "US",
        "resolution": "720p",
        "codec": "H.264",
        "lat": 30.1766,
        "lon": -85.8055,
        "tags": ["usa", "florida", "ocean", "beach", "meteo", "webcam", "cam"],
    },
    {
        "title": "WeatherNation Live Radar & Storm Tracker Cam (USA)",
        "stream_url": "https://a-cdn.klowdtv.com/live3/weathernation_720p/playlist.m3u8",
        "url": "https://www.weathernationtv.com",
        "protocol": "HLS",
        "country": "US",
        "resolution": "720p",
        "codec": "H.264",
        "lat": 39.7392,
        "lon": -104.9903,
        "tags": ["usa", "weather", "meteo", "radar", "storm", "webcam", "cam"],
    },
    {
        "title": "Adventure Earth Live Nature & Scenic Feeds (Europe)",
        "stream_url": "https://autentic-adventure-earth-1-eu.rakuten.wurl.tv/playlist.m3u8",
        "url": "https://autentic.com",
        "protocol": "HLS",
        "country": "DE",
        "resolution": "720p",
        "codec": "H.264",
        "lat": 47.4921,
        "lon": 11.0955,
        "tags": ["europe", "alps", "nature", "earth", "wildlife", "webcam", "cam"],
    },
    {
        "title": "BBC Earth Wildlife & Planet Observation Feed (UK)",
        "stream_url": "https://amg00793-amg00793c6-xumo-us-2669.playouts.now.amagi.tv/BBCStudios-BBCEarthA-hls/playlist.m3u8",
        "url": "https://www.bbcearth.com",
        "protocol": "HLS",
        "country": "GB",
        "resolution": "720p",
        "codec": "H.264",
        "lat": 51.5072,
        "lon": -0.1276,
        "tags": ["uk", "earth", "wildlife", "nature", "science", "webcam", "cam"],
    },
]


def search_webcam_streams(
    query: str,
    country: str = "",
    limit: int = 30,
) -> List[StreamItem]:
    """Searches curated public webcams, weather, volcano, space and traffic cams."""
    q_clean = (query or "").strip().lower()
    tokens = [t for t in re.split(r"\s+", q_clean) if t and t not in ("webcam", "webcams", "cam", "cams", "live", "stream", "telecamera", "telecamere", "all", "*")]
    country_filter = (country or "").strip().upper()

    results: List[StreamItem] = []
    for raw in BUILTIN_WEBCAM_STREAMS:
        if country_filter and country_filter != "ALL" and raw.get("country", "").upper() != country_filter:
            continue
        if tokens:
            hay = " ".join([
                str(raw.get("title", "")),
                str(raw.get("country", "")),
                " ".join(raw.get("tags") or []),
            ]).lower()
            if not any(tok in hay for tok in tokens):
                continue
        su = raw["stream_url"]
        results.append(StreamItem(
            title=raw["title"],
            stream_url=su,
            url=raw.get("url") or su,
            category="webcam",
            protocol=raw.get("protocol") or detect_stream_protocol(su, "", "webcam"),
            country=raw.get("country", "INT"),
            codec=raw.get("codec", "H.264"),
            resolution=raw.get("resolution", "1080p"),
            lat=raw.get("lat"),
            lon=raw.get("lon"),
            source_engine="streams_webcams",
            tags=list(raw.get("tags") or []),
        ))

    if not results and not country_filter:
        for raw in BUILTIN_WEBCAM_STREAMS[:min(limit, 8)]:
            su = raw["stream_url"]
            results.append(StreamItem(
                title=raw["title"],
                stream_url=su,
                url=raw.get("url") or su,
                category="webcam",
                protocol=raw.get("protocol") or detect_stream_protocol(su, "", "webcam"),
                country=raw.get("country", "INT"),
                codec=raw.get("codec", "H.264"),
                resolution=raw.get("resolution", "1080p"),
                lat=raw.get("lat"),
                lon=raw.get("lon"),
                source_engine="streams_webcams",
                tags=list(raw.get("tags") or []),
            ))

    return results[:limit]
