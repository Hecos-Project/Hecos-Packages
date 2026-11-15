"""
search/sources/parsers/sqlite_parser.py
Read-only SQLite parser for extracting search engines, nodes, or onion link tables.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from typing import Any, Dict, List


_COL_MAP = {
    "name": "name",
    "title": "name",
    "label": "name",
    "url": "url",
    "link": "url",
    "address": "url",
    "onion": "url",
    "onion_url": "onion_url",
    "clearnet_url": "clearnet_url",
    "search_template": "search_template",
    "template": "search_template",
    "protocol": "protocol",
    "proto": "protocol",
    "host": "host",
    "domain": "host",
    "port": "port",
    "path": "path",
    "category": "category",
    "type": "kind",
    "kind": "kind",
    "pool": "target_pool",
    "target_pool": "target_pool",
    "enabled": "enabled",
    "api_key": "api_key",
    "engine": "engine",
}

_USEFUL_KEYS = {"url", "onion_url", "clearnet_url", "search_template", "host", "engine"}


def _read_sqlite_file(db_path: str) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    uri = f"file:{os.path.abspath(db_path)}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        tables = [
            row[0]
            for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for tbl in tables:
            safe_tbl = '"' + tbl.replace('"', '""') + '"'
            cols_info = cur.execute(f"PRAGMA table_info({safe_tbl})").fetchall()
            col_names = [c[1] for c in cols_info]
            mapped = {c: _COL_MAP.get(c.strip().lower(), c.strip().lower()) for c in col_names}
            if not (set(mapped.values()) & _USEFUL_KEYS):
                continue

            rows = cur.execute(f"SELECT * FROM {safe_tbl} LIMIT 5000").fetchall()
            for r in rows:
                item: Dict[str, Any] = {}
                for orig_col in col_names:
                    val = r[orig_col]
                    if val is None or str(val).strip() == "":
                        continue
                    norm_key = mapped[orig_col]
                    item[norm_key] = val if isinstance(val, (bool, int, float)) else str(val).strip()
                if any(item.get(k) for k in _USEFUL_KEYS):
                    candidates.append(item)
    finally:
        conn.close()
    return candidates


def parse_sqlite(raw_bytes: bytes, source_url: str = "", file_path: str = "") -> List[Dict[str, Any]]:
    if file_path and os.path.isfile(file_path):
        return _read_sqlite_file(file_path)

    if not raw_bytes or not raw_bytes.startswith(b"SQLite format 3"):
        raise ValueError("Invalid SQLite database header.")

    fd, tmp_path = tempfile.mkstemp(prefix="hecos_src_", suffix=".sqlite")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw_bytes)
        return _read_sqlite_file(tmp_path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass

