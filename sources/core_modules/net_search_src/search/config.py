"""
search/config.py
Configuration manager for Hecos Deep Search.
Integrates with Hecos ConfigManager while offering safe standalone defaults.
"""
from __future__ import annotations

import os
import json
import logging
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger("browser.search.config")

_DEFAULT_SEARCH_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "default_mode": "clear",
    "default_limit": 15,
    "safe_search": False,
    "auto_fallback_tor": True,
    "tor": {
        "enabled": False,              # Default off until user turns on or starts daemon
        "socks_port": 9055,            # Custom port to never clash with Tor Browser (9050/9150)
        "control_port": 9056,
        "use_system_tor_if_available": True,
        "auto_start": True,
        "custom_proxy_url": "",
        "onion_action": "hecos_viewer",  # "hecos_viewer" | "tor_browser" | "ask_menu"
        "tor_browser_path": ""
    },
    "searxng": {
        "enabled": True,
        "url": "http://127.0.0.1:8888",
        "port": 8888,
        "auto_start": True,
        "custom_engines": ""
    },
    "engines": {
        "clear_ddgs": True,
        "clear_news": True,
        "clear_searxng": True,
        "dark_ahmia": True,
        "dark_torch": True,
        "dark_haystak": True,
        "dark_onionland": True,
        "dark_excavator": True,
        "dark_phobos": True,
        "dark_tor66": True,
        "dark_danieltore": True,
        "dark_custom": True,
        "media_images": True,
        "media_videos": True,
        "media_audio": True,
        "files_dorks": True,
        "osint_sherlock": True
    },
    "endpoints": {
        "searxng": {
            "local_url": "http://127.0.0.1:8888",
            "fallbacks": [
                "https://search.ononoki.org",
                "https://searx.be",
                "https://baresearch.org",
                "https://priv.au",
                "https://searx.tiekoetter.com"
            ]
        },
        "dark_ahmia": {
            "onion_url": "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion",
            "clearnet_url": "https://ahmia.fi"
        },
        "dark_torch": {
            "ddg_onion": "https://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion/html/",
            "torch_onion": "http://xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion/cgi-bin/omega/omega"
        },
        "dark_haystak": {
            "onion_url": "http://haystak5njsmn2hqkewecpaxetahtwhsbsa64jom2k22z5afxhnpxfid.onion"
        },
        "dark_onionland": {
            "clearnet_url": "https://onionsearchengine.com/search.php",
            "onion_url": "http://37djtvjcpiprohcrlyvlhfil45kdlfizsyvilqskgvdrafn5mocz4cid.onion/search.php"
        },
        "dark_excavator": {
            "onion_url": "http://2fd6cemt4gmccflhm6imvdfvli3nf7zn6rfrwpsy7uhxrgbypvwf5fad.onion/search"
        },
        "dark_phobos": {
            "onion_url": "http://phobosxilamwcg75xt22id7aywkzol6q6rfl2flipcqoc4e4ahima5id.onion/search"
        },
        "dark_tor66": {
            "onion_url": "http://tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion/search"
        },
        "dark_danieltore": {
            "onion_url": "http://tordexu73joywapk2txdr54jed4imqledpcvcuf75qsas2gwdgksvnyd.onion/search"
        },
        "archives": {
            "archive_org": "https://archive.org/advancedsearch.php",
            "wikimedia_commons": "https://commons.wikimedia.org/w/api.php"
        },
        "custom_nodes": [],
        "custom_onion_engines": []
    },
    "max_concurrent_engines": 6,
    "request_timeout_sec": 12.0
}


def _get_config_manager():
    try:
        import sys
        if hasattr(sys, "hecos_config_manager") and sys.hecos_config_manager:
            return sys.hecos_config_manager
        from hecos.app.config import ConfigManager
        return ConfigManager()
    except Exception:
        return None


def get_search_config() -> Dict[str, Any]:
    """Retrieve the search config merged with defaults."""
    cfg_mgr = _get_config_manager()
    current = {}
    if cfg_mgr:
        try:
            browser_cfg = cfg_mgr.config.get("plugins", {}).get("BROWSER", {})
            current = browser_cfg.get("search", {})
        except Exception as e:
            logger.debug(f"Could not read search config from ConfigManager: {e}")

    # Deep merge with defaults
    result = json.loads(json.dumps(_DEFAULT_SEARCH_CONFIG))
    def _merge(dest: dict, src: dict):
        for k, v in src.items():
            if isinstance(v, dict) and k in dest and isinstance(dest[k], dict):
                _merge(dest[k], v)
            else:
                dest[k] = v
    if isinstance(current, dict):
        _merge(result, current)

    # Auto-populate tor_browser_path if not set
    tor_cfg = result.setdefault("tor", {})
    if not tor_cfg.get("tor_browser_path"):
        detected = detect_tor_browser_path()
        if detected:
            tor_cfg["tor_browser_path"] = detected

    return result


