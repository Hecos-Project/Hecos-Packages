"""
search/__init__.py
Hecos Deep Search & Intelligence Submodule.
"""
from __future__ import annotations

import logging
from .service import HecosSearchService, get_search_service
from .tools import SearchTools
from .components.supervisor import init_supervisor, stop_all
from .components.catalog import get_component, list_components, get_all_statuses

logger = logging.getLogger("browser.search")

_initialized = False

def init_search_subsystem():
    """Initializes the Deep Search subsystem and background daemons."""
    global _initialized
    if _initialized:
        return
    _initialized = True
    try:
        init_supervisor()
        logger.info("[DeepSearch] Subsystem initialized successfully.")
    except Exception as e:
        logger.warning(f"[DeepSearch] Subsystem initialization warning: {e}")

__all__ = [
    "HecosSearchService",
    "get_search_service",
    "SearchTools",
    "init_search_subsystem",
    "stop_all",
    "get_component",
    "list_components",
    "get_all_statuses",
]
