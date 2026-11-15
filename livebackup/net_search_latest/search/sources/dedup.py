"""
search/sources/dedup.py
Canonical URL / Engine normalization and anti-duplication engine for Net Search sources.
"""
from __future__ import annotations

import re
import uuid
import urllib.parse
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

try:
    from hecos.modules.net_search.search.endpoints_config import (
        build_endpoint_url,
        decompose_endpoint_url,
    )
except (ImportError, ValueError):
    from ..endpoints_config import (
        build_endpoint_url,
        decompose_endpoint_url,
    )


_VALID_POOLS = {
    "searxng_engines",
    "searxng_fallbacks",
    "custom_nodes",
    "custom_onion_engines",
    "custom_clear_engines",
}

_SEARXNG_ENGINE_CATEGORIES = {
    "general",
    "news",
    "images",
    "videos",
    "music",
    "science",
    "it",
    "social media",
    "files",
    "other",
    "map",
}


def normalize_search_template(template: str) -> str:
    """Normalizes OpenSearch or custom query templates into Hecos `{q}` format."""
    tmpl = (template or "").strip()
    if not tmpl:
        return ""
    tmpl = re.sub(r"\{searchTerms\??\}", "{q}", tmpl, flags=re.IGNORECASE)
    # Remove optional OpenSearch tokens like &startPage={startPage?} or {language?}
    tmpl = re.sub(r"[?&][a-zA-Z0-9_.-]+=\{[a-zA-Z0-9_.:-]+\?\}", "", tmpl)
    tmpl = re.sub(r"\{[a-zA-Z0-9_.:-]+\?\}", "", tmpl)
    # Clean dangling '?' or '&' left by removed optional params
    tmpl = re.sub(r"\?&+", "?", tmpl).rstrip("?&")
    return tmpl


def is_onion_url(url_or_host: str) -> bool:
    return ".onion" in (url_or_host or "").lower()


def canonical_engine_key(name_or_id: str) -> str:
    """Canonical key for SearXNG engine adapter names/IDs."""
    return re.sub(r"[\s_\-]+", "_", (name_or_id or "").strip().lower()).strip("_")


def canonical_url_key(url_or_template: str, protocol: str = "", host: str = "", port: Any = "", path: str = "") -> str:
    """
    Produces a canonical deduplication key from a URL, template, or decomposed fields.
    Ignores scheme casing, default ports (80/443), trailing slashes, and {searchTerms}/{q} differences.
    """
    raw = (url_or_template or "").strip()
    if not raw and host:
        raw = build_endpoint_url(protocol or "https", host, port, path)
    if not raw:
        return ""

    if "://" not in raw:
        raw = f"{protocol or 'https'}://{raw}"

    try:
        parsed = urllib.parse.urlsplit(raw)
        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            return ""
        scheme = (parsed.scheme or "https").lower()
        eff_port = ""
        if parsed.port is not None:
            if not ((scheme == "http" and parsed.port == 80) or (scheme == "https" and parsed.port == 443)):
                eff_port = f":{parsed.port}"
        norm_path = (parsed.path or "").rstrip("/")
        norm_query = normalize_search_template(parsed.query).lower() if parsed.query else ""
        key = f"{hostname}{eff_port}{norm_path}"
        if norm_query:
            key = f"{key}?{norm_query}"
        return key
    except Exception:
        return raw.strip().rstrip("/").lower()


def _extract_item_url_keys(item: Any) -> List[str]:
    """Extracts all canonical URL keys represented by an existing endpoint config entry."""
    keys: List[str] = []
    if isinstance(item, str):
        k = canonical_url_key(item)
        if k:
            keys.append(k)
        return keys
    if not isinstance(item, dict):
        return keys

    for field in ("url", "onion_url", "clearnet_url", "torch_onion", "ddg_onion", "search_template"):
        val = item.get(field)
        if isinstance(val, str) and val.strip():
            k = canonical_url_key(val.strip())
            if k and k not in keys:
                keys.append(k)

    if item.get("host"):
        k = canonical_url_key(
            "",
            protocol=str(item.get("protocol", "https")),
            host=str(item.get("host", "")),
            port=item.get("port", ""),
            path=str(item.get("path", "")),
        )
        if k and k not in keys:
            keys.append(k)

    # Also add base host+path without query if search_template contains a default /search?q={q}
    tmpl = str(item.get("search_template") or "").strip()
    if tmpl and ("{q}" in tmpl or "{searchterms}" in tmpl.lower()):
        base_only = tmpl.split("?", 1)[0]
        bk = canonical_url_key(base_only)
        if bk and bk not in keys:
            keys.append(bk)

    return keys


