"""
search/http_client.py
Unified HTTP client with intelligent routing: Clearnet and Tor SOCKS5h.
Supports socks5h:// proxying to eliminate DNS leaks for .onion domains.
"""
from __future__ import annotations

import random
import socket
import logging
from typing import Optional, Dict, Any
import requests

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.http")

from .config import get_search_config

# Common desktop User-Agents to prevent bot detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0"
]


def get_random_headers() -> Dict[str, str]:
    """Generates standard browser headers."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }


def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.2) -> bool:
    """Checks if a TCP port is open locally."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def get_tor_socks_port() -> Optional[int]:
    """
    Finds the active Tor SOCKS port.
    Checks:
      1. Configured search.tor.socks_port (e.g. 9055)
      2. Standard Tor daemon port (9050)
      3. Tor Browser port (9150)
    """
    cfg = get_search_config().get("tor", {})
    configured_port = int(cfg.get("socks_port", 9055))

    # Priority 1: Check configured port
    if is_port_open(configured_port):
        return configured_port

    # Priority 2: If system tor check allowed, check standard ports
    if cfg.get("use_system_tor_if_available", True):
        for candidate in [9050, 9150]:
            if is_port_open(candidate):
                return candidate

    return None


def get_tor_proxy_url() -> Optional[str]:
    """
    Returns the socks5h proxy URL (socks5h ensures DNS resolution happens on Tor).
    Returns None if no Tor port is currently listening.
    """
    cfg = get_search_config().get("tor", {})
    custom = cfg.get("custom_proxy_url", "").strip()
    if custom:
        return custom

    port = get_tor_socks_port()
    if port:
        return f"socks5h://127.0.0.1:{port}"
    return None


def is_tor_online() -> bool:
    """Returns True if Tor socks proxy is responsive."""
    return get_tor_socks_port() is not None


def check_tor_connection() -> Dict[str, Any]:
    """
    Performs an end-to-end check through Tor.
    Returns: {"ok": bool, "is_tor": bool, "ip": str, "port": int, "error": str}
    """
    port = get_tor_socks_port()
    if not port:
        hecos_logger.debug("[TOR] Status check: daemon offline (port not open)")
        return {
            "ok": False,
            "is_tor": False,
            "ip": "",
            "port": 0,
            "error": "Tor daemon is not running. Start it in the settings panel."
        }

    proxy_url = f"socks5h://127.0.0.1:{port}"
    proxies = {"http": proxy_url, "https": proxy_url}

    try:
        resp = requests.get(
            "https://check.torproject.org/api/ip",
            proxies=proxies,
            headers=get_random_headers(),
            timeout=10.0
        )
        if resp.status_code == 200:
            data = resp.json()
            is_tor = data.get("IsTor", False)
            ip = data.get("IP", "")
            hecos_logger.info(f"[TOR] Connection verified: IsTor={is_tor}, ExitIP={ip}, Port={port}")
            return {
                "ok": True,
                "is_tor": is_tor,
                "ip": ip,
                "port": port,
                "error": None
            }
        hecos_logger.warning(f"[TOR] Check service returned HTTP {resp.status_code}")
        return {
            "ok": False,
            "is_tor": False,
            "ip": "",
            "port": port,
            "error": f"HTTP {resp.status_code} from Tor check service"
        }
    except Exception as e:
        hecos_logger.warning(f"[TOR] Tor check error: {e}")
        return {
            "ok": False,
            "is_tor": False,
            "ip": "",
            "port": port,
            "error": f"Tor connection failed: {e}"
        }


def request(
    method: str,
    url: str,
    network: str = "clearnet",         # "clearnet" | "tor" | "auto"
    timeout: float = 12.0,
    headers: Optional[Dict[str, str]] = None,
    allow_redirects: bool = True,
    verify_ssl: bool = True,
    **kwargs
) -> requests.Response:
    """
    Unified HTTP request dispatcher.
    Routes through Tor if network=='tor' or if URL contains '.onion'.
    """
    req_headers = get_random_headers()
    if headers:
        req_headers.update(headers)

    is_onion = ".onion" in url.lower()
    use_tor = (network == "tor") or is_onion

    proxies = None
    if use_tor:
        proxy_url = get_tor_proxy_url()
        if not proxy_url:
            hecos_logger.error(f"[HTTP:TOR] Request failed for {url}: Tor proxy not active on port 9055/9050/9150")
            raise ConnectionError("Tor network routing requested but no Tor daemon/proxy is active on port 9055/9050/9150.")
        proxies = {
            "http": proxy_url,
            "https": proxy_url
        }
        if is_onion:
            verify_ssl = False

    hecos_logger.debug(f"[HTTP] {method.upper()} {url} (routing={'TOR' if use_tor else 'CLEAR'})")

    return requests.request(
        method=method.upper(),
        url=url,
        headers=req_headers,
        proxies=proxies,
        timeout=timeout,
        allow_redirects=allow_redirects,
        verify=verify_ssl,
        **kwargs
    )


def get(url: str, network: str = "clearnet", timeout: float = 12.0, **kwargs) -> requests.Response:
    return request("GET", url, network=network, timeout=timeout, **kwargs)


def post(url: str, network: str = "clearnet", timeout: float = 12.0, **kwargs) -> requests.Response:
    return request("POST", url, network=network, timeout=timeout, **kwargs)