def update_search_config(updates: Dict[str, Any]) -> bool:
    """Updates the search section in Hecos plugins.BROWSER.search."""
    cfg_mgr = _get_config_manager()
    if not cfg_mgr:
        logger.warning("No ConfigManager available to persist search config.")
        return False

    try:
        current = get_search_config()
        # Merge
        def _merge(dest: dict, src: dict):
            for k, v in src.items():
                if isinstance(v, dict) and k in dest and isinstance(dest[k], dict):
                    _merge(dest[k], v)
                else:
                    dest[k] = v
        _merge(current, updates)

        browser_cfg = cfg_mgr.config.get("plugins", {}).get("BROWSER", {})
        browser_cfg["search"] = current

        payload = {
            "plugins": {
                "BROWSER": browser_cfg
            }
        }
        res = cfg_mgr.update_config(payload)
        logger.info(f"Deep Search config updated: ok={bool(res)}")
        return bool(res)
    except Exception as e:
        logger.error(f"Failed to update search config: {e}")
        return False


DEFAULT_SEARXNG_FALLBACKS = [
    {
        "name": "Ononoki Mirror",
        "protocol": "https",
        "host": "search.ononoki.org",
        "port": "",
        "path": "",
        "url": "https://search.ononoki.org",
        "enabled": True
    },
    {
        "name": "SearX Belgium",
        "protocol": "https",
        "host": "searx.be",
        "port": "",
        "path": "",
        "url": "https://searx.be",
        "enabled": True
    },
    {
        "name": "BareSearch",
        "protocol": "https",
        "host": "baresearch.org",
        "port": "",
        "path": "",
        "url": "https://baresearch.org",
        "enabled": True
    },
    {
        "name": "PrivAU Node",
        "protocol": "https",
        "host": "priv.au",
        "port": "",
        "path": "",
        "url": "https://priv.au",
        "enabled": True
    },
    {
        "name": "Tiekoetter",
        "protocol": "https",
        "host": "searx.tiekoetter.com",
        "port": "",
        "path": "",
        "url": "https://searx.tiekoetter.com",
        "enabled": True
    }
]


def build_endpoint_url(protocol: str, host: str, port: Any = "", path: str = "") -> str:
    """Builds a normalized URL from protocol, host, port, and path."""
    proto = (protocol or "https").strip().rstrip(":/")
    h = (host or "").strip().rstrip("/")
    if not h:
        return ""
    p = str(port or "").strip()
    port_str = f":{p}" if p and p not in ("80", "443", "") else ""
    path_str = (path or "").strip()
    if path_str and not path_str.startswith("/"):
        path_str = "/" + path_str
    return f"{proto}://{h}{port_str}{path_str}"


