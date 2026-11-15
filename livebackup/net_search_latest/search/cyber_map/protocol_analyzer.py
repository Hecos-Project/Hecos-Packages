"""
search/cyber_map/protocol_analyzer.py
Classifies every URL, engine, and infrastructure daemon into canonical Cyber Map protocol specs,
transport layers, ports, and color encodings across Clearnet, Tor, OSINT, Files, Media, and Local IPC.
"""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, Tuple

from .models import ProtocolSpec

PROTOCOL_CATALOG: Dict[str, ProtocolSpec] = {
    "local_ipc": ProtocolSpec(
        protocol_id="local_ipc",
        label="Local Daemon / IPC",
        transport="Loopback TCP (127.0.0.1)",
        default_port=8889,
        color="#06b6d4",
        layer="local",
    ),
    "searxng_rpc": ProtocolSpec(
        protocol_id="searxng_rpc",
        label="SearXNG Meta-Search",
        transport="HTTP/JSON Meta-RPC",
        default_port=8889,
        color="#22d3ee",
        layer="clearnet",
    ),
    "tor_circuit": ProtocolSpec(
        protocol_id="tor_circuit",
        label="Tor SOCKS5h / OR",
        transport="SOCKS5h -> Tor Onion Routing",
        default_port=9055,
        color="#a855f7",
        layer="tor",
    ),
    "onion_v3": ProtocolSpec(
        protocol_id="onion_v3",
        label="DarkWeb (.onion)",
        transport="Tor Hidden Service v3 Rendezvous",
        default_port=80,
        color="#f43f5e",
        layer="darknet",
    ),
    "https": ProtocolSpec(
        protocol_id="https",
        label="HTTPS / TLS",
        transport="TCP/443 TLS",
        default_port=443,
        color="#3b82f6",
        layer="clearnet",
    ),
    "http": ProtocolSpec(
        protocol_id="http",
        label="HTTP Clearnet",
        transport="TCP/80 Plaintext",
        default_port=80,
        color="#60a5fa",
        layer="clearnet",
    ),
    "osint_api": ProtocolSpec(
        protocol_id="osint_api",
        label="OSINT Probe / API",
        transport="HTTPS REST / Sherlock Probe",
        default_port=443,
        color="#f59e0b",
        layer="osint",
    ),
    "file_dork": ProtocolSpec(
        protocol_id="file_dork",
        label="File Hunter / Archive",
        transport="HTTPS / Indexer Stream",
        default_port=443,
        color="#10b981",
        layer="files",
    ),
    "media_stream": ProtocolSpec(
        protocol_id="media_stream",
        label="Media / yt-dlp Stream",
        transport="HTTPS / Media Extractor",
        default_port=443,
        color="#ec4899",
        layer="media",
    ),
    "rss_feed": ProtocolSpec(
        protocol_id="rss_feed",
        label="RSS / Live News",
        transport="HTTPS XML/Atom Feed",
        default_port=443,
        color="#38bdf8",
        layer="clearnet",
    ),
    "sqlite_dir": ProtocolSpec(
        protocol_id="sqlite_dir",
        label="SQLite Domain Index",
        transport="Local SQLite3 Engine",
        default_port=0,
        color="#14b8a6",
        layer="local",
    ),
    "p2p_magnet": ProtocolSpec(
        protocol_id="p2p_magnet",
        label="Magnet / P2P URI",
        transport="DHT / BitTorrent URI",
        default_port=6881,
        color="#84cc16",
        layer="files",
    ),
    "ftp": ProtocolSpec(
        protocol_id="ftp",
        label="FTP / File Server",
        transport="TCP/21 FTP",
        default_port=21,
        color="#34d399",
        layer="files",
    ),
}


def extract_host_port_scheme(url_or_host: str) -> Tuple[str, str, Optional[int]]:
    """Parses scheme, clean lowercase hostname, and explicit or default port."""
    raw = (url_or_host or "").strip()
    if not raw:
        return "https", "", None

    if "://" not in raw and not raw.startswith("magnet:"):
        raw_parse = "https://" + raw
    else:
        raw_parse = raw

    if raw_parse.startswith("magnet:"):
        return "magnet", "dht.magnet", 6881

    try:
        parsed = urllib.parse.urlparse(raw_parse)
        scheme = (parsed.scheme or "https").lower()
        host = (parsed.hostname or "").lower().strip()
        port = parsed.port
        if port is None:
            if scheme == "https":
                port = 443
            elif scheme == "http":
                port = 80
            elif scheme == "ftp":
                port = 21
            elif scheme.startswith("socks"):
                port = 9055
        return scheme, host, port
    except Exception:
        clean = raw.split("/")[0].split(":")[0].lower()
        return "https", clean, 443


def classify_protocol(
    url: str = "",
    host: str = "",
    engine_id: str = "",
    engine: str = "",
    category: str = "",
    network: str = "",
) -> Tuple[ProtocolSpec, str, Optional[int]]:
    """
    Determines the best ProtocolSpec, resolved host, and port for any node/result.
    """
    scheme, parsed_host, port = extract_host_port_scheme(url or host)
    target_host = (host or parsed_host or "").lower().split(":")[0]
    eng_id = (engine_id or "").lower()
    eng = (engine or "").lower()
    cat = (category or "").lower()
    net = (network or "").lower()

    if scheme == "magnet":
        return PROTOCOL_CATALOG["p2p_magnet"], target_host or "dht.magnet", 6881

    if scheme == "ftp":
        return PROTOCOL_CATALOG["ftp"], target_host, port or 21

    if target_host in ("127.0.0.1", "localhost", "::1"):
        if port in (9050, 9055, 9056, 9150):
            return PROTOCOL_CATALOG["tor_circuit"], target_host, port
        return PROTOCOL_CATALOG["local_ipc"], target_host, port or 8889

    if target_host.endswith(".onion") or net == "tor" or eng_id.startswith("dark_"):
        return PROTOCOL_CATALOG["onion_v3"], target_host, port or 80

    if "domain_directory" in eng_id or "sqlite" in eng:
        return PROTOCOL_CATALOG["sqlite_dir"], target_host or "domain_lists.sqlite", 0

    if "searxng" in eng_id or "searx" in eng:
        spec = PROTOCOL_CATALOG["searxng_rpc"]
        return spec, target_host, port or (443 if scheme == "https" else 80)

    if eng_id.startswith("osint_") or cat == "osint":
        return PROTOCOL_CATALOG["osint_api"], target_host, port or 443

    if eng_id.startswith("files_") or cat == "files":
        return PROTOCOL_CATALOG["file_dork"], target_host, port or (443 if scheme == "https" else 80)

    if eng_id.startswith("media_") or cat in ("videos", "images", "audio"):
        return PROTOCOL_CATALOG["media_stream"], target_host, port or 443

    if "news" in eng_id or "rss:" in eng or cat == "news":
        return PROTOCOL_CATALOG["rss_feed"], target_host, port or 443

    if scheme == "http":
        return PROTOCOL_CATALOG["http"], target_host, port or 80

    return PROTOCOL_CATALOG["https"], target_host, port or 443
