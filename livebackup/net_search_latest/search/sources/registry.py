"""
search/sources/registry.py
CRUD persistence for automated/manual search engine compilation sources and built-in presets.
"""
from __future__ import annotations

import copy
import time
import uuid
from typing import Any, Dict, List, Optional

try:
    from hecos.modules.net_search.search.config import get_search_config, update_search_config
except (ImportError, ValueError):
    from ..config import get_search_config, update_search_config

from .fetcher import normalize_source_url


_DEFAULT_SOURCE_TEMPLATE: Dict[str, Any] = {
    "id": "",
    "name": "",
    "location": "",
    "source_type": "url",      # url | github | file | opensearch | onion
    "format": "auto",          # auto | json | csv | yaml | sqlite | opensearch | onion_list
    "target_pool": "auto",     # auto | custom_clear_engines | custom_onion_engines | custom_nodes | searxng_fallbacks | searxng_engines
    "enabled": True,
    "auto_update": True,
    "interval_hours": 12,
    "use_tor": False,
    "etag": "",
    "last_modified": "",
    "last_hash": "",
    "last_sync": 0,
    "last_status": "never",
    "last_error": "",
    "stats": {
        "parsed": 0,
        "added": 0,
        "skipped_duplicates": 0,
        "invalid": 0,
    },
}


def get_preset_sources() -> List[Dict[str, Any]]:
    """Curated list of well-known open directories & OpenSearch feeds users can add in one click."""
    return [
        {
            "preset_id": "searx_space_instances",
            "name": "SearXNG Public Instances (searx.space)",
            "description": "Official live JSON directory of public Clearnet & .onion SearXNG instances.",
            "location": "https://searx.space/data/instances.json",
            "source_type": "url",
            "format": "json",
            "target_pool": "auto",
            "use_tor": False,
            "auto_update": True,
            "interval_hours": 24,
        },
        {
            "preset_id": "opensearch_wikipedia",
            "name": "Wikipedia (OpenSearch XML)",
            "description": "Direct Wikipedia OpenSearch template.",
            "location": "https://en.wikipedia.org/w/opensearch_desc.php",
            "source_type": "opensearch",
            "format": "opensearch",
            "target_pool": "custom_clear_engines",
            "use_tor": False,
            "auto_update": False,
            "interval_hours": 168,
        },
        {
            "preset_id": "opensearch_archwiki",
            "name": "ArchWiki (OpenSearch XML)",
            "description": "Technical Linux & software documentation via OpenSearch.",
            "location": "https://wiki.archlinux.org/opensearch_desc.php",
            "source_type": "opensearch",
            "format": "opensearch",
            "target_pool": "custom_clear_engines",
            "use_tor": False,
            "auto_update": False,
            "interval_hours": 168,
        },
        {
            "preset_id": "opensearch_internet_archive",
            "name": "Internet Archive (OpenSearch Auto-Discover)",
            "description": "Auto-discovers Archive.org OpenSearch XML from homepage.",
            "location": "https://archive.org/",
            "source_type": "opensearch",
            "format": "opensearch",
            "target_pool": "custom_clear_engines",
            "use_tor": False,
            "auto_update": False,
            "interval_hours": 168,
        },
    ]


def list_sources() -> List[Dict[str, Any]]:
    cfg = get_search_config()
    raw_sources = cfg.get("sources", [])
    if not isinstance(raw_sources, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw_sources:
        if not isinstance(item, dict):
            continue
        merged = copy.deepcopy(_DEFAULT_SOURCE_TEMPLATE)
        merged.update(item)
        if not isinstance(merged.get("stats"), dict):
            merged["stats"] = copy.deepcopy(_DEFAULT_SOURCE_TEMPLATE["stats"])
        out.append(merged)
    return out


def get_source(source_id: str) -> Optional[Dict[str, Any]]:
    for s in list_sources():
        if s.get("id") == source_id:
            return s
    return None


def _save_sources(sources: List[Dict[str, Any]]) -> bool:
    return update_search_config({"sources": sources})


def add_or_update_source(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Adds a new compilation source or updates an existing one by id or normalized location."""
    sources = list_sources()
    src_id = str(payload.get("id") or "").strip()
    location = str(payload.get("location") or "").strip()
    norm_loc = normalize_source_url(location) if location else ""

    existing_idx = -1
    for idx, s in enumerate(sources):
        if src_id and s.get("id") == src_id:
            existing_idx = idx
            break
        if norm_loc and normalize_source_url(s.get("location", "")) == norm_loc:
            existing_idx = idx
            break

    if existing_idx >= 0:
        entry = sources[existing_idx]
    else:
        entry = copy.deepcopy(_DEFAULT_SOURCE_TEMPLATE)
        entry["id"] = src_id or f"src_{uuid.uuid4().hex[:10]}"
        entry["created_at"] = int(time.time())

    for field in ("name", "location", "source_type", "format", "target_pool"):
        if field in payload and payload[field] is not None:
            entry[field] = str(payload[field]).strip()

    if not entry.get("name"):
        loc_display = entry.get("location") or entry["id"]
        entry["name"] = loc_display.split("://", 1)[-1][:48]

    if "enabled" in payload:
        entry["enabled"] = bool(payload["enabled"])
    if "auto_update" in payload:
        entry["auto_update"] = bool(payload["auto_update"])
    if "use_tor" in payload:
        entry["use_tor"] = bool(payload["use_tor"])
    elif ".onion" in entry.get("location", "").lower():
        entry["use_tor"] = True

    if "interval_hours" in payload:
        try:
            entry["interval_hours"] = max(1, min(720, int(payload["interval_hours"])))
        except (TypeError, ValueError):
            entry["interval_hours"] = 12

    if "github.com" in entry.get("location", "").lower() and entry.get("source_type") in ("", "url"):
        entry["source_type"] = "github"
    elif ".onion" in entry.get("location", "").lower() and entry.get("source_type") in ("", "url"):
        entry["source_type"] = "onion"

    if existing_idx >= 0:
        sources[existing_idx] = entry
    else:
        sources.append(entry)

    _save_sources(sources)
    return entry


def update_source_status(source_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sources = list_sources()
    for idx, s in enumerate(sources):
        if s.get("id") == source_id:
            s.update(updates)
            sources[idx] = s
            _save_sources(sources)
            return s
    return None


def delete_source_record(source_id: str) -> bool:
    sources = list_sources()
    filtered = [s for s in sources if s.get("id") != source_id]
    if len(filtered) == len(sources):
        return False
    return _save_sources(filtered)

