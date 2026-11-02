"""
search/components/supervisor.py
Lifecycle supervisor for Hecos Deep Search background daemons.
Ensures background services (Tor, etc.) start smoothly on boot and shut down cleanly.
"""
from __future__ import annotations

import atexit
import logging
from typing import Dict, Any

from .catalog import get_component
from ..config import get_search_config

logger = logging.getLogger("browser.search.supervisor")

_INITIALIZED = False


def start_all_enabled() -> Dict[str, Any]:
    """Starts enabled daemons based on user configuration."""
    cfg = get_search_config()
    results = {}

    # Tor Daemon auto-start
    tor_cfg = cfg.get("tor", {})
    if tor_cfg.get("enabled", False) and tor_cfg.get("auto_start", True):
        tor_comp = get_component("tor_daemon")
        if tor_comp and tor_comp.is_installed() and not tor_comp.is_running():
            logger.info("[Supervisor] Auto-starting Tor daemon...")
            ok, msg = tor_comp.start()
            results["tor_daemon"] = {"ok": ok, "message": msg}
        else:
            results["tor_daemon"] = {"ok": True, "message": "Tor already running or not installed."}

    return results


def stop_all() -> None:
    """Terminates all managed background daemons on shutdown."""
    logger.info("[Supervisor] Stopping search background daemons...")
    tor_comp = get_component("tor_daemon")
    if tor_comp:
        try:
            tor_comp.stop()
        except Exception as e:
            logger.debug(f"Error stopping Tor daemon: {e}")


def init_supervisor() -> None:
    """Initializes daemon supervision and hooks clean shutdown."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    try:
        start_all_enabled()
    except Exception as e:
        logger.warning(f"[Supervisor] Could not start enabled daemons: {e}")

    atexit.register(stop_all)
