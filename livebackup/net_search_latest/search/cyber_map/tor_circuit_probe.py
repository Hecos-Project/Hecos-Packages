"""
search/cyber_map/tor_circuit_probe.py
Resilient, low-latency reader for the active Tor daemon ControlPort (default 127.0.0.1:9056).
Extracts live Tor circuits (Guard -> Middle -> Exit/Rendezvous), relay IPs, nicknames,
and country codes using Tor's built-in GeoIP lookup with offline fallback.
"""
from __future__ import annotations

import os
import re
import socket
import time
import threading
import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("net_search.cyber_map.tor")

from .models import TorCircuitHop, TorCircuitPath
from .offline_geo_db import lookup_country_coords, lookup_host_offline

try:
    from ..config import get_search_config
    from ..http_client import get_tor_socks_port, is_port_open
except (ImportError, ValueError):
    from hecos.modules.net_search.search.config import get_search_config
    from hecos.modules.net_search.search.http_client import get_tor_socks_port, is_port_open


_LOCK = threading.Lock()
_CIRCUIT_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_RELAY_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}  # fp -> (ts, info)

_CIRCUIT_LINE_RE = re.compile(
    r"^(\d+)\s+(BUILT|EXTENDED|LAUNCHED)\s+([^\s]+)(?:\s+.*)?$"
)
_FP_NICK_RE = re.compile(r"^\$([A-Fa-f0-9]+)(?:[~=]([A-Za-z0-9_.\-]+))?$")
_PURPOSE_RE = re.compile(r"\bPURPOSE=([A-Z0-9_]+)")
_R_LINE_RE = re.compile(
    r"^r\s+([^\s]+)\s+[^\s]+\s+[^\s]+\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+)"
)


def _recv_until_end(sock: socket.socket, timeout: float = 0.8) -> str:
    """Reads a Tor control protocol response until final `250 OK` or error code."""
    sock.settimeout(timeout)
    chunks: List[str] = []
    buf = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            raw = sock.recv(8192)
            if not raw:
                break
            buf += raw.decode("utf-8", errors="replace")
            chunks.append(buf)
            # Check if buffer ends with standard Tor terminal status line ("250 OK\r\n" or "5xx ...")
            lines = buf.splitlines()
            if lines:
                last = lines[-1].strip()
                if re.match(r"^[245]\d{2}\s", last):
                    break
        except socket.timeout:
            break
        except Exception:
            break
    return buf


def _control_command(sock: socket.socket, cmd: str, timeout: float = 0.8) -> str:
    sock.sendall((cmd.rstrip("\r\n") + "\r\n").encode("utf-8"))
    return _recv_until_end(sock, timeout=timeout)


