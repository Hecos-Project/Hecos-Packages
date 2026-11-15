"""
search/stream_hunter/service.py
Orchestrates parallel Live Stream Discovery across TV/IPTV, World Radio, Public Webcams,
and Raw Stream Dorks, with Cyber Map geolocation enrichment and optional liveness probing.
"""
from __future__ import annotations

import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("net_search.stream_hunter")

from .models import StreamItem, detect_stream_protocol
from .providers_tv import search_tv_streams, fetch_and_parse_m3u
from .providers_radio import search_radio_streams
from .providers_cams import search_webcam_streams
from .providers_dorks import search_raw_stream_dorks
from .stream_prober import probe_streams_batch
from .stream_store import search_sqlite_streams, get_stream_summary

try:
    from ..cyber_map.offline_geo_db import COUNTRY_CENTROIDS, lookup_host_offline
    from ..config import get_search_config, get_endpoints
except (ImportError, ValueError):
    from hecos.modules.net_search.search.cyber_map.offline_geo_db import COUNTRY_CENTROIDS, lookup_host_offline
    from hecos.modules.net_search.search.config import get_search_config, get_endpoints


def _enrich_stream_geo(item: StreamItem) -> None:
    """Ensures every StreamItem has lat/lon coordinates for Cyber Map plotting."""
    if item.lat is not None and item.lon is not None:
        return
    # 1. Try country code centroid with deterministic micro-jitter so pins don't stack on 1 pixel
    cc = (item.country or "").upper().strip()
    if cc in COUNTRY_CENTROIDS:
        base_lat, base_lon, _, _ = COUNTRY_CENTROIDS[cc]
        h = int(hashlib.md5(item.stream_url.encode("utf-8", errors="ignore")).hexdigest()[:6], 16)
        dlat = ((h % 200) - 100) * 0.015
        dlon = (((h >> 8) % 200) - 100) * 0.015
        item.lat = round(base_lat + dlat, 4)
        item.lon = round(base_lon + dlon, 4)
        return

    # 2. Fallback to offline_geo_db host lookup
    if item.host:
        info = lookup_host_offline(item.host)
        if info:
            item.lat = info.get("lat")
            item.lon = info.get("lon")
            if (not item.country or item.country == "INT") and info.get("country_code"):
                item.country = info["country_code"]


