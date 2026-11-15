"""
search/cyber_map/geo_resolver.py
Thread-safe, cache-backed node & protocol resolver for the Net Search Cyber Map.
Strictly honors Privacy Shield (`local_only=True` performs ZERO external network/DNS calls).
"""
from __future__ import annotations

import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from .models import MapNode, MapEdge
from .offline_geo_db import lookup_host_offline, lookup_country_coords
from .protocol_analyzer import PROTOCOL_CATALOG, classify_protocol, extract_host_port_scheme
from .tor_circuit_probe import get_live_tor_circuits

try:
    from ..config import get_search_config
    from ..endpoints_config import get_endpoints
    from ..http_client import get_tor_socks_port, is_port_open
except (ImportError, ValueError):
    from hecos.modules.net_search.search.config import get_search_config
    from hecos.modules.net_search.search.endpoints_config import get_endpoints
    from hecos.modules.net_search.search.http_client import get_tor_socks_port, is_port_open


_DNS_LOCK = threading.Lock()
# host -> {"ts": float, "ip": Optional[str], "ipv6": Optional[str]}
_DNS_CACHE: Dict[str, Dict[str, Any]] = {}
_DNS_TTL_SEC = 600.0
_MAX_DNS_CACHE = 2000


def _resolve_dns_cached(host: str) -> Dict[str, Optional[str]]:
    """Resolves IPv4/IPv6 using system DNS with caching. Only called when local_only=False."""
    clean = (host or "").strip().lower().split(":")[0]
    if not clean or clean.endswith(".onion") or clean in ("127.0.0.1", "localhost", "::1"):
        return {"ip": "127.0.0.1" if clean in ("127.0.0.1", "localhost") else None, "ipv6": None}

    # Check if already an IPv4 literal
    try:
        socket.inet_aton(clean)
        return {"ip": clean, "ipv6": None}
    except OSError:
        pass

    now = time.time()
    with _DNS_LOCK:
        cached = _DNS_CACHE.get(clean)
        if cached and (now - cached["ts"]) < _DNS_TTL_SEC:
            return {"ip": cached["ip"], "ipv6": cached["ipv6"]}

    ip4: Optional[str] = None
    ip6: Optional[str] = None
    prev_timeout = socket.getdefaulttimeout()
    try:
        infos = socket.getaddrinfo(clean, None, proto=socket.IPPROTO_TCP)
        for family, _, _, _, sockaddr in infos:
            addr = sockaddr[0]
            if family == socket.AF_INET and not ip4:
                ip4 = addr
            elif family == socket.AF_INET6 and not ip6:
                ip6 = addr
            if ip4 and ip6:
                break
    except Exception:
        pass
    finally:
        try:
            socket.setdefaulttimeout(prev_timeout)
        except Exception:
            pass

    with _DNS_LOCK:
        if len(_DNS_CACHE) > _MAX_DNS_CACHE:
            _DNS_CACHE.clear()
        _DNS_CACHE[clean] = {"ts": now, "ip": ip4, "ipv6": ip6}

    return {"ip": ip4, "ipv6": ip6}