def collect_existing_keys(endpoints_cfg: Dict[str, Any]) -> Dict[str, Set[str]]:
    """
    Collects canonical deduplication keys across ALL configured endpoint pools
    so duplicates are never added regardless of pool.
    """
    url_keys: Set[str] = set()
    engine_keys: Set[str] = set()

    def _add_urls(items: Iterable[Any]):
        for it in items:
            for k in _extract_item_url_keys(it):
                url_keys.add(k)

    sx = endpoints_cfg.get("searxng", {})
    if isinstance(sx, dict):
        if sx.get("local_url"):
            _add_urls([sx.get("local_url")])
        if isinstance(sx.get("local_instance"), dict):
            _add_urls([sx["local_instance"]])
        if isinstance(sx.get("fallbacks"), list):
            _add_urls(sx["fallbacks"])
        if isinstance(sx.get("engines"), list):
            for eng in sx["engines"]:
                if isinstance(eng, dict):
                    for field in ("id", "name"):
                        ek = canonical_engine_key(str(eng.get(field) or ""))
                        if ek:
                            engine_keys.add(ek)
                elif isinstance(eng, str):
                    ek = canonical_engine_key(eng)
                    if ek:
                        engine_keys.add(ek)

    for list_key in ("custom_nodes", "custom_onion_engines", "custom_clear_engines"):
        entries = endpoints_cfg.get(list_key, [])
        if isinstance(entries, list):
            _add_urls(entries)

    for dark_key in (
        "dark_ahmia",
        "dark_torch",
        "dark_haystak",
        "dark_onionland",
        "dark_excavator",
        "dark_phobos",
        "dark_tor66",
        "dark_danieltore",
    ):
        dk_val = endpoints_cfg.get(dark_key)
        if isinstance(dk_val, dict):
            _add_urls([dk_val])
            for sub in dk_val.values():
                if isinstance(sub, (dict, str)):
                    _add_urls([sub])

    archives = endpoints_cfg.get("archives")
    if isinstance(archives, dict):
        _add_urls(archives.values())

    ms = endpoints_cfg.get("media_streams")
    if isinstance(ms, dict):
        _add_urls(ms.values())

    return {"url_keys": url_keys, "engine_keys": engine_keys}


def _infer_target_pool(raw: Dict[str, Any], default_pool: str) -> str:
    if default_pool in _VALID_POOLS:
        return default_pool

    explicit = str(raw.get("target_pool") or raw.get("pool") or "").strip().lower()
    if explicit in _VALID_POOLS:
        return explicit

    kind = str(raw.get("kind") or raw.get("type") or "").strip().lower()
    url_hint = str(
        raw.get("url")
        or raw.get("onion_url")
        or raw.get("search_template")
        or raw.get("host")
        or ""
    ).strip()

    if kind in ("searxng_engine", "sx_engine", "adapter") or (not url_hint and (raw.get("engine") or raw.get("name"))):
        return "searxng_engines"

    if is_onion_url(url_hint) or kind in ("onion", "tor", "dark"):
        return "custom_onion_engines"

    if kind in ("searxng_node", "searxng_fallback", "searxng", "fallback", "mirror"):
        return "searxng_fallbacks"

    if kind in ("custom_node", "node"):
        return "custom_nodes"

    search_tmpl = str(raw.get("search_template") or "")
    if "{q}" in search_tmpl or "{searchterms}" in search_tmpl.lower() or "{q}" in url_hint or "{searchterms}" in url_hint.lower():
        return "custom_clear_engines"

    if kind in ("opensearch", "clear_engine", "web_engine", "clear"):
        return "custom_clear_engines"

    return "searxng_fallbacks"


