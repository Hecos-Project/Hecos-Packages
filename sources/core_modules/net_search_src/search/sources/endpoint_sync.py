"""
search/sources/endpoint_sync.py
Endpoint pool deduplication merge, source cleanup purge, and source-level toggle helpers.
"""
from __future__ import annotations

from typing import Any, Dict, List

try:
    from hecos.modules.net_search.search.endpoints_config import get_endpoints, update_endpoints
except (ImportError, ValueError):
    from ..endpoints_config import get_endpoints, update_endpoints

from .dedup import collect_existing_keys, normalize_candidate


def merge_candidates_into_endpoints(
    raw_candidates: List[Dict[str, Any]],
    default_pool: str = "auto",
    source_id: str = "",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Deduplicates `raw_candidates` against all existing endpoints and merges new entries cleanly.
    When `dry_run=True`, computes full statistics and previews without mutating configuration.
    """
    endpoints = get_endpoints()
    existing = collect_existing_keys(endpoints)
    seen_url_keys = set(existing["url_keys"])
    seen_engine_keys = set(existing["engine_keys"])

    added_by_pool: Dict[str, List[Dict[str, Any]]] = {
        "searxng_engines": [],
        "searxng_fallbacks": [],
        "custom_nodes": [],
        "custom_onion_engines": [],
        "custom_clear_engines": [],
    }
    skipped_duplicates = 0
    invalid_count = 0

    for raw in raw_candidates:
        norm = normalize_candidate(raw, default_pool=default_pool, source_id=source_id)
        if not norm:
            invalid_count += 1
            continue
        pool, item, keys = norm

        target_seen = seen_engine_keys if pool == "searxng_engines" else seen_url_keys
        if any(k in target_seen for k in keys):
            skipped_duplicates += 1
            continue
        target_seen.update(keys)
        added_by_pool[pool].append(item)

    total_added = sum(len(v) for v in added_by_pool.values())
    counts_by_pool = {k: len(v) for k, v in added_by_pool.items() if v}

    if not dry_run and total_added > 0:
        updates: Dict[str, Any] = {}
        sx_updates: Dict[str, Any] = {}

        if added_by_pool["searxng_engines"]:
            cur_eng = list(endpoints.get("searxng", {}).get("engines", []))
            sx_updates["engines"] = cur_eng + added_by_pool["searxng_engines"]

        if added_by_pool["searxng_fallbacks"]:
            cur_fb = list(endpoints.get("searxng", {}).get("fallbacks", []))
            sx_updates["fallbacks"] = cur_fb + added_by_pool["searxng_fallbacks"]

        if sx_updates:
            updates["searxng"] = sx_updates

        for list_pool in ("custom_nodes", "custom_onion_engines", "custom_clear_engines"):
            if added_by_pool[list_pool]:
                cur_list = list(endpoints.get(list_pool, []))
                updates[list_pool] = cur_list + added_by_pool[list_pool]

        update_endpoints(updates)

    preview_items = []
    if dry_run:
        for pool, items in added_by_pool.items():
            for it in items[:25]:
                preview_items.append({
                    "pool": pool,
                    "name": it.get("label") or it.get("name") or it.get("id", ""),
                    "url": it.get("search_template") or it.get("url") or it.get("name", ""),
                })

    return {
        "parsed": len(raw_candidates),
        "added": total_added,
        "skipped_duplicates": skipped_duplicates,
        "invalid": invalid_count,
        "by_pool": counts_by_pool,
        "preview": preview_items[:50],
    }


def purge_endpoints_for_source(source_id: str) -> int:
    """Removes all endpoints tagged with `_source_id == source_id` across all pools."""
    if not source_id:
        return 0
    endpoints = get_endpoints()
    removed = 0
    updates: Dict[str, Any] = {}
    sx = endpoints.get("searxng", {})
    sx_updates: Dict[str, Any] = {}

    for sx_key in ("fallbacks", "engines"):
        lst = sx.get(sx_key)
        if isinstance(lst, list):
            kept = [x for x in lst if not (isinstance(x, dict) and x.get("_source_id") == source_id)]
            diff = len(lst) - len(kept)
            if diff > 0:
                removed += diff
                sx_updates[sx_key] = kept

    if sx_updates:
        updates["searxng"] = sx_updates

    for pool_key in ("custom_nodes", "custom_onion_engines", "custom_clear_engines"):
        cur = endpoints.get(pool_key, [])
        if isinstance(cur, list):
            kept = [x for x in cur if not (isinstance(x, dict) and x.get("_source_id") == source_id)]
            diff = len(cur) - len(kept)
            if diff > 0:
                removed += diff
                updates[pool_key] = kept

    if updates:
        update_endpoints(updates)
    return removed


def set_endpoints_enabled_for_source(source_id: str, enabled: bool) -> int:
    """Toggles `enabled` on all endpoints imported by `source_id`."""
    if not source_id:
        return 0
    endpoints = get_endpoints()
    changed = 0
    updates: Dict[str, Any] = {}
    sx = endpoints.get("searxng", {})
    sx_updates: Dict[str, Any] = {}

    for sx_key in ("fallbacks", "engines"):
        lst = sx.get(sx_key, [])
        if isinstance(lst, list):
            touched = False
            new_lst = []
            for item in lst:
                if isinstance(item, dict) and item.get("_source_id") == source_id:
                    item_copy = dict(item)
                    if item_copy.get("enabled", True) != enabled:
                        item_copy["enabled"] = enabled
                        touched = True
                        changed += 1
                    new_lst.append(item_copy)
                else:
                    new_lst.append(item)
            if touched:
                sx_updates[sx_key] = new_lst

    if sx_updates:
        updates["searxng"] = sx_updates

    for pool_key in ("custom_nodes", "custom_onion_engines", "custom_clear_engines"):
        lst = endpoints.get(pool_key, [])
        if isinstance(lst, list):
            touched = False
            new_lst = []
            for item in lst:
                if isinstance(item, dict) and item.get("_source_id") == source_id:
                    item_copy = dict(item)
                    if item_copy.get("enabled", True) != enabled:
                        item_copy["enabled"] = enabled
                        touched = True
                        changed += 1
                    new_lst.append(item_copy)
                else:
                    new_lst.append(item)
            if touched:
                updates[pool_key] = new_lst

    if updates:
        update_endpoints(updates)
    return changed
