"""
search/engines/__init__.py
Registry and selector for all Hecos Deep Search engines.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from .base import BaseEngine
from .clear_ddgs import ClearDdgsEngine
from .clear_news import ClearNewsEngine
from .clear_searxng import ClearSearxngEngine
from .dark_ahmia import DarkAhmiaEngine
from .dark_torch import DarkTorchEngine
from .dark_haystak import DarkHaystakEngine
from .dark_onionland import DarkOnionlandEngine
from .dark_excavator import DarkExcavatorEngine
from .dark_phobos import DarkPhobosEngine
from .dark_tor66 import DarkTor66Engine
from .dark_danieltore import DarkDanielEngine
from .dark_custom import DarkCustomEngine
from .media_images import MediaImagesEngine
from .media_videos import MediaVideosEngine
from .media_audio import MediaAudioEngine
from .files_dorks import FilesDorksEngine
from .osint_sherlock import OsintSherlockEngine
from ..config import get_search_config

logger = logging.getLogger("browser.search.engines")

_ENGINES: Dict[str, BaseEngine] = {}


def _register_all():
    if _ENGINES:
        return

    engines_list = [
        ClearDdgsEngine(),
        ClearNewsEngine(),
        ClearSearxngEngine(),
        DarkAhmiaEngine(),
        DarkTorchEngine(),
        DarkHaystakEngine(),
        DarkOnionlandEngine(),
        DarkExcavatorEngine(),
        DarkPhobosEngine(),
        DarkTor66Engine(),
        DarkDanielEngine(),
        DarkCustomEngine(),
        MediaImagesEngine(),
        MediaVideosEngine(),
        MediaAudioEngine(),
        FilesDorksEngine(),
        OsintSherlockEngine(),
    ]
    for eng in engines_list:
        _ENGINES[eng.id] = eng


def get_all_engines() -> List[BaseEngine]:
    _register_all()
    return list(_ENGINES.values())


def get_engine(engine_id: str) -> Optional[BaseEngine]:
    _register_all()
    return _ENGINES.get(engine_id)


def get_engines_for_mode(mode: str, requested_engines: Optional[List[str]] = None) -> List[BaseEngine]:
    """Returns the list of active engines for a given search mode."""
    _register_all()
    cfg = get_search_config().get("engines", {})

    mode_map = {
        "clear": ["clear_ddgs", "clear_news", "media_images", "media_videos", "files_dorks", "clear_searxng"],
        "dark": [
            "dark_ahmia", "dark_torch", "dark_haystak", "dark_onionland",
            "dark_excavator", "dark_phobos", "dark_tor66", "dark_danieltore", "dark_custom"
        ],
        "deep": [
            "clear_ddgs", "clear_news", "media_images", "media_videos", "media_audio", "files_dorks",
            "dark_ahmia", "dark_torch", "dark_haystak", "dark_onionland",
            "dark_excavator", "dark_phobos", "dark_tor66", "dark_danieltore", "dark_custom",
            "clear_searxng"
        ],
        "media": ["media_images", "media_videos", "media_audio"],
        "files": ["files_dorks", "clear_ddgs"],
        "osint": ["osint_sherlock", "clear_ddgs"],
    }

    selected_ids = mode_map.get(mode, mode_map["clear"])

    # If user explicitly requested specific engines, filter by those
    if requested_engines:
        selected_ids = [eid for eid in requested_engines if eid in _ENGINES]

    active_engines: List[BaseEngine] = []
    for eid in selected_ids:
        eng = _ENGINES.get(eid)
        if not eng:
            continue
        # Check user config toggle
        if not cfg.get(eid, True):
            continue
        # Check engine availability
        if eng.is_available():
            active_engines.append(eng)

    # Sort by priority desc
    active_engines.sort(key=lambda x: x.priority, reverse=True)
    return active_engines
