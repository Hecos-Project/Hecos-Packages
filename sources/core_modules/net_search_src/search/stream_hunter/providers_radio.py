"""
search/stream_hunter/providers_radio.py
World Radio & Icecast/Shoutcast Audio Stream Discovery Provider:
1. Built-in resilient Italian & International radio streams (Icecast/MP3/AAC/HLS).
2. Distributed Radio-Browser API (30,000+ live stations worldwide with codec, bitrate, and GPS coordinates).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

import requests

from .models import StreamItem, detect_stream_protocol

RADIO_BROWSER_MIRRORS = [
    "https://de1.api.radio-browser.info",
    "https://fi1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
]

BUILTIN_RADIO_STREAMS: List[Dict[str, Any]] = [
    {
        "title": "RTL 102.5 Live (Italia)",
        "stream_url": "https://streamingv2.shoutcast.com/rtl-1025",
        "url": "https://www.rtl.it",
        "country": "IT",
        "language": "it",
        "codec": "MP3",
        "bitrate": 192,
        "lat": 45.5236,
        "lon": 9.2747,
        "tags": ["pop", "hits", "news", "italia", "rtl", "radio"],
    },
    {
        "title": "Radio 24 - Il Sole 24 Ore (Talk & News Italia)",
        "stream_url": "http://shoutcast2.radio24.it:8000/",
        "url": "https://www.radio24.ilsole24ore.com",
        "country": "IT",
        "language": "it",
        "codec": "MP3",
        "bitrate": 128,
        "lat": 45.4792,
        "lon": 9.1538,
        "tags": ["news", "talk", "economia", "finanza", "italia", "radio24", "radio"],
    },
    {
        "title": "Virgin Radio Italy (Rock Live)",
        "stream_url": "https://icecast.unitedradio.it/Virgin.mp3",
        "url": "https://www.virginradio.it",
        "country": "IT",
        "language": "it",
        "codec": "MP3",
        "bitrate": 128,
        "lat": 45.4642,
        "lon": 9.1900,
        "tags": ["rock", "classic rock", "italia", "virgin", "music", "radio"],
    },
    {
        "title": "Radio Monte Carlo (RMC 1 Live)",
        "stream_url": "https://icecast.unitedradio.it/RMC.mp3",
        "url": "https://www.radiomontecarlo.net",
        "country": "IT",
        "language": "it",
        "codec": "MP3",
        "bitrate": 128,
        "lat": 43.7384,
        "lon": 7.4246,
        "tags": ["lounge", "pop", "jazz", "chill", "italia", "rmc", "radio"],
    },
    {
        "title": "Radio 105 Network Live (Italia)",
        "stream_url": "https://icecast.unitedradio.it/Radio105.mp3",
        "url": "https://www.105.net",
        "country": "IT",
        "language": "it",
        "codec": "MP3",
        "bitrate": 128,
        "lat": 45.4654,
        "lon": 9.1859,
        "tags": ["pop", "comedy", "hits", "italia", "105", "radio"],
    },
    {
        "title": "Radio Deejay Live (Italia)",
        "stream_url": "https://4c4b867c89244861ac216426883d1ad0.msvdn.net/radiodeejay/radiodeejay/master_ma.m3u8",
        "url": "https://www.deejay.it",
        "country": "IT",
        "language": "it",
        "codec": "AAC",
        "bitrate": 192,
        "lat": 45.4773,
        "lon": 9.1815,
        "tags": ["pop", "dance", "talk", "italia", "deejay", "radio"],
    },
    {
        "title": "Radio Capital Live (Classics & News Italia)",
        "stream_url": "https://4c4b867c89244861ac216426883d1ad0.msvdn.net/radiocapital/radiocapital/master_ma.m3u8",
        "url": "https://www.capital.it",
        "country": "IT",
        "language": "it",
        "codec": "AAC",
        "bitrate": 192,
        "lat": 41.9028,
        "lon": 12.4964,
        "tags": ["classic", "rock", "soul", "news", "italia", "capital", "radio"],
    },
    {
        "title": "SomaFM: DEF CON Radio (Hacker & Cyber Music)",
        "stream_url": "https://ice2.somafm.com/defcon-128-mp3",
        "url": "https://somafm.com/defcon/",
        "country": "US",
        "language": "en",
        "codec": "MP3",
        "bitrate": 128,
        "lat": 37.7749,
        "lon": -122.4194,
        "tags": ["electronic", "cyber", "hacker", "ambient", "tech", "somafm", "radio"],
    },
    {
        "title": "SomaFM: Groove Salad (Ambient / Downtempo Beats)",
        "stream_url": "https://ice2.somafm.com/groovesalad-128-mp3",
        "url": "https://somafm.com/groovesalad/",
        "country": "US",
        "language": "en",
        "codec": "MP3",
        "bitrate": 128,
        "lat": 37.7749,
        "lon": -122.4194,
        "tags": ["ambient", "chillout", "downtempo", "lounge", "somafm", "radio"],
    },
    {
        "title": "SomaFM: Secret Agent (Spy Lounge & Soundtrack)",
        "stream_url": "https://ice2.somafm.com/secretagent-128-mp3",
        "url": "https://somafm.com/secretagent/",
        "country": "US",
        "language": "en",
        "codec": "MP3",
        "bitrate": 128,
        "lat": 37.7749,
        "lon": -122.4194,
        "tags": ["lounge", "jazz", "soundtrack", "spy", "somafm", "radio"],
    },
    {
        "title": "BBC World Service English (Global News Radio)",
        "stream_url": "http://stream.live.vc.bbcmedia.co.uk/bbc_world_service",
        "url": "https://www.bbc.co.uk/sounds/play/live:bbc_world_service",
        "country": "GB",
        "language": "en",
        "codec": "MP3",
        "bitrate": 128,
        "lat": 51.5186,
        "lon": -0.1436,
        "tags": ["news", "world", "bbc", "uk", "talk", "english", "radio"],
    },
    {
        "title": "Radio Swiss Jazz (Ad-Free 24/7 Jazz)",
        "stream_url": "https://stream.srg-ssr.ch/m/rsj/mp3_128",
        "url": "https://www.radioswissjazz.ch",
        "country": "CH",
        "language": "en",
        "codec": "MP3",
        "bitrate": 128,
        "lat": 46.9480,
        "lon": 7.4474,
        "tags": ["jazz", "blues", "soul", "swiss", "music", "radio"],
    },
    {
        "title": "Radio Swiss Classic (Symphonic & Classical)",
        "stream_url": "https://stream.srg-ssr.ch/m/rsc_de/mp3_128",
        "url": "https://www.radioswissclassic.ch",
        "country": "CH",
        "language": "de",
        "codec": "MP3",
        "bitrate": 128,
        "lat": 47.3769,
        "lon": 8.5417,
        "tags": ["classical", "classica", "orchestra", "swiss", "music", "radio"],
    },
    {
        "title": "FIP Radio France (Eclectic Music Paris)",
        "stream_url": "https://icecast.radiofrance.fr/fip-hifi.aac",
        "url": "https://www.radiofrance.fr/fip",
        "country": "FR",
        "language": "fr",
        "codec": "AAC",
        "bitrate": 192,
        "lat": 48.8524,
        "lon": 2.2782,
        "tags": ["eclectic", "jazz", "world", "rock", "france", "fip", "radio"],
    },
    {
        "title": "KEXP 90.3 FM Seattle (Indie & Alternative Live)",
        "stream_url": "https://kexp-mp3-128.streamguys1.com/kexp128.mp3",
        "url": "https://www.kexp.org",
        "country": "US",
        "language": "en",
        "codec": "MP3",
        "bitrate": 128,
        "lat": 47.6229,
        "lon": -122.3537,
        "tags": ["indie", "alternative", "rock", "live", "kexp", "usa", "radio"],
    },
]


def search_radio_streams(
    query: str,
    country: str = "",
    limit: int = 40,
    local_only: bool = False,
) -> List[StreamItem]:
    """Searches built-in radio streams + Radio-Browser distributed API."""
    q_clean = (query or "").strip().lower()
    tokens = [t for t in re.split(r"\s+", q_clean) if t and t not in ("radio", "live", "stream", "fm", "audio", "all", "*")]
    country_filter = (country or "").strip().upper()

    results: List[StreamItem] = []
    seen_urls = set()

    def _matches_builtin(entry: Dict[str, Any]) -> bool:
        if country_filter and country_filter != "ALL" and entry.get("country", "").upper() != country_filter:
            return False
        if not tokens:
            return True
        hay = " ".join([
            str(entry.get("title", "")),
            str(entry.get("country", "")),
            str(entry.get("codec", "")),
            " ".join(entry.get("tags") or []),
        ]).lower()
        return any(tok in hay for tok in tokens)

    # 1. Built-in high-reliability stations
    for raw in BUILTIN_RADIO_STREAMS:
        if _matches_builtin(raw):
            su = raw["stream_url"]
            if su not in seen_urls:
                seen_urls.add(su)
                results.append(StreamItem(
                    title=raw["title"],
                    stream_url=su,
                    url=raw.get("url") or su,
                    category="radio",
                    protocol=detect_stream_protocol(su, "", "radio"),
                    country=raw.get("country", "INT"),
                    language=raw.get("language", ""),
                    codec=raw.get("codec", "MP3"),
                    bitrate=int(raw.get("bitrate", 128)),
                    resolution="Audio",
                    lat=raw.get("lat"),
                    lon=raw.get("lon"),
                    source_engine="streams_radiobrowser",
                    tags=list(raw.get("tags") or []),
                ))

    # 2. Remote Radio-Browser API lookup (when Privacy Shield allows external queries)
    if not local_only and len(results) < limit:
        params: Dict[str, Any] = {
            "limit": min(60, max(20, limit)),
            "hidebroken": "true",
            "order": "clickcount",
            "reverse": "true",
        }
        if tokens:
            params["name"] = " ".join(tokens)
        if country_filter and country_filter != "ALL" and len(country_filter) == 2:
            params["countrycode"] = country_filter

        headers = {"User-Agent": "HecosNetSearch/1.1"}
        for mirror in RADIO_BROWSER_MIRRORS:
            try:
                resp = requests.get(
                    f"{mirror}/json/stations/search",
                    params=params,
                    headers=headers,
                    timeout=4.5,
                )
                if resp.status_code == 200:
                    stations = resp.json()
                    # If name search returned too few and we had a genre/tag token, try tag search too
                    if len(stations) < 5 and tokens:
                        tag_params = dict(params)
                        tag_params.pop("name", None)
                        tag_params["tag"] = tokens[0]
                        r2 = requests.get(
                            f"{mirror}/json/stations/search",
                            params=tag_params,
                            headers=headers,
                            timeout=3.5,
                        )
                        if r2.status_code == 200:
                            stations.extend(r2.json())

                    for st in stations:
                        su = (st.get("url_resolved") or st.get("url") or "").strip()
                        if not su or su in seen_urls or not su.startswith(("http://", "https://")):
                            continue
                        seen_urls.add(su)
                        cc = (st.get("countrycode") or "INT").upper()
                        codec = (st.get("codec") or "MP3").upper()
                        br = int(st.get("bitrate") or 0)
                        lat = st.get("geo_lat")
                        lon = st.get("geo_long")
                        raw_tags = [t.strip() for t in (st.get("tags") or "").split(",") if t.strip()][:6]
                        results.append(StreamItem(
                            title=(st.get("name") or "Live Radio").strip(),
                            stream_url=su,
                            url=st.get("homepage") or su,
                            category="radio",
                            protocol=detect_stream_protocol(su, codec, "radio"),
                            country=cc,
                            language=(st.get("languagecodes") or "").split(",")[0],
                            codec=codec,
                            bitrate=br,
                            resolution="Audio",
                            logo=st.get("favicon") or "",
                            lat=float(lat) if lat is not None else None,
                            lon=float(lon) if lon is not None else None,
                            source_engine="streams_radiobrowser",
                            tags=raw_tags,
                        ))
                        if len(results) >= limit:
                            break
                    break
            except Exception:
                continue

    if not results and not country_filter:
        for raw in BUILTIN_RADIO_STREAMS[:min(limit, 10)]:
            su = raw["stream_url"]
            results.append(StreamItem(
                title=raw["title"],
                stream_url=su,
                url=raw.get("url") or su,
                category="radio",
                protocol=detect_stream_protocol(su, "", "radio"),
                country=raw.get("country", "INT"),
                language=raw.get("language", ""),
                codec=raw.get("codec", "MP3"),
                bitrate=int(raw.get("bitrate", 128)),
                resolution="Audio",
                lat=raw.get("lat"),
                lon=raw.get("lon"),
                source_engine="streams_radiobrowser",
                tags=list(raw.get("tags") or []),
            ))

    return results[:limit]
