"""
search/components/searxng_component.py
Native Pure-Python SearXNG daemon manager for Hecos Deep Search.
Runs locally via pure-Python modules (simplexng / waitress) without requiring Docker.
"""
from __future__ import annotations

import os
import sys
import time
import socket
import logging
import subprocess
import requests
from typing import Tuple, Dict, Any, Optional, Callable

from .base import BaseComponent
from ..config import get_search_config
from ..http_client import is_port_open

logger = logging.getLogger("browser.search.searxng_component")

try:
    from hecos.core.logging import logger as hecos_logger
except (ImportError, ValueError):
    hecos_logger = logger

DEFAULT_PORT = 8888
_GLOBAL_SEARXNG_PROC: Optional[subprocess.Popen] = None


def _get_searxng_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    hecos_root = os.path.normpath(os.path.join(here, "..", "..", "..", ".."))
    searxng_dir = os.path.join(hecos_root, "data", "searxng")
    os.makedirs(searxng_dir, exist_ok=True)
    return searxng_dir


def _ensure_searxng_config(port: int = DEFAULT_PORT) -> str:
    sdir = _get_searxng_dir()
    config_path = os.path.join(sdir, "settings.yml")
    if not os.path.isfile(config_path):
        import secrets
        secret = secrets.token_hex(16)
        content = f"""# Hecos Pure-Python SearXNG Configuration (Docker-Free)
use_default_settings: true

general:
  debug: false
  instance_name: "Hecos-SearXNG"

search:
  safe_search: 0
  autocomplete: 'duckduckgo'
  formats:
    - html
    - json

server:
  port: {port}
  bind_address: "127.0.0.1"
  secret_key: "{secret}"
  limiter: false
  image_proxy: false
  public_instance: false

redis:
  url: false

ui:
  static_use_hash: false

engines:
  - name: bing
    disabled: false
  - name: yahoo
    disabled: false
  - name: brave
    disabled: false
  - name: wikipedia
    disabled: false
  - name: duckduckgo
    disabled: false
"""
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(content)
        hecos_logger.info(f"[SEARXNG] Generated native SearXNG config: {config_path}")
    return config_path


class SearXNGComponent(BaseComponent):
    """Manages pure-Python native SearXNG daemon (Docker-Free)."""

    def __init__(self):
        super().__init__(
            component_id="searxng",
            name="SearXNG Meta-Search",
            description="Aggregates 70+ search engines into a private local Python API (No Docker required).",
            category="core",
            auto_start=True
        )

    def is_installed(self) -> bool:
        try:
            import importlib.util
            return importlib.util.find_spec("simplexng") is not None
        except Exception:
            return False

    def is_running(self) -> bool:
        cfg = get_search_config().get("searxng", {})
        url = cfg.get("url", f"http://127.0.0.1:{DEFAULT_PORT}").rstrip("/")
        try:
            r = requests.get(f"{url}/search", params={"q": "ping", "format": "json"}, timeout=1.2)
            return r.status_code == 200
        except Exception:
            return False

    def install(self, progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None) -> Tuple[bool, str]:
        if self.is_installed():
            return True, "SearXNG pure-python package is already installed."

        if progress_cb:
            progress_cb({"step": "pip", "message": "Installing pure-python SearXNG package..."})

        try:
            cmd = [sys.executable, "-m", "pip", "install", "simplexng", "waitress", "h2"]
            ret = subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ret == 0:
                return True, "SearXNG package installed successfully."
            return False, f"pip install returned error code {ret}"
        except Exception as e:
            return False, str(e)

    def start(self) -> Tuple[bool, str]:
        global _GLOBAL_SEARXNG_PROC
        if self.is_running():
            return True, "SearXNG daemon is already running."

        cfg = get_search_config().get("searxng", {})
        port = int(cfg.get("port", DEFAULT_PORT))
        settings_file = _ensure_searxng_config(port)

        hecos_logger.info(f"[SEARXNG] Spawning native SearXNG pure-python daemon on port {port}...")

        # Flags to suppress CMD window on Windows (100% invisible background process)
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW

        env = os.environ.copy()
        env["SEARXNG_SETTINGS_PATH"] = os.path.abspath(settings_file)

        cmd = [
            sys.executable,
            "-m", "simplexng.simplexng",
            "-p", str(port),
            "-H", "127.0.0.1",
            "--settings", os.path.abspath(settings_file)
        ]

        log_path = os.path.join(_get_searxng_dir(), "searxng.log")
        try:
            log_file = open(log_path, "a", encoding="utf-8")
            _GLOBAL_SEARXNG_PROC = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=log_file,
                env=env,
                startupinfo=startupinfo,
                creationflags=creationflags
            )

            # Wait for socket to become active (up to 8 seconds)
            start_t = time.time()
            while time.time() - start_t < 8.0:
                if self.is_running():
                    hecos_logger.info(f"[SEARXNG] Native SearXNG daemon active on port {port} (PID: {_GLOBAL_SEARXNG_PROC.pid})")
                    return True, f"SearXNG started on port {port}"
                if _GLOBAL_SEARXNG_PROC.poll() is not None:
                    return False, f"SearXNG process exited with code {_GLOBAL_SEARXNG_PROC.returncode}"
                time.sleep(0.35)

            return True, f"SearXNG daemon spawned on port {port}"
        except Exception as e:
            hecos_logger.error(f"[SEARXNG] Failed to spawn SearXNG daemon: {e}")
            return False, str(e)

    def stop(self) -> Tuple[bool, str]:
        global _GLOBAL_SEARXNG_PROC
        if _GLOBAL_SEARXNG_PROC and _GLOBAL_SEARXNG_PROC.poll() is None:
            try:
                _GLOBAL_SEARXNG_PROC.terminate()
                _GLOBAL_SEARXNG_PROC.wait(timeout=3.0)
            except Exception:
                try:
                    _GLOBAL_SEARXNG_PROC.kill()
                except Exception:
                    pass
            _GLOBAL_SEARXNG_PROC = None
            hecos_logger.info("[SEARXNG] Native SearXNG daemon stopped.")
            return True, "SearXNG daemon stopped."
        return True, "SearXNG was not running."

    def uninstall(self) -> Tuple[bool, str]:
        self.stop()
        return True, "SearXNG component reset."

    def get_details(self) -> Dict[str, Any]:
        cfg = get_search_config().get("searxng", {})
        return {
            "type": "Pure Python (Docker-Free)",
            "configured_url": cfg.get("url", f"http://127.0.0.1:{DEFAULT_PORT}"),
            "port": DEFAULT_PORT,
            "has_docker": False,
            "is_running": self.is_running(),
            "help": "Runs 100% locally via pure Python & waitress without Docker."
        }
