"""
search/sources/updater.py
Synchronization, deduplication merge, dry-run preview, source cleanup, and raw import orchestrator.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from hecos.modules.net_search.search.endpoints_config import get_endpoints, update_endpoints
    from hecos.core.logging import logger as hecos_logger
except (ImportError, ValueError):
    from ..endpoints_config import get_endpoints, update_endpoints
    hecos_logger = logging.getLogger("browser.search.sources")

from .dedup import collect_existing_keys, normalize_candidate
from . import domain_store
from .fetcher import fetch_source
from .parsers import parse_payload
from .registry import (
    add_or_update_source,
    delete_source_record,
    get_source,
    list_sources,
    update_source_status,
)


_SYNC_LOCK = threading.Lock()


def _merge_candidates_into_endpoints(
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

        if pool == "searxng_engines":
            if any(k in seen_engine_keys for k in keys):
                skipped_duplicates += 1
                continue
            seen_engine_keys.update(keys)
            added_by_pool[pool].append(item)
        else:
            if any(k in seen_url_keys for k in keys):
                skipped_duplicates += 1
                continue
            seen_url_keys.update(keys)
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


def _apply_parsed_candidates(
    detected_fmt: str,
    raw_candidates: List[Dict[str, Any]],
    default_pool: str = "auto",
    source_id: str = "",
    dry_run: bool = False,
    url_hint: str = "",
) -> Dict[str, Any]:
    """Routes parsed candidates either to SQLite Domain Index or to endpoint config pools."""
    is_domain_pool = default_pool in ("domain_blocklist", "domain_allowlist", "domain_directory")
    if detected_fmt == "domain_list" or is_domain_pool:
        if default_pool == "domain_allowlist":
            role = "allowlist"
        elif default_pool == "domain_directory":
            role = "directory"
        elif default_pool == "domain_blocklist":
            role = "blocklist"
        else:
            first_pool = str(raw_candidates[0].get("target_pool", "")) if raw_candidates else ""
            if first_pool == "domain_allowlist" or "allow" in (url_hint or "").lower():
                role = "allowlist"
            else:
                role = "blocklist"

        domains = [
            str(c.get("domain") or c.get("host") or c.get("url") or "")
            for c in raw_candidates
            if isinstance(c, dict)
        ]
        parsed_valid, added, skipped = domain_store.insert_domains(
            source_id=source_id,
            role=role,
            domains=domains,
            category="adult" if "porn" in (url_hint or "").lower() else "general",
            dry_run=dry_run,
        )
        preview = []
        if dry_run:
            for d in domains[:15]:
                nd = domain_store.normalize_domain(d)
                if nd:
                    preview.append({"pool": f"domain_{role}", "name": nd, "url": f"sqlite://{role}/{nd}"})
        return {
            "parsed": parsed_valid,
            "added": added,
            "skipped_duplicates": skipped,
            "invalid": max(0, len(raw_candidates) - parsed_valid),
            "by_pool": {f"domain_{role}": added} if added else {},
            "preview": preview,
        }

    return _merge_candidates_into_endpoints(
        raw_candidates,
        default_pool=default_pool,
        source_id=source_id,
        dry_run=dry_run,
    )


def _purge_endpoints_for_source(source_id: str) -> int:
    """Removes all endpoints tagged with `_source_id == source_id` across all pools."""
    if not source_id:
        return 0
    endpoints = get_endpoints()
    removed = 0
    updates: Dict[str, Any] = {}
    sx = endpoints.get("searxng", {})
    sx_updates: Dict[str, Any] = {}

    if isinstance(sx.get("fallbacks"), list):
        kept = [x for x in sx["fallbacks"] if not (isinstance(x, dict) and x.get("_source_id") == source_id)]
        diff = len(sx["fallbacks"]) - len(kept)
        if diff > 0:
            removed += diff
            sx_updates["fallbacks"] = kept

    if isinstance(sx.get("engines"), list):
        kept = [x for x in sx["engines"] if not (isinstance(x, dict) and x.get("_source_id") == source_id)]
        diff = len(sx["engines"]) - len(kept)
        if diff > 0:
            removed += diff
            sx_updates["engines"] = kept

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


def _set_endpoints_enabled_for_source(source_id: str, enabled: bool) -> int:
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


def sync_source(source_id: str, force: bool = False, dry_run: bool = False) -> Dict[str, Any]:
    """Fetches, parses, deduplicates, and applies updates for a configured source."""
    src = get_source(source_id)
    if not src:
        return {"ok": False, "error": f"Source '{source_id}' not found."}

    with _SYNC_LOCK:
        now = int(time.time())
        fetch_res = fetch_source(
            src.get("location", ""),
            use_tor=bool(src.get("use_tor", False)),
            etag="" if (force or dry_run) else src.get("etag", ""),
            last_modified="" if (force or dry_run) else src.get("last_modified", ""),
            prefer_opensearch=(src.get("format") == "opensearch" or src.get("source_type") == "opensearch"),
        )

        if not fetch_res.ok:
            status = "skipped_tor_offline" if fetch_res.tor_offline else "error"
            if not dry_run:
                update_source_status(source_id, {
                    "last_sync": now,
                    "last_status": status,
                    "last_error": fetch_res.error,
                })
            return {"ok": False, "status": status, "error": fetch_res.error, "source": get_source(source_id)}

        if fetch_res.not_modified or (not force and not dry_run and fetch_res.sha256 and fetch_res.sha256 == src.get("last_hash")):
            tpool = src.get("target_pool", "auto")
            if tpool in ("domain_blocklist", "domain_allowlist", "domain_directory"):
                domain_store.set_source_role(source_id, tpool.replace("domain_", "", 1))
            update_source_status(source_id, {
                "last_sync": now,
                "last_status": "unchanged",
                "last_error": "",
                "etag": fetch_res.etag or src.get("etag", ""),
                "last_modified": fetch_res.last_modified or src.get("last_modified", ""),
            })
            return {
                "ok": True,
                "status": "unchanged",
                "stats": src.get("stats", {"parsed": 0, "added": 0, "skipped_duplicates": 0, "invalid": 0}),
                "source": get_source(source_id),
            }

        try:
            detected_fmt, raw_candidates = parse_payload(
                fetch_res.content,
                fmt=src.get("format", "auto"),
                filename=fetch_res.file_path or src.get("location", ""),
                url=fetch_res.resolved_url or src.get("location", ""),
                content_type=fetch_res.content_type,
                file_path=fetch_res.file_path,
            )
            stats = _apply_parsed_candidates(
                detected_fmt,
                raw_candidates,
                default_pool=src.get("target_pool", "auto"),
                source_id=source_id,
                dry_run=dry_run,
                url_hint=fetch_res.resolved_url or src.get("location", ""),
            )
        except Exception as e:
            err_msg = f"Parse/merge failed: {e}"
            hecos_logger.warning(f"[Sources] Sync failed for '{src.get('name')}': {err_msg}")
            if not dry_run:
                update_source_status(source_id, {
                    "last_sync": now,
                    "last_status": "error",
                    "last_error": err_msg,
                })
            return {"ok": False, "status": "error", "error": err_msg, "source": get_source(source_id)}

        if not dry_run:
            update_source_status(source_id, {
                "last_sync": now,
                "last_status": "ok",
                "last_error": "",
                "etag": fetch_res.etag,
                "last_modified": fetch_res.last_modified,
                "last_hash": fetch_res.sha256,
                "format": detected_fmt if src.get("format", "auto") == "auto" else src.get("format"),
                "stats": {
                    "parsed": stats["parsed"],
                    "added": stats["added"],
                    "skipped_duplicates": stats["skipped_duplicates"],
                    "invalid": stats["invalid"],
                },
            })
            hecos_logger.info(
                f"[Sources] Synced '{src.get('name')}' ({detected_fmt}): "
                f"+{stats['added']} added, {stats['skipped_duplicates']} duplicates skipped."
            )

        return {
            "ok": True,
            "status": "preview" if dry_run else "ok",
            "detected_format": detected_fmt,
            "stats": stats,
            "source": get_source(source_id),
        }


def sync_all_sources(force: bool = False, only_due: bool = False) -> Dict[str, Any]:
    """Synchronizes all enabled sources (optionally filtering by due auto_update interval)."""
    sources = list_sources()
    now = int(time.time())
    results: List[Dict[str, Any]] = []
    total_added = 0
    total_skipped = 0
    errors = 0

    for src in sources:
        if not src.get("enabled", True):
            continue
        if only_due:
            if not src.get("auto_update", True):
                continue
            interval_sec = max(1, int(src.get("interval_hours", 12))) * 3600
            last_sync = int(src.get("last_sync") or 0)
            if last_sync > 0 and (now - last_sync) < interval_sec:
                continue

        res = sync_source(src["id"], force=force, dry_run=False)
        results.append({
            "id": src["id"],
            "name": src.get("name", src["id"]),
            **res,
        })
        if res.get("ok"):
            st = res.get("stats") or {}
            total_added += int(st.get("added", 0))
            total_skipped += int(st.get("skipped_duplicates", 0))
        elif res.get("status") != "skipped_tor_offline":
            errors += 1

    return {
        "ok": True,
        "synced_count": len(results),
        "total_added": total_added,
        "total_skipped_duplicates": total_skipped,
        "errors": errors,
        "results": results,
    }


def remove_source(source_id: str) -> Dict[str, Any]:
    """Deletes a source and purges all endpoints and indexed domains originally imported from it."""
    with _SYNC_LOCK:
        removed_endpoints = _purge_endpoints_for_source(source_id)
        removed_domains = domain_store.remove_domains_for_source(source_id)
        deleted = delete_source_record(source_id)
        return {
            "ok": deleted,
            "removed_endpoints": removed_endpoints + removed_domains,
            "error": "" if deleted else f"Source '{source_id}' not found.",
        }


def toggle_source(source_id: str, enabled: Optional[bool] = None) -> Dict[str, Any]:
    """Enables or disables a source and toggles its managed endpoints and indexed domains accordingly."""
    src = get_source(source_id)
    if not src:
        return {"ok": False, "error": f"Source '{source_id}' not found."}
    new_state = (not bool(src.get("enabled", True))) if enabled is None else bool(enabled)
    with _SYNC_LOCK:
        updated = update_source_status(source_id, {"enabled": new_state})
        affected_ep = _set_endpoints_enabled_for_source(source_id, new_state)
        affected_dom = domain_store.set_source_enabled(source_id, new_state)
    return {"ok": True, "enabled": new_state, "affected_endpoints": affected_ep + affected_dom, "source": updated}


def import_raw_content(
    content_or_bytes: Any,
    fmt: str = "auto",
    filename: str = "",
    target_pool: str = "auto",
    source_name: str = "Manual Import",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Imports pasted text or uploaded file bytes (JSON, CSV, YAML, SQLite, OpenSearch XML, .onion list)."""
    raw_bytes = content_or_bytes if isinstance(content_or_bytes, (bytes, bytearray)) else str(content_or_bytes or "").encode("utf-8")
    if not raw_bytes.strip():
        return {"ok": False, "error": "Empty import content."}

    with _SYNC_LOCK:
        detected_fmt, raw_candidates = parse_payload(
            bytes(raw_bytes),
            fmt=fmt,
            filename=filename,
        )
        import uuid
        src_id = "" if dry_run else f"src_{uuid.uuid4().hex[:10]}"

        stats = _apply_parsed_candidates(
            detected_fmt,
            raw_candidates,
            default_pool=target_pool,
            source_id=src_id,
            dry_run=dry_run,
            url_hint=filename or source_name,
        )

        if not dry_run and stats["added"] > 0:
            add_or_update_source({
                "id": src_id,
                "name": source_name or filename or f"Import ({detected_fmt.upper()})",
                "location": filename or f"manual://{detected_fmt}/{int(time.time())}",
                "source_type": "file" if filename else "manual",
                "format": detected_fmt,
                "target_pool": target_pool,
                "enabled": True,
                "auto_update": False,
                "last_sync": int(time.time()),
                "last_status": "ok",
                "last_error": "",
                "stats": {
                    "parsed": stats["parsed"],
                    "added": stats["added"],
                    "skipped_duplicates": stats["skipped_duplicates"],
                    "invalid": stats["invalid"],
                },
            })
        elif not dry_run:
            src_id = ""

        return {
            "ok": True,
            "detected_format": detected_fmt,
            "source_id": src_id,
            "stats": stats,
        }


def preview_ad_hoc_source(location: str, fmt: str = "auto", target_pool: str = "auto", use_tor: bool = False) -> Dict[str, Any]:
    """Fetches and parses a URL or file path in dry-run mode without saving the source or endpoints."""
    fetch_res = fetch_source(
        location,
        use_tor=use_tor or (".onion" in (location or "").lower()),
        prefer_opensearch=(fmt == "opensearch"),
    )
    if not fetch_res.ok:
        return {"ok": False, "error": fetch_res.error, "tor_offline": fetch_res.tor_offline}
    detected_fmt, raw_candidates = parse_payload(
        fetch_res.content,
        fmt=fmt,
        filename=fetch_res.file_path or location,
        url=fetch_res.resolved_url or location,
        content_type=fetch_res.content_type,
        file_path=fetch_res.file_path,
    )
    stats = _apply_parsed_candidates(
        detected_fmt,
        raw_candidates,
        default_pool=target_pool,
        dry_run=True,
        url_hint=fetch_res.resolved_url or location,
    )
    return {
        "ok": True,
        "detected_format": detected_fmt,
        "resolved_url": fetch_res.resolved_url,
        "stats": stats,
    }
