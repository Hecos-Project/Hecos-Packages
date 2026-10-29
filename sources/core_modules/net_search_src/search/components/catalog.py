"""
search/components/catalog.py
Central registry of all on-demand search components and tools.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .base import BaseComponent
from .pip_component import PipComponent
from .tor_daemon import TorDaemonComponent
from .searxng_component import SearXNGComponent

logger = logging.getLogger("browser.search.catalog")

_COMPONENTS: Dict[str, BaseComponent] = {}


def _init_catalog():
    if _COMPONENTS:
        return

    # 1. Core MetaSearch Engine (ddgs)
    _COMPONENTS["ddgs"] = PipComponent(
        component_id="ddgs",
        name="DDGS Multi-Engine Core",
        description="Unified metasearch library covering Google, Bing, Brave, DuckDuckGo, Yahoo, Startpage & Wikipedia.",
        import_name="ddgs",
        pip_package="ddgs",
        category="core"
    )

    # 2. Tor Daemon Service
    _COMPONENTS["tor_daemon"] = TorDaemonComponent()

    # 3. Tor Python SOCKS Routing (PySocks + stem)
    _COMPONENTS["tor_pysocks"] = PipComponent(
        component_id="tor_pysocks",
        name="Tor SOCKS5 Python Support",
        description="Enables Python requests and engines to route through Tor (socks5h://) with no DNS leaks.",
        import_name="socks",
        pip_package="PySocks stem",
        category="tor",
        extra_imports=["stem"]
    )

    # 4. Trafilatura text extraction
    _COMPONENTS["trafilatura"] = PipComponent(
        component_id="trafilatura",
        name="Trafilatura Text Extractor",
        description="Deep web scraping & article extraction engine to produce clean, readable text for LLMs.",
        import_name="trafilatura",
        pip_package="trafilatura",
        category="scraping"
    )

    # 5. yt-dlp media discovery
    _COMPONENTS["yt_dlp"] = PipComponent(
        component_id="yt_dlp",
        name="yt-dlp Media Search",
        description="Media search and metadata extraction for audio, video, and streaming platforms.",
        import_name="yt_dlp",
        pip_package="yt-dlp",
        category="media"
    )

    # 6. Sherlock OSINT
    _COMPONENTS["sherlock"] = PipComponent(
        component_id="sherlock",
        name="Sherlock OSINT Discovery",
        description="Scans 400+ social networks and web services for a specific username or persona.",
        import_name="sherlock_project",
        pip_package="sherlock-project",
        category="osint"
    )

    # 7. SearXNG
    _COMPONENTS["searxng"] = SearXNGComponent()


def get_component(component_id: str) -> Optional[BaseComponent]:
    _init_catalog()
    return _COMPONENTS.get(component_id)


def list_components() -> List[BaseComponent]:
    _init_catalog()
    return list(_COMPONENTS.values())


def get_all_statuses() -> List[Dict]:
    _init_catalog()
    return [c.get_status().to_dict() for c in _COMPONENTS.values()]
