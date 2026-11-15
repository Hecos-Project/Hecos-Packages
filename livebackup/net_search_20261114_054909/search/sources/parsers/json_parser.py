"""
search/sources/parsers/json_parser.py
Parser for JSON engine lists, SearXNG instance directories (searx.space), and Hecos endpoint exports.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List


def _item_from_dict(d: Dict[str, Any], default_kind: str = "") -> Dict[str, Any]:
    out = dict(d)
    if default_kind and not out.get("kind") and not out.get("type"):
        out["kind"] = default_kind
    return out


def parse_json(raw_bytes: bytes, source_url: str = "") -> List[Dict[str, Any]]:
    text = raw_bytes.decode("utf-8", errors="replace").strip()
    if not text:
        return []
    data = json.loads(text)
    candidates: List[Dict[str, Any]] = []

    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, str) and entry.strip():
                candidates.append({"url": entry.strip()})
            elif isinstance(entry, dict):
                candidates.append(_item_from_dict(entry))
        return candidates

    if not isinstance(data, dict):
        return candidates

    # 1. searx.space format: {"instances": {"https://...": {network, version, ...}}}
    if isinstance(data.get("instances"), dict):
        for inst_url, meta in data["instances"].items():
            if not isinstance(inst_url, str) or not inst_url.startswith(("http://", "https://")):
                continue
            meta_dict = meta if isinstance(meta, dict) else {}
            # Skip explicitly dead/error instances when status metadata is provided
            http_info = meta_dict.get("http") if isinstance(meta_dict.get("http"), dict) else {}
            if http_info.get("error"):
                continue
            is_tor = ".onion" in inst_url.lower() or str(meta_dict.get("network", "")).lower() == "tor"
            candidates.append({
                "name": meta_dict.get("name") or inst_url.split("://", 1)[-1].split("/", 1)[0],
                "url": inst_url.strip(),
                "kind": "onion" if is_tor else "searxng_node",
                "target_pool": "custom_onion_engines" if is_tor else "searxng_fallbacks",
                "enabled": True,
            })
        return candidates

    # 2. Hecos endpoints schema: {"endpoints": {...}} or direct pool keys
    root = data.get("endpoints") if isinstance(data.get("endpoints"), dict) else data
    pool_map = {
        "fallbacks": ("searxng_node", "searxng_fallbacks"),
        "custom_nodes": ("custom_node", "custom_nodes"),
        "custom_onion_engines": ("onion", "custom_onion_engines"),
        "custom_clear_engines": ("clear_engine", "custom_clear_engines"),
        "engines": ("searxng_engine", "searxng_engines"),
    }

    matched_hecos = False
    sx = root.get("searxng")
    if isinstance(sx, dict):
        for fb in sx.get("fallbacks", []) or []:
            matched_hecos = True
            if isinstance(fb, str):
                candidates.append({"url": fb, "kind": "searxng_node", "target_pool": "searxng_fallbacks"})
            elif isinstance(fb, dict):
                candidates.append({**fb, "kind": "searxng_node", "target_pool": "searxng_fallbacks"})
        for eng in sx.get("engines", []) or []:
            matched_hecos = True
            if isinstance(eng, str):
                candidates.append({"name": eng, "kind": "searxng_engine", "target_pool": "searxng_engines"})
            elif isinstance(eng, dict):
                candidates.append({**eng, "kind": "searxng_engine", "target_pool": "searxng_engines"})

    for key, (kind, pool) in pool_map.items():
        val = root.get(key)
        if isinstance(val, list):
            matched_hecos = True
            for entry in val:
                if isinstance(entry, str):
                    if key == "engines":
                        candidates.append({"name": entry, "kind": kind, "target_pool": pool})
                    else:
                        candidates.append({"url": entry, "kind": kind, "target_pool": pool})
                elif isinstance(entry, dict):
                    has_url = bool(entry.get("url") or entry.get("host") or entry.get("search_template") or entry.get("onion_url"))
                    eff_kind = entry.get("kind") or ("clear_engine" if (key == "engines" and has_url) else kind)
                    eff_pool = entry.get("target_pool") or ("custom_clear_engines" if (key == "engines" and has_url) else pool)
                    candidates.append({**entry, "kind": eff_kind, "target_pool": eff_pool})

    if matched_hecos:
        return candidates

    # 3. Generic wrapper keys
    for container_key in ("items", "nodes", "sources", "results", "data", "urls", "links"):
        val = data.get(container_key)
        if isinstance(val, list):
            for entry in val:
                if isinstance(entry, str) and entry.strip():
                    candidates.append({"url": entry.strip()})
                elif isinstance(entry, dict):
                    candidates.append(_item_from_dict(entry))
            return candidates

    # 4. Single object with URL or host
    if data.get("url") or data.get("host") or data.get("search_template") or data.get("onion_url"):
        candidates.append(_item_from_dict(data))

    return candidates

