"""
search/sources/updater.py
Synchronization, dry-run preview, source cleanup, and raw import orchestrator.
Delegates endpoint merge/purge to `endpoint_sync.py` and SQLite indexing to `sqlite_sync.py`.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

try:
    from hecos.core.logging import logger as hecos_logger
except (ImportError, ValueError):
    hecos_logger = logging.getLogger("browser.search.sources")

from . import domain_store
from ..stream_hunter import stream_store
from .endpoint_sync import (
    merge_candidates_into_endpoints,
    purge_endpoints_for_source,
    set_endpoints_enabled_for_source,
)
from .sqlite_sync import (
    DOMAIN_POOLS,
    STREAM_POOL_ROLES,
    apply_domain_candidates,
    apply_stream_candidates,
    is_stream_target,
)
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


def _apply_parsed_candidates(
    detected_fmt: str,
    raw_candidates: List[Dict[str, Any]],
    default_pool: str = "auto",
    source_id: str = "",
    dry_run: bool = False,
    url_hint: str = "",
    raw_bytes: bytes = b"",
    source_name: str = "",
) -> Dict[str, Any]:
    """Routes parsed candidates either to SQLite Stream Index, SQLite Domain Index, or endpoint pools."""
    if is_stream_target(detected_fmt, default_pool, url_hint, raw_bytes):
        return apply_stream_candidates(
            raw_candidates=raw_candidates,
            default_pool=default_pool,
            source_id=source_id,
            dry_run=dry_run,
            url_hint=url_hint,
            raw_bytes=raw_bytes,
        )

    if detected_fmt == "domain_list" or default_pool in DOMAIN_POOLS:
        return apply_domain_candidates(
            raw_candidates=raw_candidates,
            default_pool=default_pool,
            source_id=source_id,
            dry_run=dry_run,
            url_hint=url_hint,
        )

    return merge_candidates_into_endpoints(
        raw_candidates,
        default_pool=default_pool,
        source_id=source_id,
        dry_run=dry_run,
    )


def _parse_for_target(
    content: bytes,
    fmt_hint: str,
    target_pool: str,
    filename: str = "",
    url: str = "",
    content_type: str = "",
    file_path: str = "",
) -> tuple[str, List[Dict[str, Any]]]:
    if fmt_hint == "m3u" or target_pool in STREAM_POOL_ROLES:
        detected_fmt = "m3u" if fmt_hint in ("auto", "m3u") else fmt_hint
        return detected_fmt, []
    return parse_payload(
        content,
        fmt=fmt_hint,
        filename=filename,
        url=url,
        content_type=content_type,
        file_path=file_path,
    )


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

        tpool = src.get("target_pool", "auto")
        if fetch_res.not_modified or (not force and not dry_run and fetch_res.sha256 and fetch_res.sha256 == src.get("last_hash")):
            if tpool in DOMAIN_POOLS:
                domain_store.set_source_role(source_id, tpool.replace("domain_", "", 1))
            elif tpool in STREAM_POOL_ROLES:
                stream_store.set_stream_source_role(source_id, STREAM_POOL_ROLES[tpool])
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
            detected_fmt, raw_candidates = _parse_for_target(
                fetch_res.content,
                fmt_hint=src.get("format", "auto"),
                target_pool=tpool,
                filename=fetch_res.file_path or src.get("location", ""),
                url=fetch_res.resolved_url or src.get("location", ""),
                content_type=fetch_res.content_type,
                file_path=fetch_res.file_path,
            )
            stats = _apply_parsed_candidates(
                detected_fmt,
                raw_candidates,
                default_pool=tpool,
                source_id=source_id,
                dry_run=dry_run,
                url_hint=fetch_res.resolved_url or src.get("location", ""),
                raw_bytes=fetch_res.content,
                source_name=src.get("name", ""),
            )
        except Exception as e:
            err_msg = f"Parse/merge failed: {e}"
            hecos_logger.warning(f"[Sources] Sync failed for '{src.get('name')}': {err_msg}")
            if not dry_run:
                update_source_status(source_id, {"last_sync": now, "last_status": "error", "last_error": err_msg})
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
        results.append({"id": src["id"], "name": src.get("name", src["id"]), **res})
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
    """Deletes a source and purges all endpoints and indexed domains/streams originally imported from it."""
    with _SYNC_LOCK:
        removed_endpoints = purge_endpoints_for_source(source_id)
        removed_domains = domain_store.remove_domains_for_source(source_id)
        removed_streams = stream_store.remove_stream_source(source_id)
        deleted = delete_source_record(source_id)
        return {
            "ok": deleted,
            "removed_endpoints": removed_endpoints + removed_domains + removed_streams,
            "error": "" if deleted else f"Source '{source_id}' not found.",
        }


def toggle_source(source_id: str, enabled: Optional[bool] = None) -> Dict[str, Any]:
    """Enables or disables a source and toggles its managed endpoints and indexed domains/streams accordingly."""
    src = get_source(source_id)
    if not src:
        return {"ok": False, "error": f"Source '{source_id}' not found."}
    new_state = (not bool(src.get("enabled", True))) if enabled is None else bool(enabled)
    with _SYNC_LOCK:
        updated = update_source_status(source_id, {"enabled": new_state})
        affected_ep = set_endpoints_enabled_for_source(source_id, new_state)
        affected_dom = domain_store.set_source_enabled(source_id, new_state) or 0
        affected_str = stream_store.set_stream_source_enabled(source_id, new_state) or 0
    return {"ok": True, "enabled": new_state, "affected_endpoints": affected_ep + affected_dom + affected_str, "source": updated}


def import_raw_content(
    content_or_bytes: Any,
    fmt: str = "auto",
    filename: str = "",
    target_pool: str = "auto",
    source_name: str = "Manual Import",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Imports pasted text or uploaded file bytes (JSON, CSV, YAML, SQLite, OpenSearch XML, .m3u/.m3u8, .onion list)."""
    raw_bytes = content_or_bytes if isinstance(content_or_bytes, (bytes, bytearray)) else str(content_or_bytes or "").encode("utf-8")
    if not raw_bytes.strip():
        return {"ok": False, "error": "Empty import content."}

    with _SYNC_LOCK:
        detected_fmt, raw_candidates = _parse_for_target(bytes(raw_bytes), fmt_hint=fmt, target_pool=target_pool, filename=filename)
        src_id = "" if dry_run else f"src_{uuid.uuid4().hex[:10]}"

        stats = _apply_parsed_candidates(
            detected_fmt,
            raw_candidates,
            default_pool=target_pool,
            source_id=src_id,
            dry_run=dry_run,
            url_hint=filename or source_name,
            raw_bytes=bytes(raw_bytes),
            source_name=source_name or filename,
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

        return {"ok": True, "detected_format": detected_fmt, "source_id": src_id, "stats": stats}


def preview_ad_hoc_source(location: str, fmt: str = "auto", target_pool: str = "auto", use_tor: bool = False) -> Dict[str, Any]:
    """Fetches and parses a URL or file path in dry-run mode without saving the source or endpoints."""
    fetch_res = fetch_source(
        location,
        use_tor=use_tor or (".onion" in (location or "").lower()),
        prefer_opensearch=(fmt == "opensearch"),
    )
    if not fetch_res.ok:
        return {"ok": False, "error": fetch_res.error, "tor_offline": fetch_res.tor_offline}
    detected_fmt, raw_candidates = _parse_for_target(
        fetch_res.content,
        fmt_hint=fmt,
        target_pool=target_pool,
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
        raw_bytes=fetch_res.content,
    )
    return {"ok": True, "detected_format": detected_fmt, "resolved_url": fetch_res.resolved_url, "stats": stats}