def decompose_endpoint_url(
    url: str,
    default_name: str = "",
    default_protocol: str = "https",
    use_api_key: bool = False,
    api_key: str = ""
) -> Dict[str, Any]:
    """Decomposes a URL string into structured endpoint dict (name, protocol, host, port, path, url, enabled, use_api_key, api_key)."""
    if not url:
        return {
            "name": default_name,
            "protocol": default_protocol,
            "host": "",
            "port": "",
            "path": "",
            "url": "",
            "enabled": True,
            "use_api_key": bool(use_api_key),
            "api_key": str(api_key or "")
        }
    url_str = str(url).strip()
    proto = default_protocol
    if "://" in url_str:
        proto, rest = url_str.split("://", 1)
    else:
        rest = url_str

    if "/" in rest:
        netloc, path_part = rest.split("/", 1)
        path = "/" + path_part
    else:
        netloc = rest
        path = ""

    if ":" in netloc:
        parts = netloc.split(":")
        host = parts[0]
        port = parts[1] if len(parts) > 1 else ""
    else:
        host = netloc
        port = ""
    KNOWN_NAMES = {
        "search.ononoki.org": "Ononoki Mirror",
        "searx.be": "SearX Belgium",
        "baresearch.org": "BareSearch",
        "priv.au": "PrivAU Node",
        "searx.tiekoetter.com": "Tiekoetter",
        "ahmia.fi": "Ahmia Clearnet Gateway",
        "onionsearchengine.com": "Onion Search Engine",
        "37djtvjcpiprohcrlyvlhfil45kdlfizsyvilqskgvdrafn5mocz4cid.onion": "Onion Search Engine (.onion)",
        "2fd6cemt4gmccflhm6imvdfvli3nf7zn6rfrwpsy7uhxrgbypvwf5fad.onion": "Excavator (.onion)",
        "tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion": "Tor66 (.onion)",
        "tordexu73joywapk2txdr54jed4imqledpcvcuf75qsas2gwdgksvnyd.onion": "TorDex Directory (.onion)",
        "haystak5njsmn2hqkewecpaxetahtwhsbsa64jom2k22z5afxhnpxfid.onion": "Haystak (.onion)",
        "phobosxilamwcg75xt22id7aywkzol6q6rfl2flipcqoc4e4ahima5id.onion": "Phobos (.onion)",
        "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion": "DuckDuckGo (.onion)",
        "xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion": "Torch (.onion)",
        "juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion": "Ahmia (.onion)",
        "archive.org": "Internet Archive",
        "commons.wikimedia.org": "Wikimedia Commons",
        "127.0.0.1": "SearXNG Local Daemon",
        "localhost": "SearXNG Local Daemon",
    }
    name = default_name or KNOWN_NAMES.get(host, host)
    full_url = build_endpoint_url(proto, host, port, path)

    return {
        "name": name,
        "protocol": proto,
        "host": host,
        "port": port,
        "path": path,
        "url": full_url,
        "enabled": True,
        "use_api_key": bool(use_api_key),
        "api_key": str(api_key or "")
    }


def get_endpoints() -> Dict[str, Any]:
    """Retrieve all search engine endpoints and fallback lists with full structured fields."""
    cfg = get_search_config()
    defaults = _DEFAULT_SEARCH_CONFIG.get("endpoints", {})
    current = cfg.get("endpoints", {})
    merged = json.loads(json.dumps(defaults))

    def _merge(dest: dict, src: dict):
        for k, v in src.items():
            if isinstance(v, dict) and k in dest and isinstance(dest[k], dict):
                _merge(dest[k], v)
            else:
                dest[k] = v

    if isinstance(current, dict):
        _merge(merged, current)

    # 1. Enrich SearXNG fallbacks
    raw_fallbacks = merged.get("searxng", {}).get("fallbacks", [])
    rich_fallbacks = []
    if isinstance(raw_fallbacks, list):
        for fb in raw_fallbacks:
            if isinstance(fb, dict):
                if not fb.get("url"):
                    fb["url"] = build_endpoint_url(fb.get("protocol", "https"), fb.get("host", ""), fb.get("port", ""), fb.get("path", ""))
                fb.setdefault("use_api_key", False)
                fb.setdefault("api_key", "")
                rich_fallbacks.append(fb)
            elif isinstance(fb, str) and fb.strip():
                rich_fallbacks.append(decompose_endpoint_url(fb.strip()))
    if not rich_fallbacks:
        rich_fallbacks = json.loads(json.dumps(DEFAULT_SEARXNG_FALLBACKS))
    merged.setdefault("searxng", {})["fallbacks"] = rich_fallbacks

    # 2. Enrich SearXNG local instance
    sx_local = merged.get("searxng", {}).get("local_url", "http://127.0.0.1:8888")
    if not merged.get("searxng", {}).get("local_instance"):
        merged["searxng"]["local_instance"] = decompose_endpoint_url(sx_local, default_name="SearXNG Local Daemon", default_protocol="http")
    else:
        merged["searxng"]["local_instance"].setdefault("use_api_key", False)
        merged["searxng"]["local_instance"].setdefault("api_key", "")

    # 3. Ensure custom_nodes and custom_onion_engines are lists and have API key defaults
    merged.setdefault("custom_nodes", [])
    for cn in merged.get("custom_nodes", []):
        if isinstance(cn, dict):
            cn.setdefault("use_api_key", False)
            cn.setdefault("api_key", "")

    merged.setdefault("custom_onion_engines", [])
    for coe in merged.get("custom_onion_engines", []):
        if isinstance(coe, dict):
            coe.setdefault("use_api_key", False)
            coe.setdefault("api_key", "")

    return merged