def normalize_candidate(
    raw: Dict[str, Any],
    default_pool: str = "auto",
    source_id: str = "",
) -> Optional[Tuple[str, Dict[str, Any], List[str]]]:
    """
    Normalizes a raw parsed candidate into `(target_pool, normalized_dict, dedup_keys)`.
    Returns None if candidate lacks valid address/identifier.
    """
    if not isinstance(raw, dict):
        return None

    pool = _infer_target_pool(raw, default_pool)
    enabled = raw.get("enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in ("0", "false", "no", "off", "disabled")
    else:
        enabled = bool(enabled)

    if pool == "searxng_engines":
        eng_name = str(raw.get("engine") or raw.get("name") or raw.get("id") or "").strip().lower()
        if not eng_name:
            return None
        eng_id = str(raw.get("id") or canonical_engine_key(eng_name)).strip().lower()
        label = str(raw.get("label") or raw.get("title") or eng_name.replace("_", " ").title()).strip()
        cat_raw = raw.get("category") or raw.get("categories") or "general"
        if isinstance(cat_raw, list):
            cat_raw = cat_raw[0] if cat_raw else "general"
        category = str(cat_raw).split(",")[0].strip().lower() or "general"
        if category not in _SEARXNG_ENGINE_CATEGORIES:
            category = "general"

        item: Dict[str, Any] = {
            "id": eng_id,
            "name": eng_name,
            "label": label,
            "category": category,
            "enabled": enabled,
        }
        if source_id:
            item["_source_id"] = source_id
        keys = [k for k in {canonical_engine_key(eng_name), canonical_engine_key(eng_id)} if k]
        return pool, item, keys

    # URL-based candidate
    raw_template = normalize_search_template(str(raw.get("search_template") or raw.get("template") or ""))
    raw_url = str(
        raw.get("url")
        or raw.get("onion_url")
        or raw.get("clearnet_url")
        or raw_template
        or ""
    ).strip()

    default_proto = "http" if (pool == "custom_onion_engines" or is_onion_url(raw_url or str(raw.get("host", "")))) else "https"
    use_api_key = bool(raw.get("use_api_key", False) or raw.get("api_key"))
    api_key = str(raw.get("api_key") or "").strip()
    name = str(raw.get("name") or raw.get("title") or raw.get("label") or "").strip()

    if raw_url:
        # Preserve decomposed host/port/path cleanly (strip query params only from template vs path if needed)
        base_for_decompose = raw_url
        if not raw.get("host"):
            item = decompose_endpoint_url(
                base_for_decompose,
                default_name=name,
                default_protocol=default_proto,
                use_api_key=use_api_key,
                api_key=api_key,
            )
        else:
            proto = str(raw.get("protocol") or default_proto).strip().lower().rstrip(":/")
            host = str(raw.get("host") or "").strip()
            port = str(raw.get("port") or "").strip()
            path = str(raw.get("path") or "").strip()
            item = {
                "name": name or host,
                "protocol": proto,
                "host": host,
                "port": port,
                "path": path,
                "url": build_endpoint_url(proto, host, port, path) or raw_url,
                "enabled": enabled,
                "use_api_key": use_api_key,
                "api_key": api_key,
            }
    elif raw.get("host"):
        proto = str(raw.get("protocol") or default_proto).strip().lower().rstrip(":/")
        host = str(raw.get("host") or "").strip()
        port = str(raw.get("port") or "").strip()
        path = str(raw.get("path") or "").strip()
        url = build_endpoint_url(proto, host, port, path)
        if not url:
            return None
        item = {
            "name": name or host,
            "protocol": proto,
            "host": host,
            "port": port,
            "path": path,
            "url": url,
            "enabled": enabled,
            "use_api_key": use_api_key,
            "api_key": api_key,
        }
    else:
        return None

    if not item.get("host") or not item.get("url"):
        return None

    item["id"] = str(raw.get("id") or f"ep_{uuid.uuid4().hex[:10]}")
    item["enabled"] = enabled
    if name:
        item["name"] = name
    if raw_template:
        item["search_template"] = raw_template
    elif "{q}" in item["url"]:
        item["search_template"] = item["url"]
    elif pool in ("custom_onion_engines", "custom_clear_engines"):
        base_url = item["url"].rstrip("/")
        item["search_template"] = f"{base_url}/search?q={{q}}" if not base_url.endswith("/search") else f"{base_url}?q={{q}}"

    if pool == "custom_onion_engines":
        item["onion_url"] = item["url"]

    category = str(raw.get("category") or ("onion" if pool == "custom_onion_engines" else "general")).strip().lower()
    item["category"] = category
    if source_id:
        item["_source_id"] = source_id

    keys = _extract_item_url_keys(item)
    if not keys:
        return None
    return pool, item, keys

