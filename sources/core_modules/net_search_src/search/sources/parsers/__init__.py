"""
search/sources/parsers/__init__.py
Format auto-detection and unified parsing entrypoint for search engine compilations.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from .json_parser import parse_json
from .csv_parser import parse_csv
from .yaml_parser import parse_yaml
from .sqlite_parser import parse_sqlite
from .opensearch_parser import parse_opensearch, discover_opensearch_links_from_html
from .onion_list_parser import parse_onion_or_text_list
from .domain_list_parser import parse_domain_list


SUPPORTED_FORMATS = ("auto", "json", "csv", "yaml", "sqlite", "opensearch", "onion_list", "domain_list")


def detect_format(raw_bytes: bytes, filename: str = "", url: str = "", content_type: str = "") -> str:
    """Detects compilation format using magic bytes, extension, Content-Type, and content sniffing."""
    if raw_bytes.startswith(b"SQLite format 3"):
        return "sqlite"

    hint = f"{filename} {url}".lower().split("?", 1)[0]
    ext = os.path.splitext(hint)[1]
    ct = (content_type or "").lower()

    if ext in (".sqlite", ".sqlite3", ".db") or "sqlite" in ct:
        return "sqlite"
    if ext in (".yaml", ".yml") or "yaml" in ct:
        return "yaml"
    if ext == ".csv" or ext == ".tsv" or "text/csv" in ct:
        return "csv"
    if ext == ".json" or "application/json" in ct:
        return "json"
    if ext == ".osd" or "opensearchdescription" in ct:
        return "opensearch"

    head = raw_bytes[:2048].decode("utf-8", errors="ignore").lstrip()
    head_l = head.lower()

    if "<opensearchdescription" in head_l or (head.startswith("<") and "opensearch" in head_l):
        return "opensearch"
    if head.startswith("{") or head.startswith("["):
        return "json"

    # Check CSV vs YAML vs plain text list
    non_comment_lines = [ln.strip() for ln in head.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if non_comment_lines:
        first = non_comment_lines[0].lower()
        if any(tok in first for tok in ("engines:", "fallbacks:", "nodes:", "custom_nodes:", "custom_onion_engines:", "onion_engines:")) or first.startswith("- name:"):
            return "yaml"
        if ("," in first or ";" in first or "\t" in first) and any(k in first for k in ("url", "host", "name", "onion", "template", "domain")):
            return "csv"

        # Bare domain / hosts / adblock detection (not .onion and not full URLs)
        sample_lines = [ln for ln in non_comment_lines[:15] if not ln.startswith(("!", "["))]
        if sample_lines:
            domain_hits = 0
            for ln in sample_lines:
                tok = ln.split()[0].lower()
                if ".onion" in ln.lower() or "://" in ln:
                    continue
                if tok in ("0.0.0.0", "127.0.0.1", "::", "::1") or ln.startswith("||") or ("." in tok and " " not in ln.strip()):
                    domain_hits += 1
            if domain_hits >= max(1, len(sample_lines) // 2):
                return "domain_list"

    if ext in (".xml",):
        return "opensearch"

    return "onion_list"


def parse_payload(
    raw_bytes: bytes,
    fmt: str = "auto",
    filename: str = "",
    url: str = "",
    content_type: str = "",
    file_path: str = "",
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Parses a compilation payload into raw candidate dictionaries.
    Returns `(detected_format, raw_candidates)`.
    """
    eff_fmt = (fmt or "auto").strip().lower()
    if eff_fmt not in SUPPORTED_FORMATS:
        eff_fmt = "auto"

    if eff_fmt == "auto":
        eff_fmt = detect_format(raw_bytes, filename=filename, url=url, content_type=content_type)

    if eff_fmt == "sqlite":
        return "sqlite", parse_sqlite(raw_bytes, source_url=url, file_path=file_path)
    if eff_fmt == "json":
        return "json", parse_json(raw_bytes, source_url=url)
    if eff_fmt == "yaml":
        return "yaml", parse_yaml(raw_bytes, source_url=url)
    if eff_fmt == "csv":
        return "csv", parse_csv(raw_bytes, source_url=url)
    if eff_fmt == "opensearch":
        return "opensearch", parse_opensearch(raw_bytes, source_url=url)
    if eff_fmt == "domain_list":
        return "domain_list", parse_domain_list(raw_bytes, source_url=url)
    return "onion_list", parse_onion_or_text_list(raw_bytes, source_url=url)


__all__ = [
    "SUPPORTED_FORMATS",
    "detect_format",
    "parse_payload",
    "discover_opensearch_links_from_html",
]