class StreamHunterService:
    """High-level service for searching, parsing, and probing live audio/video streams."""

    def search(
        self,
        query: str = "",
        subfilter: str = "all",
        country: str = "",
        limit: int = 80,
        local_only: Optional[bool] = None,
        auto_probe: bool = False,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        cfg = get_search_config()
        effective_local_only = bool(cfg.get("local_only", False)) if local_only is None else bool(local_only)

        q_str = (query or "").strip()
        sub = (subfilter or "all").strip().lower()
        cc = (country or "").strip().upper()
        if cc == "ALL":
            cc = ""

        sh_cfg = cfg.get("stream_hunter") if isinstance(cfg.get("stream_hunter"), dict) else {}
        src_toggles = sh_cfg.get("sources") if isinstance(sh_cfg.get("sources"), dict) else {}
        use_iptv_builtin = src_toggles.get("iptv_builtin", True) is not False
        use_iptv_api = src_toggles.get("iptv_org_api", True) is not False
        use_radio_builtin = src_toggles.get("radio_builtin", True) is not False
        use_radio_api = src_toggles.get("radio_browser_api", True) is not False
        use_webcams = src_toggles.get("webcams_builtin", True) is not False
        use_dorks = src_toggles.get("searxng_dorks", True) is not False
        use_sqlite = src_toggles.get("sqlite_stream_store", True) is not False

        hecos_logger.info(
            f"[StreamHunter] Search start: query={q_str!r} subfilter={sub} country={cc or 'ALL'} "
            f"limit={limit} local_only={effective_local_only} auto_probe={auto_probe}"
        )

        all_items: List[StreamItem] = []

        # 1. Include user's Manual Stream Nodes from Central Hub (custom_stream_nodes)
        manual_count = 0
        try:
            endpoints = get_endpoints()
            custom_nodes = endpoints.get("custom_stream_nodes", [])
            q_lower = q_str.lower()
            for node in custom_nodes:
                if not isinstance(node, dict) or node.get("enabled") is False:
                    continue
                n_url = (node.get("url") or "").strip()
                if not n_url:
                    continue
                n_cat = (node.get("category") or "tv").strip().lower()
                if n_cat not in ("tv", "radio", "webcam", "raw"):
                    n_cat = "tv"
                if sub not in ("all", "") and not (
                    sub == n_cat
                    or (sub == "cams" and n_cat == "webcam")
                    or (sub == "dorks" and n_cat == "raw")
                ):
                    continue
                n_country = (node.get("country") or "INT").strip().upper()
                if cc and n_country != cc and n_country != "INT":
                    continue
                n_name = (node.get("name") or n_url).strip()
                if q_lower and not q_str.startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://")):
                    hay = f"{n_name} {n_url} {n_cat} {n_country}".lower()
                    if not all(tok in hay for tok in q_lower.split()):
                        continue
                all_items.append(StreamItem(
                    title=n_name,
                    stream_url=n_url,
                    url=n_url,
                    category=n_cat,
                    protocol=detect_stream_protocol(n_url, n_cat),
                    country=n_country,
                    tags=["manual", "custom-node", n_cat],
                    source_engine="streams_manual",
                ))
                manual_count += 1
        except Exception as e:
            hecos_logger.warning(f"[StreamHunter] Manual custom_stream_nodes read error: {e}")

        # 2. Query SQLite Stream Compilations Store (stream_lists.sqlite)
        sqlite_count = 0
        if use_sqlite:
            try:
                sqlite_hits = search_sqlite_streams(
                    query=q_str if not q_str.startswith(("http://", "https://", "rtsp://")) else "",
                    subfilter=sub,
                    country=cc,
                    limit=max(30, int(limit // 2)),
                )
                sqlite_count = len(sqlite_hits)
                all_items.extend(sqlite_hits)
            except Exception as e:
                hecos_logger.warning(f"[StreamHunter] SQLite stream store query error: {e}")

        # Direct URL / Playlist detection: if query is a URL (.m3u8, .m3u, .pls, rtsp://, http://)
        if q_str.startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://")):
            if any(ext in q_str.lower() for ext in (".m3u", ".m3u8", ".pls")):
                parsed_list = fetch_and_parse_m3u(q_str)
                all_items.extend(parsed_list)
                hecos_logger.info(f"[StreamHunter] Direct playlist parsed {len(parsed_list)} items from {q_str}")
            if not all_items:
                all_items.append(StreamItem(
                    title=q_str.split("/")[-1].split("?")[0] or "Direct Network Stream",
                    stream_url=q_str,
                    url=q_str,
                    category="raw",
                    protocol=detect_stream_protocol(q_str),
                    source_engine="streams_direct",
                ))

        per_provider_limit = max(20, int(limit // 2)) if sub == "all" else max(30, int(limit))

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {}
            if sub in ("all", "tv") and (use_iptv_builtin or use_iptv_api):
                tv_local_only = effective_local_only or (not use_iptv_api)
                futures["tv"] = pool.submit(
                    search_tv_streams, q_str, cc, per_provider_limit, tv_local_only
                )
            if sub in ("all", "radio") and (use_radio_builtin or use_radio_api):
                radio_local_only = effective_local_only or (not use_radio_api)
                futures["radio"] = pool.submit(
                    search_radio_streams, q_str, cc, per_provider_limit, radio_local_only
                )
            if sub in ("all", "webcam", "cams") and use_webcams:
                futures["webcam"] = pool.submit(
                    search_webcam_streams, q_str, cc, per_provider_limit
                )
            if sub in ("all", "raw", "dorks") and use_dorks:
                futures["raw"] = pool.submit(
                    search_raw_stream_dorks, q_str, sub, min(25, per_provider_limit)
                )

            provider_counts: Dict[str, int] = {"tv": 0, "radio": 0, "webcam": 0, "raw": 0}
            for key, fut in futures.items():
                try:
                    res_list = fut.result(timeout=8.0) or []
                    provider_counts[key] = len(res_list)
                    all_items.extend(res_list)
                except Exception as e:
                    provider_counts[key] = 0
                    hecos_logger.warning(f"[StreamHunter] Provider '{key}' failed or timed out: {e}")

        # Deduplicate by stream_url and enrich geolocation
        deduped: List[StreamItem] = []
        seen_urls = set()
        for item in all_items:
            su = (item.stream_url or "").strip()
            if not su or su in seen_urls:
                continue
            seen_urls.add(su)
            _enrich_stream_geo(item)
            deduped.append(item)
            if len(deduped) >= limit:
                break

        # Optional fast batch liveness probe on top 12 streams
        if auto_probe and deduped:
            top_urls = [it.stream_url for it in deduped[:12]]
            probe_map = probe_streams_batch(top_urls, timeout=2.5)
            live_probed = 0
            for it in deduped:
                p = probe_map.get(it.stream_url)
                if p:
                    it.is_live = bool(p.get("is_live"))
                    if it.is_live:
                        live_probed += 1
                    if p.get("bitrate") and not it.bitrate:
                        it.bitrate = int(p["bitrate"])
                    if p.get("resolution") and not it.resolution:
                        it.resolution = str(p["resolution"])
                    if p.get("now_playing") and not it.now_playing:
                        it.now_playing = str(p["now_playing"])
            hecos_logger.info(f"[StreamHunter] Auto-probe checked {len(top_urls)} streams: {live_probed} live")

        cat_counts = {"all": len(deduped), "tv": 0, "radio": 0, "webcam": 0, "raw": 0}
        for it in deduped:
            c = it.category if it.category in cat_counts else "raw"
            cat_counts[c] += 1

        duration = round(time.perf_counter() - t0, 2)
        hecos_logger.info(
            f"[StreamHunter] Search complete in {duration}s: {len(deduped)} deduped streams "
            f"(manual={manual_count}, sqlite={sqlite_count}, providers={provider_counts}, cats={cat_counts})"
        )
        return {
            "ok": True,
            "query": q_str,
            "subfilter": sub,
            "country": cc or "ALL",
            "count": len(deduped),
            "counts": cat_counts,
            "duration_sec": duration,
            "streams": [it.to_dict() for it in deduped],
            "search_results": [it.to_search_result_dict() for it in deduped],
        }


_SERVICE_SINGLETON: Optional[StreamHunterService] = None


def get_stream_hunter_service() -> StreamHunterService:
    global _SERVICE_SINGLETON
    if _SERVICE_SINGLETON is None:
        _SERVICE_SINGLETON = StreamHunterService()
    return _SERVICE_SINGLETON


def search_streams(
    query: str = "",
    category: str = "all",
    max_results: int = 40,
    country: str = "",
    auto_probe: bool = False,
) -> Dict[str, Any]:
    """Convenience wrapper used by StreamLLMTools and StreamRemoteBus."""
    return get_stream_hunter_service().search(
        query=query,
        subfilter=category,
        country=country,
        limit=max_results,
        auto_probe=auto_probe,
    )

