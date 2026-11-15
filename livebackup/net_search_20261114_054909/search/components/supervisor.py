"""
search/components/supervisor.py
Lifecycle supervisor for Hecos Deep Search background daemons.
Ensures background services (Tor, etc.) start smoothly on boot and shut down cleanly.
"""
from __future__ import annotations

import atexit
import logging
import threading
from typing import Dict, Any

from .catalog import get_component
from ..config import get_search_config

logger = logging.getLogger("browser.search.supervisor")

_INITIALIZED = False
_STOP_EVENT = threading.Event()
_SOURCES_THREAD: threading.Thread | None = None


def _sources_auto_updater_loop() -> None:
    """Periodically syncs enabled sources that have auto_update=True."""
    # Initial grace delay so app startup remains instant
    if _STOP_EVENT.wait(timeout=45.0):
        return
    while not _STOP_EVENT.is_set():
        try:
            cfg = get_search_config()
            if cfg.get("enabled", True) and cfg.get("sources_auto_update", True):
                from ..sources import sync_all_sources
                res = sync_all_sources(force=False, only_due=True)
                if res.get("total_added", 0) > 0:
                    logger.info(
                        f"[Supervisor] Auto-updated sources: +{res['total_added']} added, "
                        f"{res['total_skipped_duplicates']} duplicates skipped."
                    )
        except Exception as e:
            logger.debug(f"[Supervisor] Source auto-updater tick error: {e}")

        # Wake every 30 minutes (or earlier on shutdown)
        if _STOP_EVENT.wait(timeout=1800.0):
            break


def start_sources_scheduler() -> None:
    """Starts the daemon thread responsible for periodic source list synchronization."""
    global _SOURCES_THREAD
    if _SOURCES_THREAD is not None and _SOURCES_THREAD.is_alive():
        return
    _STOP_EVENT.clear()
    _SOURCES_THREAD = threading.Thread(
        target=_sources_auto_updater_loop,
        name="NetSearchSourcesUpdater",
        daemon=True,
    )
    _SOURCES_THREAD.start()


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
    _STOP_EVENT.set()
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

    try:
        start_sources_scheduler()
    except Exception as e:
        logger.warning(f"[Supervisor] Could not start sources scheduler: {e}")

    atexit.register(stop_all)
