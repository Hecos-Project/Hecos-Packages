"""
search/sources/sqlite_sync.py
Routes parsed source compilations into SQLite Domain Index or SQLite Stream Index.
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import domain_store
from ..stream_hunter import stream_store
from ..stream_hunter.models import StreamItem, detect_stream_protocol

STREAM_POOL_ROLES = {
    "stream_tv": "tv",
    "stream_radio": "radio",
    "stream_webcam": "webcam",
    "stream_raw": "raw",
}

DOMAIN_POOLS = ("domain_blocklist", "domain_allowlist", "domain_directory")


def is_stream_target(detected_fmt: str, default_pool: str, url_hint: str, raw_bytes: bytes) -> bool:
    if default_pool in STREAM_POOL_ROLES:
        return True
    hint_low = (url_hint or "").lower()
    raw_prefix = raw_bytes[:512].decode("utf-8", errors="ignore").lstrip() if raw_bytes else ""
    return (
        detected_fmt == "m3u"
        or hint_low.endswith((".m3u", ".m3u8", ".pls"))
        or raw_prefix.startswith(("#EXTM3U", "#EXTINF:", "[playlist]"))
    )


def apply_stream_candidates(
    raw_candidates: List[Dict[str, Any]],
    default_pool: str,
    source_id: str,
    dry_run: bool,
    url_hint: str,
    raw_bytes: bytes,
) -> Dict[str, Any]:
    s_role = STREAM_POOL_ROLES.get(default_pool, "tv")
    if raw_bytes:
        text_body = raw_bytes.decode("utf-8", errors="ignore")
        stream_items = stream_store.parse_stream_compilation_text(
            text_body, default_role=s_role, source_url=url_hint or source_id
        )
    else:
        stream_items = []
        for c in raw_candidates:
            if not isinstance(c, dict):
                continue
            su = str(c.get("url") or c.get("url_resolved") or c.get("stream_url") or "").strip()
            if su.startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://")):
                nm = str(c.get("name") or c.get("title") or su).strip()
                stream_items.append(StreamItem(
                    title=nm,
                    stream_url=su,
                    url=su,
                    category=s_role,
                    protocol=detect_stream_protocol(su, "", s_role),
                    country=str(c.get("country") or c.get("countrycode") or "INT").upper()[:2] or "INT",
                ))

    parsed_valid, added, skipped = stream_store.insert_streams(
        source_id=source_id or "preview",
        role=s_role,
        items=stream_items,
        dry_run=dry_run,
    )
    preview = []
    if dry_run:
        for it in stream_items[:15]:
            preview.append({
                "pool": f"stream_{s_role}",
                "name": f"[{it.protocol}] {it.title}",
                "url": it.stream_url,
            })
    return {
        "parsed": parsed_valid,
        "added": added,
        "skipped_duplicates": skipped,
        "invalid": 0,
        "by_pool": {f"stream_{s_role}": added} if added else {},
        "preview": preview,
    }


def apply_domain_candidates(
    raw_candidates: List[Dict[str, Any]],
    default_pool: str,
    source_id: str,
    dry_run: bool,
    url_hint: str,
) -> Dict[str, Any]:
    if default_pool in DOMAIN_POOLS:
        role = default_pool.replace("domain_", "", 1)
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
