"""
search/endpoints_config.py
Endpoints configuration, URL builder/decomposer, SearXNG fallbacks, and authentication headers.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger("browser.search.endpoints")

DEFAULT_SEARXNG_FALLBACKS: List[Dict[str, Any]] = [
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
    """Decomposes a URL string into structured endpoint dict."""
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
    try:
        from hecos.modules.net_search.search.config import get_search_config, _DEFAULT_SEARCH_CONFIG
    except (ImportError, ValueError):
        from .config import get_search_config, _DEFAULT_SEARCH_CONFIG

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
    sx_local = merged.get("searxng", {}).get("local_url", "http://127.0.0.1:8889")
    if not merged.get("searxng", {}).get("local_instance"):
        merged["searxng"]["local_instance"] = decompose_endpoint_url(sx_local, default_name="SearXNG Local Daemon", default_protocol="http")
    else:
        merged["searxng"]["local_instance"].setdefault("use_api_key", False)
        merged["searxng"]["local_instance"].setdefault("api_key", "")

    # 2b. Enrich SearXNG Aggregated Engines (Merge user customized states with all default engines)
    default_engines = _DEFAULT_SEARCH_CONFIG.get("endpoints", {}).get("searxng", {}).get("engines", [])
    raw_user_engines = merged.get("searxng", {}).get("engines", [])
    existing_map = {}
    if isinstance(raw_user_engines, list):
        for e in raw_user_engines:
            if isinstance(e, dict):
                k = str(e.get("name") or e.get("id") or "").strip().lower()
                if k:
                    existing_map[k] = e

    combined_engines = []
    seen_engine_names = set()
    for d_eng in default_engines:
        d_name = str(d_eng.get("name") or d_eng.get("id") or "").strip().lower()
        seen_engine_names.add(d_name)
        eng_entry = dict(d_eng)
        if d_name in existing_map:
            eng_entry["enabled"] = existing_map[d_name].get("enabled", d_eng.get("enabled", True))
        combined_engines.append(eng_entry)

    # Preserve any custom user-added engines not in defaults
    for k, v in existing_map.items():
        if k not in seen_engine_names:
            combined_engines.append(v)

    rich_engines = []
    for eng in combined_engines:
        if isinstance(eng, dict):
            eng_name = str(eng.get("name") or eng.get("id") or "").strip().lower()
            if eng_name:
                rich_engines.append({
                    "id": eng.get("id") or eng_name,
                    "name": eng_name,
                    "label": str(eng.get("label") or eng_name.capitalize()).strip(),
                    "category": str(eng.get("category", "general")).strip(),
                    "enabled": eng.get("enabled", True) is not False
                })
    merged.setdefault("searxng", {})["engines"] = rich_engines

    # 2c. Enrich media_streams
    ms_defaults = _DEFAULT_SEARCH_CONFIG.get("endpoints", {}).get("media_streams", {})
    merged.setdefault("media_streams", {})
    for k, v in ms_defaults.items():
        if k not in merged["media_streams"]:
            merged["media_streams"][k] = json.loads(json.dumps(v))

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

    merged.setdefault("custom_clear_engines", [])
    for cce in merged.get("custom_clear_engines", []):
        if isinstance(cce, dict):
            cce.setdefault("use_api_key", False)
            cce.setdefault("api_key", "")
            cce.setdefault("category", "general")

    merged.setdefault("custom_stream_nodes", [])
    for csn in merged.get("custom_stream_nodes", []):
        if isinstance(csn, dict):
            csn.setdefault("use_api_key", False)
            csn.setdefault("api_key", "")
            csn.setdefault("category", "tv")
            csn.setdefault("country", "INT")
            if not csn.get("url") and csn.get("host"):
                csn["url"] = build_endpoint_url(
                    csn.get("protocol", "https"),
                    csn.get("host", ""),
                    csn.get("port", ""),
                    csn.get("path", ""),
                )

    # 4. Enrich Open Archives & Repositories (structured nodes + custom_archives)
    arch = merged.setdefault("archives", {})
    ao_url = str(arch.get("archive_org") or "https://archive.org/advancedsearch.php").strip()
    wm_url = str(arch.get("wikimedia_commons") or "https://commons.wikimedia.org/w/api.php").strip()
    arch["archive_org"] = ao_url
    arch["wikimedia_commons"] = wm_url

    ao_node = arch.get("archive_org_node")
    if not isinstance(ao_node, dict) or not ao_node.get("host"):
        ao_node = decompose_endpoint_url(ao_url, default_name="Internet Archive", default_protocol="https")
    ao_node["enabled"] = arch.get("archive_org_enabled", ao_node.get("enabled", True)) is not False
    ao_node.setdefault("use_api_key", False)
    ao_node.setdefault("api_key", "")
    ao_node["url"] = ao_node.get("url") or build_endpoint_url(
        ao_node.get("protocol", "https"), ao_node.get("host", "archive.org"), ao_node.get("port", ""), ao_node.get("path", "")
    )
    arch["archive_org_node"] = ao_node
    arch["archive_org_enabled"] = bool(ao_node["enabled"])

    wm_node = arch.get("wikimedia_node")
    if not isinstance(wm_node, dict) or not wm_node.get("host"):
        wm_node = decompose_endpoint_url(wm_url, default_name="Wikimedia Commons", default_protocol="https")
    wm_node["enabled"] = arch.get("wikimedia_enabled", wm_node.get("enabled", True)) is not False
    wm_node.setdefault("use_api_key", False)
    wm_node.setdefault("api_key", "")
    wm_node["url"] = wm_node.get("url") or build_endpoint_url(
        wm_node.get("protocol", "https"), wm_node.get("host", "commons.wikimedia.org"), wm_node.get("port", ""), wm_node.get("path", "")
    )
    arch["wikimedia_node"] = wm_node
    arch["wikimedia_enabled"] = bool(wm_node["enabled"])

    custom_arch = arch.get("custom_archives", [])
    if not isinstance(custom_arch, list):
        custom_arch = []
    for ca in custom_arch:
        if isinstance(ca, dict):
            ca.setdefault("use_api_key", False)
            ca.setdefault("api_key", "")
            ca.setdefault("category", "general")
            if not ca.get("url") and ca.get("host"):
                ca["url"] = build_endpoint_url(ca.get("protocol", "https"), ca.get("host", ""), ca.get("port", ""), ca.get("path", ""))
    arch["custom_archives"] = custom_arch

    return merged


def update_endpoints(updates: Dict[str, Any]) -> bool:
    """Updates the endpoints section in search config, ensuring structured and URL fields stay in sync."""
    try:
        from hecos.modules.net_search.search.config import update_search_config
    except (ImportError, ValueError):
        from .config import update_search_config

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
            url = li.get("url") or build_endpoint_url(li.get("protocol", "http"), li.get("host", "127.0.0.1"), li.get("port", "8889"), li.get("path", ""))
            li["url"] = url
            li["use_api_key"] = bool(li.get("use_api_key", False))
            li["api_key"] = str(li.get("api_key", "")).strip()
            updates["searxng"]["local_url"] = url

        if "engines" in updates["searxng"] and isinstance(updates["searxng"]["engines"], list):
            engines = []
            for item in updates["searxng"]["engines"]:
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("id") or "").strip().lower()
                    if name:
                        engines.append({
                            "id": item.get("id") or name,
                            "name": name,
                            "label": str(item.get("label") or name.capitalize()).strip(),
                            "category": str(item.get("category", "general")).strip(),
                            "enabled": item.get("enabled", True) is not False
                        })
            updates["searxng"]["engines"] = engines
            try:
                from .components.searxng_component import update_searxng_engines
                update_searxng_engines(engines)
            except Exception as se:
                logger.warning(f"Could not sync SearXNG settings.yml: {se}")

    if "archives" in updates and isinstance(updates["archives"], dict):
        ua = updates["archives"]
        if isinstance(ua.get("archive_org_node"), dict):
            ao = ua["archive_org_node"]
            ao_url = ao.get("url") or build_endpoint_url(
                ao.get("protocol", "https"), ao.get("host", "archive.org"), ao.get("port", ""), ao.get("path", "")
            )
            ao["url"] = ao_url
            ao["use_api_key"] = bool(ao.get("use_api_key", False))
            ao["api_key"] = str(ao.get("api_key", "")).strip()
            ao["enabled"] = ao.get("enabled", True) is not False
            if ao_url:
                ua["archive_org"] = ao_url
            ua["archive_org_enabled"] = ao["enabled"]
        if isinstance(ua.get("wikimedia_node"), dict):
            wm = ua["wikimedia_node"]
            wm_url = wm.get("url") or build_endpoint_url(
                wm.get("protocol", "https"), wm.get("host", "commons.wikimedia.org"), wm.get("port", ""), wm.get("path", "")
            )
            wm["url"] = wm_url
            wm["use_api_key"] = bool(wm.get("use_api_key", False))
            wm["api_key"] = str(wm.get("api_key", "")).strip()
            wm["enabled"] = wm.get("enabled", True) is not False
            if wm_url:
                ua["wikimedia_commons"] = wm_url
            ua["wikimedia_enabled"] = wm["enabled"]
        if isinstance(ua.get("custom_archives"), list):
            clean_ca = []
            for item in ua["custom_archives"]:
                if isinstance(item, dict):
                    url = item.get("url") or build_endpoint_url(
                        item.get("protocol", "https"), item.get("host", ""), item.get("port", ""), item.get("path", "")
                    )
                    item["url"] = url
                    item["use_api_key"] = bool(item.get("use_api_key", False))
                    item["api_key"] = str(item.get("api_key", "")).strip()
                    item["category"] = str(item.get("category") or "general").strip().lower()
                    if url or item.get("host"):
                        clean_ca.append(item)
            ua["custom_archives"] = clean_ca

    if "custom_stream_nodes" in updates and isinstance(updates["custom_stream_nodes"], list):
        clean_csn = []
        for item in updates["custom_stream_nodes"]:
            if isinstance(item, dict):
                url = item.get("url") or build_endpoint_url(
                    item.get("protocol", "https"),
                    item.get("host", ""),
                    item.get("port", ""),
                    item.get("path", ""),
                )
                item["url"] = url
                item["use_api_key"] = bool(item.get("use_api_key", False))
                item["api_key"] = str(item.get("api_key", "")).strip()
                item["category"] = str(item.get("category") or "tv").strip().lower()
                item["country"] = str(item.get("country") or "INT").strip().upper()
                item["enabled"] = item.get("enabled", True) is not False
                if url or item.get("host"):
                    clean_csn.append(item)
        updates["custom_stream_nodes"] = clean_csn

    def _merge(dest: dict, src: dict):
        for k, v in src.items():
            if isinstance(v, dict) and k in dest and isinstance(dest[k], dict):
                _merge(dest[k], v)
            else:
                dest[k] = v

    _merge(current_endpoints, updates)
    return update_search_config({"endpoints": current_endpoints})


def get_archive_endpoint(key: str) -> tuple[bool, str, Dict[str, str]]:
    """Returns `(enabled, url, auth_headers)` for a built-in archive (`archive_org` | `wikimedia_commons`)."""
    try:
        from hecos.modules.net_search.search.config import get_search_config
    except (ImportError, ValueError):
        from .config import get_search_config

    arch = get_search_config().get("endpoints", {}).get("archives", {})
    if key == "wikimedia_commons":
        default_url = "https://commons.wikimedia.org/w/api.php"
        node = arch.get("wikimedia_node") if isinstance(arch.get("wikimedia_node"), dict) else {}
        enabled = arch.get("wikimedia_enabled", node.get("enabled", True)) is not False
        url = str(node.get("url") or arch.get("wikimedia_commons") or default_url).strip()
    else:
        default_url = "https://archive.org/advancedsearch.php"
        node = arch.get("archive_org_node") if isinstance(arch.get("archive_org_node"), dict) else {}
        enabled = arch.get("archive_org_enabled", node.get("enabled", True)) is not False
        url = str(node.get("url") or arch.get("archive_org") or default_url).strip()

    headers: Dict[str, str] = {}
    if node.get("use_api_key") and node.get("api_key"):
        token = str(node["api_key"]).strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-API-Key"] = token
    return enabled, url, headers


def get_engine_auth_headers(engine_key: str, sub_key: str = "onion") -> Dict[str, str]:
    """Retrieves HTTP authentication headers (Bearer and X-API-Key) if configured and enabled for this engine."""
    try:
        from hecos.modules.net_search.search.config import get_search_config
    except (ImportError, ValueError):
        from .config import get_search_config

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
    try:
        from hecos.modules.net_search.search.config import update_search_config, _DEFAULT_SEARCH_CONFIG
    except (ImportError, ValueError):
        from .config import update_search_config, _DEFAULT_SEARCH_CONFIG

    defaults = json.loads(json.dumps(_DEFAULT_SEARCH_CONFIG.get("endpoints", {})))
    defaults.setdefault("searxng", {})["fallbacks"] = json.loads(json.dumps(DEFAULT_SEARXNG_FALLBACKS))
    return update_search_config({"endpoints": defaults})

