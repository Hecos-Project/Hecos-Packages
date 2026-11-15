"""
search/stream_hunter/stream_store.py
High-speed SQLite index for imported Live Stream lists & compilations (.m3u, .m3u8, .pls, JSON, CSV, TXT).
Mirrors `domain_store.py` so the Central Hub 'Live Streams' tab behaves and looks 100% identical to 'Domains (SQLite)'.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import StreamItem, detect_stream_protocol
from .providers_tv import parse_m3u_content

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("net_search.stream_hunter.stream_store")

VALID_STREAM_ROLES = ("tv", "radio", "webcam", "raw")


def _get_db_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "stream_lists.sqlite")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_get_db_path(), timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stream_sources (
            source_id TEXT PRIMARY KEY,
            role TEXT NOT NULL DEFAULT 'tv',
            enabled INTEGER NOT NULL DEFAULT 1,
            stream_count INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stream_entries (
            source_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'tv',
            stream_url TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            protocol TEXT NOT NULL DEFAULT 'HLS',
            country TEXT NOT NULL DEFAULT 'INT',
            logo TEXT NOT NULL DEFAULT '',
            resolution TEXT NOT NULL DEFAULT '',
            bitrate INTEGER NOT NULL DEFAULT 0,
            tags TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (role, stream_url)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stream_entries_src ON stream_entries(source_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stream_entries_title ON stream_entries(title)")
    return conn


def parse_stream_compilation_text(content: str, default_role: str = "tv", source_url: str = "") -> List[StreamItem]:
    """
    Universal parser for ready-made stream compilations:
    - #EXTM3U / .m3u / .m3u8 / .pls playlists
    - JSON arrays (IPTV-Org streams.json, Radio-Browser stations JSON, custom JSON)
    - CSV / TSV lines (title,url,country,category)
    - Plain text lists of stream URLs (one per line, or 'Title | URL')
    """
    raw = (content or "").strip()
    if not raw:
        return []

    role = default_role if default_role in VALID_STREAM_ROLES else "tv"

    # 1. Check M3U / PLS
    if raw.startswith("#EXTM3U") or "#EXTINF:" in raw or "[playlist]" in raw.lower()[:120]:
        return parse_m3u_content(raw, source_url=source_url, default_category=role)

    # 2. Check JSON array / object
    if raw.startswith("[") or raw.startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = data.get("streams") or data.get("stations") or data.get("channels") or data.get("items") or []
            if isinstance(data, list):
                items: List[StreamItem] = []
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    su = (entry.get("stream_url") or entry.get("url_resolved") or entry.get("url") or "").strip()
                    if not su or not su.startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://")):
                        continue
                    title = (entry.get("title") or entry.get("name") or entry.get("channel") or su.split("/")[-1]).strip()
                    cc = (entry.get("country") or entry.get("countrycode") or "INT").upper()[:2]
                    logo = (entry.get("logo") or entry.get("favicon") or "").strip()
                    codec = (entry.get("codec") or "").upper()
                    br = int(entry.get("bitrate") or 0)
                    res = str(entry.get("resolution") or entry.get("quality") or "")
                    cat = str(entry.get("category") or role).lower()
                    if cat not in VALID_STREAM_ROLES:
                        cat = role
                    items.append(StreamItem(
                        title=title,
                        stream_url=su,
                        url=entry.get("homepage") or su,
                        category=cat,
                        protocol=detect_stream_protocol(su, codec, cat),
                        country=cc or "INT",
                        codec=codec,
                        bitrate=br,
                        resolution=res,
                        logo=logo,
                        source_engine="streams_sqlite",
                    ))
                return items
        except Exception:
            pass

    # 3. Line-by-line CSV / Pipe / Raw URL list
    out: List[StreamItem] = []
    for ln in raw.splitlines():
        line = ln.strip()
        if not line or line.startswith("#"):
            continue
        title = ""
        su = ""
        cc = "INT"
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            title = parts[0]
            su = parts[1] if len(parts) > 1 else ""
            if len(parts) > 2 and len(parts[2]) == 2:
                cc = parts[2].upper()
        elif "," in line and not line.startswith(("http://", "https://", "rtsp://")):
            parts = [p.strip().strip('"') for p in line.split(",")]
            for p in parts:
                if p.startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://")):
                    su = p
                elif not title and len(p) > 2:
                    title = p
                elif len(p) == 2 and p.isalpha():
                    cc = p.upper()
        elif line.startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://")):
            su = line
            title = su.split("/")[-1].split("?")[0] or "Live Stream"

        if su and su.startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://")):
            out.append(StreamItem(
                title=title or su.split("/")[-1] or "Stream",
                stream_url=su,
                url=su,
                category=role,
                protocol=detect_stream_protocol(su, "", role),
                country=cc,
                source_engine="streams_sqlite",
            ))
    return out


def insert_streams(
    source_id: str,
    role: str,
    items: Iterable[StreamItem],
    dry_run: bool = False,
) -> Tuple[int, int, int]:
    """
    Bulk-inserts deduplicated StreamItems into SQLite `stream_lists.sqlite`.
    Returns `(parsed_valid, added, skipped_duplicates)`.
    """
    eff_role = role.replace("stream_", "") if role else "tv"
    if eff_role not in VALID_STREAM_ROLES:
        eff_role = "tv"
    eff_src = source_id or "__dry_run__"

    rows = []
    seen_urls = set()
    skipped_in_batch = 0

    for it in items:
        su = (it.stream_url or "").strip()
        if not su:
            continue
        if su in seen_urls:
            skipped_in_batch += 1
            continue
        seen_urls.add(su)
        rows.append((
            eff_src,
            eff_role,
            su,
            (it.title or "Live Stream")[:200],
            (it.protocol or "HLS")[:20],
            (it.country or "INT")[:4],
            (it.logo or "")[:500],
            (it.resolution or "")[:30],
            int(it.bitrate or 0),
            ",".join(it.tags or [])[:250],
        ))

    parsed_valid = len(seen_urls) + skipped_in_batch
    if not rows:
        return parsed_valid, 0, skipped_in_batch

    conn = _connect()
    try:
        conn.execute("BEGIN")
        if not dry_run:
            conn.execute(
                "DELETE FROM stream_entries WHERE source_id = ? AND role != ?",
                (eff_src, eff_role),
            )
        before = conn.total_changes
        conn.executemany(
            """
            INSERT OR IGNORE INTO stream_entries
            (source_id, role, stream_url, title, protocol, country, logo, resolution, bitrate, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        added = conn.total_changes - before
        skipped_total = skipped_in_batch + (len(rows) - added)

        if dry_run:
            conn.execute("ROLLBACK")
        else:
            cur = conn.execute(
                "SELECT COUNT(*) FROM stream_entries WHERE source_id = ?",
                (eff_src,),
            )
            total_for_source = int(cur.fetchone()[0])
            conn.execute(
                """
                INSERT INTO stream_sources(source_id, role, enabled, stream_count, updated_at)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    role = excluded.role,
                    stream_count = excluded.stream_count,
                    updated_at = excluded.updated_at
                """,
                (eff_src, eff_role, total_for_source, int(time.time())),
            )
            conn.commit()
        return parsed_valid, added, skipped_total
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def set_stream_source_role(source_id: str, new_role: str) -> int:
    """Switches a stream list's role (tv | radio | webcam | raw) in SQLite in 1 click."""
    eff_role = new_role.replace("stream_", "").lower()
    if not source_id or eff_role not in VALID_STREAM_ROLES:
        return 0
    conn = _connect()
    try:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE OR IGNORE stream_entries SET role = ? WHERE source_id = ?",
            (eff_role, source_id),
        )
        conn.execute(
            "DELETE FROM stream_entries WHERE source_id = ? AND role != ?",
            (source_id, eff_role),
        )
        cur = conn.execute("SELECT COUNT(*) FROM stream_entries WHERE source_id = ?", (source_id,))
        cnt = int(cur.fetchone()[0])
        conn.execute(
            "UPDATE stream_sources SET role = ?, stream_count = ?, updated_at = ? WHERE source_id = ?",
            (eff_role, cnt, int(time.time()), source_id),
        )
        conn.commit()
        return cnt
    finally:
        conn.close()


