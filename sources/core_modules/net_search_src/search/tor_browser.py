"""
search/tor_browser.py
Tor Browser desktop executable detection, resolution, and launch subsystem.
"""
from __future__ import annotations

import os
import logging
import subprocess
from typing import Optional, Tuple

logger = logging.getLogger("browser.search.tor_browser")


def detect_tor_browser_path() -> Optional[str]:
    """Auto-detects the Tor Browser firefox.exe executable across standard OS paths."""
    user_home = os.path.expanduser("~")
    candidates = [
        os.path.join(user_home, "Desktop", "Tor Browser", "Browser", "firefox.exe"),
        os.path.join(user_home, "OneDrive", "Desktop", "Tor Browser", "Browser", "firefox.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tor Browser", "Browser", "firefox.exe"),
        r"C:\Program Files\Tor Browser\Browser\firefox.exe",
        r"C:\Program Files (x86)\Tor Browser\Browser\firefox.exe",
        r"D:\Tor Browser\Browser\firefox.exe",
        # Common Linux / macOS fallback paths
        os.path.expanduser("~/.local/share/torbrowser/tbb/x86_64/tor-browser/Browser/firefox"),
        "/Applications/Tor Browser.app/Contents/MacOS/firefox",
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


def get_tor_browser_path() -> str:
    """Returns configured Tor Browser path or auto-detects it from standard paths."""
    try:
        try:
            from hecos.modules.net_search.search.config import get_search_config
        except (ImportError, ValueError):
            from .config import get_search_config
        cfg = get_search_config().get("tor", {})
        configured = cfg.get("tor_browser_path", "").strip()
        if configured and os.path.isfile(configured):
            return configured
    except Exception as e:
        logger.debug(f"Could not read tor config for browser path: {e}")

    detected = detect_tor_browser_path()
    return detected or ""


def launch_tor_browser(url: str) -> Tuple[bool, str, str]:
    """
    Launches external desktop Tor Browser with the specified URL.
    Returns: (success: bool, message: str, resolved_path: str)
    """
    path = get_tor_browser_path()
    if not path:
        return False, "Tor Browser executable not found. Please install Tor Browser or specify the executable path.", ""

    try:
        subprocess.Popen([path, url], shell=False)
        return True, f"Launched Tor Browser successfully: {path}", path
    except Exception as e:
        logger.error(f"Failed to launch Tor Browser: {e}")
        return False, f"Failed to launch Tor Browser: {e}", path