def update_endpoints(updates: Dict[str, Any]) -> bool:
    """Updates the endpoints section in search config, ensuring structured and URL fields stay in sync."""
    current_endpoints = get_endpoints()

    # Process SearXNG fallbacks if updated
    if "searxng" in updates and isinstance(updates["searxng"], dict):
        if "fallbacks" in updates["searxng"]:
            fbs = []
            for item in updates["searxng"]["fallbacks"]:
                if isinstance(item, dict):
                    url = item.get("url") or build_endpoint_url(
                        item.get("protocol", "https"),
                        item.get("host", ""),
                        item.get("port", ""),
                        item.get("path", "")
                    )
                    item["url"] = url
                    item["use_api_key"] = bool(item.get("use_api_key", False))
                    item["api_key"] = str(item.get("api_key", "")).strip()
                    fbs.append(item)
                elif isinstance(item, str):
                    fbs.append(decompose_endpoint_url(item))
            updates["searxng"]["fallbacks"] = fbs

        if "local_instance" in updates["searxng"] and isinstance(updates["searxng"]["local_instance"], dict):
            li = updates["searxng"]["local_instance"]
            url = li.get("url") or build_endpoint_url(li.get("protocol", "http"), li.get("host", "127.0.0.1"), li.get("port", "8888"), li.get("path", ""))
            li["url"] = url
            li["use_api_key"] = bool(li.get("use_api_key", False))
            li["api_key"] = str(li.get("api_key", "")).strip()
            updates["searxng"]["local_url"] = url

    def _merge(dest: dict, src: dict):
        for k, v in src.items():
            if isinstance(v, dict) and k in dest and isinstance(dest[k], dict):
                _merge(dest[k], v)
            else:
                dest[k] = v

    _merge(current_endpoints, updates)
    return update_search_config({"endpoints": current_endpoints})


def get_engine_auth_headers(engine_key: str, sub_key: str = "onion") -> Dict[str, str]:
    """Retrieves HTTP authentication headers (Bearer and X-API-Key) if configured and enabled for this engine."""
    cfg = get_search_config().get("endpoints", {}).get(engine_key, {})
    target = cfg
    if isinstance(cfg.get(sub_key), dict):
        target = cfg[sub_key]

    use_key = target.get("use_api_key", False)
    api_key = str(target.get("api_key", "")).strip()

    if use_key and api_key:
        return {
            "Authorization": f"Bearer {api_key}",
            "X-API-Key": api_key
        }
    return {}


def reset_endpoints_to_defaults() -> bool:
    """Resets all search engine endpoints to default values."""
    defaults = json.loads(json.dumps(_DEFAULT_SEARCH_CONFIG.get("endpoints", {})))
    defaults.setdefault("searxng", {})["fallbacks"] = json.loads(json.dumps(DEFAULT_SEARXNG_FALLBACKS))
    return update_search_config({"endpoints": defaults})


def detect_tor_browser_path() -> Optional[str]:
    """Auto-detects the Tor Browser firefox.exe executable across standard paths."""
    user_home = os.path.expanduser("~")
    candidates = [
        os.path.join(user_home, "Desktop", "Tor Browser", "Browser", "firefox.exe"),
        os.path.join(user_home, "OneDrive", "Desktop", "Tor Browser", "Browser", "firefox.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tor Browser", "Browser", "firefox.exe"),
        r"C:\Program Files\Tor Browser\Browser\firefox.exe",
        r"C:\Program Files (x86)\Tor Browser\Browser\firefox.exe",
        r"D:\Tor Browser\Browser\firefox.exe",
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


def get_tor_browser_path() -> str:
    """Returns configured Tor Browser path or auto-detects it."""
    cfg = get_search_config().get("tor", {})
    configured = cfg.get("tor_browser_path", "").strip()
    if configured and os.path.isfile(configured):
        return configured
    detected = detect_tor_browser_path()
    return detected or ""


def launch_tor_browser(url: str) -> Tuple[bool, str, str]:
    """Launches Tor Browser with the specified URL."""
    path = get_tor_browser_path()
    if not path:
        return False, "Tor Browser executable not found. Please install Tor Browser or specify the executable path.", ""

    import subprocess
    try:
        subprocess.Popen([path, url], shell=False)
        return True, f"Launched Tor Browser successfully: {path}", path
    except Exception as e:
        logger.error(f"Failed to launch Tor Browser: {e}")
        return False, f"Failed to launch Tor Browser: {e}", path