def set_stream_source_enabled(source_id: str, enabled: bool) -> None:
    if not source_id:
        return
    conn = _connect()
    try:
        conn.execute(
            "UPDATE stream_sources SET enabled = ? WHERE source_id = ?",
            (1 if enabled else 0, source_id),
        )
        conn.commit()
    finally:
        conn.close()


def remove_stream_source(source_id: str) -> int:
    if not source_id:
        return 0
    conn = _connect()
    try:
        before = conn.total_changes
        conn.execute("DELETE FROM stream_entries WHERE source_id = ?", (source_id,))
        removed = conn.total_changes - before
        conn.execute("DELETE FROM stream_sources WHERE source_id = ?", (source_id,))
        conn.commit()
        return removed
    finally:
        conn.close()


def get_stream_summary() -> Dict[str, Any]:
    """Returns SQLite stream index counts by role and by source_id for the Central Hub UI."""
    conn = _connect()
    try:
        by_role = {"tv": 0, "radio": 0, "webcam": 0, "raw": 0}
        cur = conn.execute(
            """
            SELECT e.role, COUNT(*)
            FROM stream_entries e
            LEFT JOIN stream_sources s ON e.source_id = s.source_id
            WHERE COALESCE(s.enabled, 1) = 1
            GROUP BY e.role
            """
        )
        for role, cnt in cur.fetchall():
            if role in by_role:
                by_role[role] = int(cnt)

        by_source: Dict[str, Dict[str, Any]] = {}
        cur2 = conn.execute("SELECT source_id, role, enabled, stream_count, updated_at FROM stream_sources")
        for sid, role, en, cnt, upd in cur2.fetchall():
            by_source[sid] = {
                "role": role,
                "enabled": bool(en),
                "count": int(cnt),
                "updated_at": int(upd),
            }
        return {
            "total_streams": sum(by_role.values()),
            "by_role": by_role,
            "by_source": by_source,
        }
    except Exception:
        return {"total_streams": 0, "by_role": {"tv": 0, "radio": 0, "webcam": 0, "raw": 0}, "by_source": {}}
    finally:
        conn.close()


