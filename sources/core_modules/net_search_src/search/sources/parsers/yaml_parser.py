"""
search/sources/parsers/yaml_parser.py
Safe YAML parser supporting SearXNG settings.yml engines and structured endpoint lists.
"""
from __future__ import annotations

from typing import Any, Dict, List
import yaml


def parse_yaml(raw_bytes: bytes, source_url: str = "") -> List[Dict[str, Any]]:
    text = raw_bytes.decode("utf-8", errors="replace").strip()
    if not text:
        return []
    data = yaml.safe_load(text)
    candidates: List[Dict[str, Any]] = []

    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, str) and entry.strip():
                candidates.append({"url": entry.strip()})
            elif isinstance(entry, dict):
                candidates.append(dict(entry))
        return candidates

    if not isinstance(data, dict):
        return candidates

    # SearXNG settings.yml style: {"engines": [{"name": ..., "engine": ..., "categories": ..., "disabled": ...}]}
    engines = data.get("engines")
    if isinstance(engines, list):
        for eng in engines:
            if isinstance(eng, dict):
                has_url = bool(eng.get("url") or eng.get("host") or eng.get("search_template") or eng.get("onion_url") or eng.get("base_url"))
                item = dict(eng)
                if "base_url" in item and not item.get("url"):
                    item["url"] = item["base_url"]
                if "disabled" in item and "enabled" not in item:
                    item["enabled"] = not bool(item["disabled"])
                if not has_url:
                    item.setdefault("kind", "searxng_engine")
                    item.setdefault("target_pool", "searxng_engines")
                candidates.append(item)
            elif isinstance(eng, str) and eng.strip():
                candidates.append({"name": eng.strip(), "kind": "searxng_engine", "target_pool": "searxng_engines"})

    for key, pool, kind in (
        ("fallbacks", "searxng_fallbacks", "searxng_node"),
        ("nodes", "custom_nodes", "custom_node"),
        ("custom_nodes", "custom_nodes", "custom_node"),
        ("onion_engines", "custom_onion_engines", "onion"),
        ("custom_onion_engines", "custom_onion_engines", "onion"),
        ("custom_clear_engines", "custom_clear_engines", "clear_engine"),
        ("sources", "auto", ""),
        ("urls", "auto", ""),
    ):
        val = data.get(key)
        if isinstance(val, list):
            for entry in val:
                if isinstance(entry, str) and entry.strip():
                    item = {"url": entry.strip()}
                    if kind:
                        item["kind"] = kind
                    if pool != "auto":
                        item["target_pool"] = pool
                    candidates.append(item)
                elif isinstance(entry, dict):
                    item = dict(entry)
                    if kind and not item.get("kind"):
                        item["kind"] = kind
                    if pool != "auto" and not item.get("target_pool"):
                        item["target_pool"] = pool
                    candidates.append(item)

    if not candidates and (data.get("url") or data.get("host") or data.get("search_template")):
        candidates.append(dict(data))

    return candidates

