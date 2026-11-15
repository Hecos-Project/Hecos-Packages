"""
search/sources/__init__.py
Modular search-engine & resource list ingestion subsystem for Hecos Net Search.
Supports JSON, CSV, YAML, SQLite, OpenSearch XML, GitHub raw, and Tor .onion compilations.
"""
from __future__ import annotations

from .registry import (
    add_or_update_source,
    get_preset_sources,
    get_source,
    list_sources,
)
from .updater import (
    import_raw_content,
    preview_ad_hoc_source,
    remove_source,
    sync_all_sources,
    sync_source,
    toggle_source,
)

__all__ = [
    "list_sources",
    "get_source",
    "add_or_update_source",
    "get_preset_sources",
    "sync_source",
    "sync_all_sources",
    "remove_source",
    "toggle_source",
    "import_raw_content",
    "preview_ad_hoc_source",
]