def search_sqlite_streams(
    query: str = "",
    subfilter: str = "all",
    country: str = "",
    limit: int = 50,
    category: Optional[str] = None,
) -> List[StreamItem]:
    """Searches enabled SQLite stream lists by query tokens, category role, and country."""
    conn = _connect()
    try:
        q_clean = (query or "").strip().lower()
        tokens = [t for t in re.split(r"\s+", q_clean) if t and t not in ("live", "stream", "tv", "radio", "webcam", "all", "*")]
        cc = (country or "").strip().upper()
        raw_sub = (category if category is not None else subfilter) or "all"
        sub = raw_sub.strip().lower()
        if sub == "cams":
            sub = "webcam"
        elif sub == "dorks":
            sub = "raw"

        sql = """
            SELECT e.title, e.stream_url, e.role, e.protocol, e.country, e.logo, e.resolution, e.bitrate, e.tags
            FROM stream_entries e
            LEFT JOIN stream_sources s ON e.source_id = s.source_id
            WHERE COALESCE(s.enabled, 1) = 1
        """
        params: List[Any] = []
        if sub in VALID_STREAM_ROLES:
            sql += " AND e.role = ?"
            params.append(sub)
        if cc and cc != "ALL":
            sql += " AND UPPER(e.country) = ?"
            params.append(cc)
        for tok in tokens[:4]:
            sql += " AND (LOWER(e.title) LIKE ? OR LOWER(e.tags) LIKE ? OR LOWER(e.stream_url) LIKE ?)"
            like = f"%{tok}%"
            params.extend([like, like, like])

        sql += " LIMIT ?"
        params.append(max(10, int(limit)))

        cur = conn.execute(sql, params)
        out: List[StreamItem] = []
        for title, su, role, proto, c_code, logo, res, br, tags_str in cur.fetchall():
            out.append(StreamItem(
                title=title,
                stream_url=su,
                url=su,
                category=role if role in VALID_STREAM_ROLES else "tv",
                protocol=proto or detect_stream_protocol(su, "", role),
                country=c_code or "INT",
                logo=logo or "",
                resolution=res or "",
                bitrate=int(br or 0),
                source_engine="streams_sqlite",
                tags=[t for t in (tags_str or "").split(",") if t],
            ))
        return out
    except Exception as e:
        hecos_logger.warning(f"[StreamStore] SQLite stream search error: {e}")
        return []
    finally:
        conn.close()
