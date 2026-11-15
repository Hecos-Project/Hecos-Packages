"""
search/sources/parsers/csv_parser.py
Parser for CSV/TSV endpoint and engine lists with automatic delimiter and column detection.
"""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List


_COL_ALIASES = {
    "name": "name",
    "title": "name",
    "label": "name",
    "engine_name": "name",
    "url": "url",
    "link": "url",
    "address": "url",
    "endpoint": "url",
    "onion": "url",
    "onion_url": "onion_url",
    "clearnet_url": "clearnet_url",
    "search_template": "search_template",
    "template": "search_template",
    "query_url": "search_template",
    "protocol": "protocol",
    "proto": "protocol",
    "scheme": "protocol",
    "host": "host",
    "domain": "host",
    "hostname": "host",
    "port": "port",
    "path": "path",
    "category": "category",
    "categories": "category",
    "type": "kind",
    "kind": "kind",
    "pool": "target_pool",
    "target_pool": "target_pool",
    "enabled": "enabled",
    "active": "enabled",
    "api_key": "api_key",
    "apikey": "api_key",
    "token": "api_key",
    "engine": "engine",
    "id": "id",
}


def parse_csv(raw_bytes: bytes, source_url: str = "") -> List[Dict[str, Any]]:
    text = raw_bytes.decode("utf-8-sig", errors="replace").strip()
    if not text:
        return []

    sample = text[:4096]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except Exception:
        if "\t" in sample and "," not in sample:
            delimiter = "\t"
        elif ";" in sample and "," not in sample:
            delimiter = ";"

    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return []

    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return []

    first_norm = [c.strip().lower().replace(" ", "_") for c in rows[0]]
    has_header = any(col in _COL_ALIASES for col in first_norm)

    candidates: List[Dict[str, Any]] = []
    if has_header:
        header_map = [_COL_ALIASES.get(col, col) for col in first_norm]
        for row in rows[1:]:
            if not any(cell.strip() for cell in row):
                continue
            item: Dict[str, Any] = {}
            for idx, val in enumerate(row):
                if idx < len(header_map):
                    key = header_map[idx]
                    v = val.strip()
                    if v != "":
                        item[key] = v
            if item:
                candidates.append(item)
    else:
        # Headerless: either [url] or [name, url, (optional template/category)]
        for row in rows:
            cells = [c.strip() for c in row if c.strip()]
            if not cells:
                continue
            if len(cells) == 1:
                val = cells[0]
                if "://" in val or "." in val:
                    candidates.append({"url": val})
            else:
                first_is_url = "://" in cells[0] or ".onion" in cells[0].lower()
                if first_is_url:
                    item = {"url": cells[0], "name": cells[1]}
                else:
                    item = {"name": cells[0], "url": cells[1]}
                if len(cells) >= 3:
                    item["category"] = cells[2]
                candidates.append(item)

    return candidates

