"""
search/stream_hunter/stream_prober.py
Fast concurrent HTTP /HLS / ICY (Icecast/Shoutcast) / MJPEG liveness prober and metadata extractor.
"""
from __future__ import annotations

import logging
import re
import socket
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

import requests

from .models import detect_stream_protocol

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("net_search.stream_prober")


def probe_single_stream(url: str, timeout: float = 3.0) -> Dict[str, Any]:
    """
    Probes a single stream URL (HTTP/HTTPS/RTSP) for liveness, latency, Content-Type,
    HLS resolution/bandwidth, and Icecast ICY headers.
    """
    u = (url or "").strip()
    t0 = time.perf_counter()
    result: Dict[str, Any] = {
        "url": u,
        "is_live": False,
        "status_code": 0,
        "protocol": detect_stream_protocol(u),
        "content_type": "",
        "bitrate": 0,
        "resolution": "",
        "now_playing": "",
        "server_name": "",
        "latency_ms": 0,
    }
    if not u:
        return result

    # RTSP / RTMP TCP socket check
    if u.startswith(("rtsp://", "rtsps://", "rtmp://", "mms://")):
        try:
            parsed = urllib.parse.urlparse(u)
            host = parsed.hostname or ""
            port = parsed.port or (554 if u.startswith("rtsp") else 1935)
            with socket.create_connection((host, port), timeout=timeout):
                result["is_live"] = True
                result["status_code"] = 200
                result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            hecos_logger.info(
                f"[StreamProber] TCP socket probe LIVE {result['protocol']} {u} latency={result['latency_ms']}ms"
            )
        except Exception as e:
            result["is_live"] = False
            result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            hecos_logger.info(f"[StreamProber] TCP socket probe OFFLINE {u}: {e}")
        return result

    headers = {
        "User-Agent": "VLC/3.0.20 LibVLC/3.0.20",
        "Icy-MetaData": "1",
        "Accept": "*/*",
    }
    try:
        resp = requests.get(u, headers=headers, timeout=timeout, stream=True, allow_redirects=True)
        latency = int((time.perf_counter() - t0) * 1000)
        result["status_code"] = resp.status_code
        result["latency_ms"] = latency

        ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        result["content_type"] = ct
        result["protocol"] = detect_stream_protocol(u, ct)

        # Check Icecast / Shoutcast ICY headers
        icy_br = resp.headers.get("icy-br") or resp.headers.get("ice-audio-info", "")
        if icy_br:
            m_br = re.search(r"(\d+)", str(icy_br))
            if m_br:
                result["bitrate"] = int(m_br.group(1))
        icy_name = resp.headers.get("icy-name") or ""
        if icy_name:
            result["server_name"] = icy_name.strip()
        icy_desc = resp.headers.get("icy-description") or resp.headers.get("icy-genre") or ""
        if icy_desc:
            result["now_playing"] = icy_desc.strip()

        if 200 <= resp.status_code < 400:
            result["is_live"] = True
            # If HLS playlist, peek first 2 KB to verify #EXTM3U and extract resolution/bandwidth
            if result["protocol"] in ("HLS", "M3U") or "mpegurl" in ct or u.lower().endswith(".m3u8"):
                chunk = next(resp.iter_content(chunk_size=2048), b"")
                text = chunk.decode("utf-8", errors="ignore")
                if "#EXTM3U" in text:
                    result["protocol"] = "HLS"
                    m_res = re.search(r"RESOLUTION=(\d+x\d+)", text)
                    if m_res:
                        res_raw = m_res.group(1)
                        h = res_raw.split("x")[-1]
                        result["resolution"] = f"{h}p" if h in ("1080", "720", "480", "360", "2160") else res_raw
                    m_bw = re.search(r"BANDWIDTH=(\d+)", text)
                    if m_bw and not result["bitrate"]:
                        result["bitrate"] = max(64, int(int(m_bw.group(1)) / 1000))
        resp.close()
        hecos_logger.info(
            f"[StreamProber] HTTP probe {'LIVE' if result['is_live'] else 'OFFLINE'} "
            f"status={result['status_code']} proto={result['protocol']} "
            f"res={result['resolution'] or '-'} br={result['bitrate'] or 0}kbps "
            f"latency={latency}ms url={u}"
        )
    except Exception as e:
        result["is_live"] = False
        result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        hecos_logger.info(f"[StreamProber] HTTP probe ERROR url={u}: {e}")

    return result


def probe_streams_batch(urls: List[str], timeout: float = 3.0, max_workers: int = 8) -> Dict[str, Dict[str, Any]]:
    """Concurrently probes up to 25 stream URLs and returns a map of url -> probe result."""
    clean_urls = []
    seen = set()
    for u in (urls or []):
        u_str = (u or "").strip()
        if u_str and u_str not in seen:
            seen.add(u_str)
            clean_urls.append(u_str)
        if len(clean_urls) >= 25:
            break

    if not clean_urls:
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(clean_urls))) as pool:
        fut_map = {pool.submit(probe_single_stream, u, timeout): u for u in clean_urls}
        for fut in as_completed(fut_map):
            u = fut_map[fut]
            try:
                out[u] = fut.result()
            except Exception as e:
                hecos_logger.warning(f"[StreamProber] Batch worker exception for {u}: {e}")
                out[u] = {"url": u, "is_live": False, "status_code": 0}
    live_count = sum(1 for v in out.values() if v.get("is_live"))
    hecos_logger.info(f"[StreamProber] Batch probe finished: {live_count}/{len(clean_urls)} streams LIVE")
    return out
