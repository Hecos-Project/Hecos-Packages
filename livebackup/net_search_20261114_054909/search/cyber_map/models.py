"""
search/cyber_map/models.py
Structured data models for the Net Search Cyber Map topology, protocols, nodes, edges, and Tor circuits.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class GeoCoord:
    """Geographic and logical coordinates for a network node."""
    lat: float
    lon: float
    country_code: str = "XX"
    country_name: str = "Unknown"
    city: str = ""
    source: str = "offline_db"  # offline_db | tor_geoip | dns_rdap | darknet_orbit | local
    is_virtual: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProtocolSpec:
    """Normalized protocol metadata for visualization and inspection."""
    protocol_id: str            # local_ipc | tor_circuit | onion_v3 | https | http | osint_api | file_dork | media_stream | rss_feed
    label: str                  # e.g. "HTTPS/TLS", "Tor SOCKS5h (.onion)", "OSINT API"
    transport: str              # e.g. "TCP/443 TLS", "SOCKS5h -> Tor OR", "Local HTTP"
    default_port: int = 0
    color: str = "#3b82f6"
    layer: str = "clearnet"     # local | tor | darknet | clearnet | osint | files | media

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MapNode:
    """A host, relay, daemon, or service node on the Cyber Map."""
    id: str
    label: str
    host: str
    node_type: str              # local_core | local_daemon | tor_relay | onion_service | search_engine | osint_target | file_host | media_host | web_host
    network: str                # local | clearnet | tor
    protocol: str               # Canonical protocol_id
    protocol_label: str
    transport: str
    port: Optional[int] = None
    ip: Optional[str] = None
    ipv6: Optional[str] = None
    lat: float = 0.0
    lon: float = 0.0
    country_code: str = "XX"
    country_name: str = "Unknown"
    city: str = ""
    geo_source: str = "offline_db"
    is_virtual: bool = False
    color: str = "#3b82f6"
    engines: List[str] = field(default_factory=list)
    result_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MapEdge:
    """A directed connection / traffic arc between two nodes."""
    id: str
    source: str                 # source MapNode.id
    target: str                 # target MapNode.id
    protocol: str
    protocol_label: str
    color: str = "#3b82f6"
    weight: int = 1
    dashed: bool = False
    circuit_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TorCircuitHop:
    """Single relay hop in a live Tor circuit."""
    fingerprint: str
    nickname: str
    role: str                   # guard | middle | exit | rendezvous
    ip: Optional[str] = None
    or_port: Optional[int] = None
    country_code: str = "XX"
    country_name: str = "Unknown"
    lat: float = 0.0
    lon: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TorCircuitPath:
    """Complete active Tor circuit reported by Tor ControlPort."""
    circuit_id: str
    status: str                 # BUILT | EXTENDED | LAUNCHED
    purpose: str                # GENERAL | HS_CLIENT_REND | HS_CLIENT_INTRO | etc.
    hops: List[TorCircuitHop] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["hops"] = [h.to_dict() if isinstance(h, TorCircuitHop) else h for h in self.hops]
        return d