def _find_cookie_auth_hex() -> Optional[str]:
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        hecos_root = os.path.normpath(os.path.join(here, "..", "..", "..", "..", ".."))
        candidates = [
            os.path.join(hecos_root, "data", "tor", "data", "control_auth_cookie"),
            os.path.join(hecos_root, "hecos", "data", "tor", "data", "control_auth_cookie"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    return f.read().hex()
    except Exception:
        pass
    return None


def _open_authenticated_ctrl_socket(ctrl_port: int, timeout: float = 0.7) -> Optional[socket.socket]:
    if not is_port_open(ctrl_port, timeout=0.15):
        return None
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(("127.0.0.1", ctrl_port))
        resp = _control_command(s, 'AUTHENTICATE ""', timeout=timeout)
        if "250" in resp:
            return s
        cookie_hex = _find_cookie_auth_hex()
        if cookie_hex:
            resp2 = _control_command(s, f"AUTHENTICATE {cookie_hex}", timeout=timeout)
            if "250" in resp2:
                return s
        s.close()
    except Exception:
        try:
            s.close()
        except Exception:
            pass
    return None


def _query_relay_descriptor(sock: socket.socket, fingerprint: str, nickname: str) -> Dict[str, Any]:
    fp_up = fingerprint.upper()
    now = time.time()
    cached = _RELAY_CACHE.get(fp_up)
    if cached and (now - cached[0]) < 120.0:
        return dict(cached[1])

    info: Dict[str, Any] = {
        "fingerprint": fp_up,
        "nickname": nickname or fp_up[:8],
        "ip": None,
        "or_port": None,
        "country_code": "XX",
        "country_name": "Tor Network Relay",
        "lat": 0.0,
        "lon": 0.0,
    }

    try:
        ns_resp = _control_command(sock, f"GETINFO ns/id/{fp_up}", timeout=0.5)
        for line in ns_resp.splitlines():
            m = _R_LINE_RE.match(line.strip())
            if m:
                info["nickname"] = m.group(1) or info["nickname"]
                info["ip"] = m.group(2)
                info["or_port"] = int(m.group(3))
                break
    except Exception:
        pass

    ip = info.get("ip")
    if ip:
        # 1. Try Tor's native GeoIP engine first (zero external network traffic)
        try:
            geo_resp = _control_command(sock, f"GETINFO ip-to-country/{ip}", timeout=0.4)
            m_cc = re.search(rf"ip-to-country/{re.escape(ip)}=([A-Za-z?]{{2}})", geo_resp)
            if m_cc:
                cc = m_cc.group(1).upper()
                if cc != "??":
                    coords = lookup_country_coords(cc, seed=fp_up)
                    if coords:
                        info["country_code"] = coords["country_code"]
                        info["country_name"] = coords["country_name"]
                        info["lat"] = coords["lat"]
                        info["lon"] = coords["lon"]
        except Exception:
            pass

    # 2. Fallback deterministic offline coordinates anchored across European/US Tor relay hubs
    if info["country_code"] == "XX" or (info["lat"] == 0.0 and info["lon"] == 0.0):
        # Deterministic relay cluster selection based on fingerprint when Tor GeoIP file is absent
        hubs = ["DE", "NL", "FR", "CH", "FI", "GB", "SE", "US", "CA", "RO", "CZ"]
        try:
            idx = int(fp_up[:4], 16) % len(hubs)
        except Exception:
            idx = 0
        fallback_cc = hubs[idx]
        coords = lookup_country_coords(fallback_cc, seed=fp_up)
        if coords:
            info["country_code"] = fallback_cc
            info["country_name"] = f"{coords['country_name']} (Relay)"
            info["lat"] = coords["lat"]
            info["lon"] = coords["lon"]

    _RELAY_CACHE[fp_up] = (now, dict(info))
    return info


def get_live_tor_circuits(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Returns live Tor circuits from the local ControlPort (127.0.0.1:9056).
    Never raises on failure; gracefully indicates offline/unavailable status.
    """
    now = time.time()
    with _LOCK:
        if not force_refresh and _CIRCUIT_CACHE["data"] and (now - _CIRCUIT_CACHE["ts"]) < 4.0:
            return _CIRCUIT_CACHE["data"]

    cfg = get_search_config().get("tor", {})
    ctrl_port = int(cfg.get("control_port", 9056))
    socks_port = get_tor_socks_port()

    result: Dict[str, Any] = {
        "tor_online": socks_port is not None,
        "socks_port": socks_port,
        "control_port": ctrl_port,
        "control_reachable": False,
        "circuits": [],
        "timestamp": now,
    }

    sock = _open_authenticated_ctrl_socket(ctrl_port, timeout=0.6)
    if not sock:
        with _LOCK:
            _CIRCUIT_CACHE["ts"] = now
            _CIRCUIT_CACHE["data"] = result
        return result

    result["control_reachable"] = True
    circuits: List[TorCircuitPath] = []
    try:
        raw = _control_command(sock, "GETINFO circuit-status", timeout=0.9)
        parsed_built: List[Tuple[str, str, str, List[str]]] = []

        for line in raw.splitlines():
            clean = line.strip()
            m = _CIRCUIT_LINE_RE.match(clean)
            if not m:
                continue
            cid, status, path_str = m.group(1), m.group(2), m.group(3)
            if status != "BUILT":
                continue
            m_p = _PURPOSE_RE.search(clean)
            purpose = m_p.group(1) if m_p else "GENERAL"
            hop_tokens = [t.strip() for t in path_str.split(",") if t.strip()]
            if hop_tokens:
                parsed_built.append((cid, status, purpose, hop_tokens))

        # Prioritize active GENERAL and HS circuits, cap at 8 circuits to stay lightweight
        parsed_built.sort(key=lambda c: (0 if "HS_" in c[2] or c[2] == "GENERAL" else 1, -len(c[3]), -int(c[0])))
        for cid, status, purpose, hop_tokens in parsed_built[:8]:
            hops: List[TorCircuitHop] = []
            total = len(hop_tokens)
            for idx, tok in enumerate(hop_tokens):
                m_fp = _FP_NICK_RE.match(tok)
                if not m_fp:
                    continue
                fp = m_fp.group(1).upper()
                nick = m_fp.group(2) or fp[:8]
                if idx == 0:
                    role = "guard"
                elif idx == total - 1:
                    role = "rendezvous" if purpose.startswith("HS_") else "exit"
                else:
                    role = "middle"

                relay_info = _query_relay_descriptor(sock, fp, nick)
                hops.append(
                    TorCircuitHop(
                        fingerprint=fp,
                        nickname=relay_info["nickname"],
                        role=role,
                        ip=relay_info.get("ip"),
                        or_port=relay_info.get("or_port"),
                        country_code=relay_info["country_code"],
                        country_name=relay_info["country_name"],
                        lat=relay_info["lat"],
                        lon=relay_info["lon"],
                    )
                )

            if hops:
                circuits.append(
                    TorCircuitPath(
                        circuit_id=cid,
                        status=status,
                        purpose=purpose,
                        hops=hops,
                        timestamp=now,
                    )
                )
    except Exception as e:
        hecos_logger.debug(f"[CyberMap:Tor] Error reading circuit-status: {e}")
    finally:
        try:
            sock.close()
        except Exception:
            pass

    result["circuits"] = [c.to_dict() for c in circuits]
    with _LOCK:
        _CIRCUIT_CACHE["ts"] = now
        _CIRCUIT_CACHE["data"] = result
    return result