def resolve_host_batch(
    items: List[Dict[str, Any]],
    local_only: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Resolves a batch of search result / engine items into Cyber Map host telemetry objects.
    When `local_only=True` (Privacy Shield), ZERO external DNS/HTTP lookups occur.
    """
    cfg = get_search_config()
    effective_local_only = bool(cfg.get("local_only", True)) if local_only is None else bool(local_only)

    # First pass: classify protocols and deduplicate hosts
    grouped: Dict[str, Dict[str, Any]] = {}
    clear_hosts_for_dns: List[str] = []

    for raw in (items or [])[:120]:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or "").strip()
        raw_host = str(raw.get("host") or "").strip()
        engine_id = str(raw.get("engine_id") or "").strip()
        engine = str(raw.get("engine") or "").strip()
        category = str(raw.get("category") or "").strip()
        network = str(raw.get("network") or "").strip()

        spec, host, port = classify_protocol(
            url=url,
            host=raw_host,
            engine_id=engine_id,
            engine=engine,
            category=category,
            network=network,
        )
        if not host:
            continue

        key = f"{host}|{spec.protocol_id}"
        if key not in grouped:
            geo = lookup_host_offline(host)
            grouped[key] = {
                "key": key,
                "host": host,
                "port": port,
                "protocol": spec.protocol_id,
                "protocol_label": spec.label,
                "transport": spec.transport,
                "layer": spec.layer,
                "color": spec.color,
                "network": "tor" if (host.endswith(".onion") or network == "tor" or spec.layer in ("tor", "darknet")) else ("local" if spec.layer == "local" else "clearnet"),
                "lat": geo["lat"],
                "lon": geo["lon"],
                "country_code": geo["country_code"],
                "country_name": geo["country_name"],
                "city": geo["city"],
                "geo_source": geo["source"],
                "is_virtual": geo["is_virtual"],
                "ip": "127.0.0.1" if spec.layer == "local" else None,
                "ipv6": None,
                "privacy_mode": "local_only" if effective_local_only else "all_engines",
            }
            if (
                not effective_local_only
                and not host.endswith(".onion")
                and host not in ("127.0.0.1", "localhost", "::1", "domain_lists.sqlite", "dht.magnet")
                and host not in clear_hosts_for_dns
            ):
                clear_hosts_for_dns.append(host)

    # Second pass: optional parallel DNS lookup ONLY when Privacy Shield allows external lookups
    dns_results: Dict[str, Dict[str, Optional[str]]] = {}
    if not effective_local_only and clear_hosts_for_dns:
        pool_workers = min(12, max(2, len(clear_hosts_for_dns)))
        with ThreadPoolExecutor(max_workers=pool_workers) as pool:
            futs = {pool.submit(_resolve_dns_cached, h): h for h in clear_hosts_for_dns[:60]}
            try:
                for fut in as_completed(futs, timeout=2.5):
                    h = futs[fut]
                    try:
                        dns_results[h] = fut.result()
                    except Exception:
                        pass
            except Exception:
                pass

    resolved: List[Dict[str, Any]] = []
    for entry in grouped.values():
        h = entry["host"]
        if h in dns_results:
            entry["ip"] = dns_results[h].get("ip") or entry["ip"]
            entry["ipv6"] = dns_results[h].get("ipv6") or entry["ipv6"]
            if entry["ip"]:
                entry["geo_source"] = f"{entry['geo_source']}+dns"
        resolved.append(entry)

    return {
        "ok": True,
        "local_only": effective_local_only,
        "count": len(resolved),
        "resolved": resolved,
        "protocols": {k: v.to_dict() for k, v in PROTOCOL_CATALOG.items()},
    }


def get_base_topology() -> Dict[str, Any]:
    """
    Builds the infrastructure topology snapshot: Hecos local core, SearXNG local daemon,
    Tor SOCKS5h/ControlPort, active Tor circuits, and configured fallback nodes.
    """
    cfg = get_search_config()
    endpoints = get_endpoints()
    tor_info = get_live_tor_circuits(force_refresh=False)

    searx_cfg = cfg.get("searxng", {})
    local_searx_url = searx_cfg.get("local_url", "http://127.0.0.1:8889")
    _, searx_host, searx_port = extract_host_port_scheme(local_searx_url)
    searx_port = searx_port or 8889
    searx_online = is_port_open(searx_port, searx_host or "127.0.0.1", timeout=0.15)

    socks_port = tor_info.get("socks_port") or int(cfg.get("tor", {}).get("socks_port", 9055))
    ctrl_port = tor_info.get("control_port") or int(cfg.get("tor", {}).get("control_port", 9056))

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    # 1. Hecos Core Node
    core_node = MapNode(
        id="local:hecos_core",
        label="Hecos Core Node",
        host="127.0.0.1",
        node_type="local_core",
        network="local",
        protocol="local_ipc",
        protocol_label=PROTOCOL_CATALOG["local_ipc"].label,
        transport="Internal Event Bus",
        port=5000,
        ip="127.0.0.1",
        lat=41.9028,
        lon=12.4964,
        country_code="LOCAL",
        country_name="Local Origin",
        city="Hecos Workspace",
        geo_source="local",
        color=PROTOCOL_CATALOG["local_ipc"].color,
        metadata={"role": "Coordinator & Multi-Engine Orchestrator"},
    )
    nodes.append(core_node.to_dict())

    # 2. SearXNG Local Daemon
    searx_node = MapNode(
        id="local:searxng",
        label=f"SearXNG Daemon ({'ONLINE' if searx_online else 'OFFLINE'})",
        host=searx_host or "127.0.0.1",
        node_type="local_daemon",
        network="local",
        protocol="searxng_rpc",
        protocol_label=PROTOCOL_CATALOG["searxng_rpc"].label,
        transport=f"HTTP Local :{searx_port}",
        port=searx_port,
        ip="127.0.0.1",
        lat=42.55,
        lon=11.65,
        country_code="LOCAL",
        country_name="Local Daemon",
        city=f"127.0.0.1:{searx_port}",
        geo_source="local",
        color=PROTOCOL_CATALOG["searxng_rpc"].color,
        metadata={"online": searx_online, "url": local_searx_url},
    )
    nodes.append(searx_node.to_dict())
    edges.append(
        MapEdge(
            id="edge:core->searxng",
            source="local:hecos_core",
            target="local:searxng",
            protocol="local_ipc",
            protocol_label="Local IPC",
            color=PROTOCOL_CATALOG["local_ipc"].color,
            weight=2,
            dashed=not searx_online,
        ).to_dict()
    )

    # 3. Tor SOCKS5h Daemon
    tor_online = bool(tor_info.get("tor_online"))
    tor_node = MapNode(
        id="local:tor_socks",
        label=f"Tor SOCKS5h Proxy ({'ONLINE' if tor_online else 'OFFLINE'})",
        host="127.0.0.1",
        node_type="local_daemon",
        network="tor",
        protocol="tor_circuit",
        protocol_label=PROTOCOL_CATALOG["tor_circuit"].label,
        transport=f"SOCKS5h :{socks_port} / Ctrl :{ctrl_port}",
        port=socks_port,
        ip="127.0.0.1",
        lat=41.25,
        lon=13.35,
        country_code="LOCAL",
        country_name="Local Tor Proxy",
        city=f"127.0.0.1:{socks_port}",
        geo_source="local",
        color=PROTOCOL_CATALOG["tor_circuit"].color,
        metadata={
            "online": tor_online,
            "socks_port": socks_port,
            "control_port": ctrl_port,
            "control_reachable": tor_info.get("control_reachable", False),
            "active_circuits": len(tor_info.get("circuits", [])),
        },
    )
    nodes.append(tor_node.to_dict())
    edges.append(
        MapEdge(
            id="edge:core->tor",
            source="local:hecos_core",
            target="local:tor_socks",
            protocol="tor_circuit",
            protocol_label="Tor SOCKS5h",
            color=PROTOCOL_CATALOG["tor_circuit"].color,
            weight=2,
            dashed=not tor_online,
        ).to_dict()
    )

    # 4. SQLite Domain Directory
    sqlite_node = MapNode(
        id="local:domain_sqlite",
        label="SQLite Domain Directory",
        host="domain_lists.sqlite",
        node_type="local_daemon",
        network="local",
        protocol="sqlite_dir",
        protocol_label=PROTOCOL_CATALOG["sqlite_dir"].label,
        transport="Embedded SQLite3 FTS",
        port=0,
        ip="127.0.0.1",
        lat=41.35,
        lon=11.75,
        country_code="LOCAL",
        country_name="Local Index",
        city="data/domain_lists.sqlite",
        geo_source="local",
        color=PROTOCOL_CATALOG["sqlite_dir"].color,
        metadata={"role": "Offline .onion & Clearnet Domain Directory"},
    )
    nodes.append(sqlite_node.to_dict())

    # 5. Live Tor Circuit Relays (if Tor is running)
    for circ in tor_info.get("circuits", [])[:4]:
        cid = circ["circuit_id"]
        hops = circ.get("hops", [])
        prev_id = "local:tor_socks"
        for hop in hops:
            hop_id = f"tor_relay:{hop['fingerprint']}"
            # Avoid duplicate relay nodes across circuits
            if not any(n["id"] == hop_id for n in nodes):
                nodes.append(
                    MapNode(
                        id=hop_id,
                        label=f"{hop['nickname']} ({hop['role'].upper()})",
                        host=hop.get("ip") or hop["fingerprint"][:12],
                        node_type="tor_relay",
                        network="tor",
                        protocol="tor_circuit",
                        protocol_label="Tor OR Relay",
                        transport=f"Tor OR/{hop.get('or_port') or 9001}",
                        port=hop.get("or_port") or 9001,
                        ip=hop.get("ip"),
                        lat=hop["lat"],
                        lon=hop["lon"],
                        country_code=hop["country_code"],
                        country_name=hop["country_name"],
                        city=f"Tor {hop['role'].title()} Relay",
                        geo_source="tor_control",
                        color=PROTOCOL_CATALOG["tor_circuit"].color,
                        metadata={
                            "fingerprint": hop["fingerprint"],
                            "role": hop["role"],
                            "circuit_id": cid,
                            "purpose": circ.get("purpose", "GENERAL"),
                        },
                    ).to_dict()
                )
            edges.append(
                MapEdge(
                    id=f"edge:circ:{cid}:{prev_id}->{hop_id}",
                    source=prev_id,
                    target=hop_id,
                    protocol="tor_circuit",
                    protocol_label=f"Tor Circuit #{cid}",
                    color=PROTOCOL_CATALOG["tor_circuit"].color,
                    weight=2,
                    dashed=False,
                    circuit_id=cid,
                ).to_dict()
            )
            prev_id = hop_id

    # 6. Summary of configured SearXNG mirrors (for topology awareness, light marker)
    fallbacks = endpoints.get("searxng_fallbacks", []) or []
    mirror_hosts = []
    for fb in fallbacks:
        if isinstance(fb, dict) and fb.get("enabled", True):
            u = fb.get("url") or ""
            _, h, p = extract_host_port_scheme(u)
            if h:
                mirror_hosts.append({"name": fb.get("name", h), "host": h, "port": p or 443})

    return {
        "ok": True,
        "local_only": bool(cfg.get("local_only", True)),
        "searx_online": searx_online,
        "tor": tor_info,
        "nodes": nodes,
        "edges": edges,
        "mirrors": mirror_hosts,
        "protocols": {k: v.to_dict() for k, v in PROTOCOL_CATALOG.items()},
    }
