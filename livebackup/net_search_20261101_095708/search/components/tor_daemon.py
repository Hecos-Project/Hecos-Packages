"""
search/components/tor_daemon.py
Autonomous Tor daemon manager for Hecos Deep Search.
Downloads Tor Expert Bundle, configures dedicated ports, and runs headless in background.
"""
from __future__ import annotations

import os
import sys
import tarfile
import socket
import logging
import subprocess
import requests
from typing import Tuple, Dict, Any, Optional, Callable

from .base import BaseComponent
from ..config import get_search_config
from ..http_client import is_port_open, get_tor_socks_port

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.tor_daemon")

TOR_DOWNLOAD_URLS = [
    "https://dist.torproject.org/torbrowser/15.0.26/tor-expert-bundle-windows-x86_64-15.0.26.tar.gz",
    "https://archive.torproject.org/tor-package-archive/torbrowser/15.0.26/tor-expert-bundle-windows-x86_64-15.0.26.tar.gz",
]


def _get_tor_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    hecos_root = os.path.normpath(os.path.join(here, "..", "..", "..", ".."))
    tor_dir = os.path.join(hecos_root, "data", "tor")
    os.makedirs(tor_dir, exist_ok=True)
    return tor_dir


def _get_tor_exe() -> Optional[str]:
    # Check in data/tor
    data_tor = _get_tor_dir()
    for candidate in [
        os.path.join(data_tor, "tor", "tor.exe"),
        os.path.join(data_tor, "tor.exe"),
    ]:
        if os.path.isfile(candidate):
            return candidate

    # Check system PATH
    import shutil
    sys_tor = shutil.which("tor")
    if sys_tor and os.path.isfile(sys_tor):
        return sys_tor

    return None


class TorDaemonComponent(BaseComponent):
    """Manages downloading, lifecycle and circuit renewal for the Tor service."""

    def __init__(self):
        super().__init__(
            component_id="tor_daemon",
            name="Tor Network Service",
            description="Background Tor onion routing proxy for uninhibited and anonymous Dark Web search.",
            category="tor",
            auto_start=True
        )
        self._proc: Optional[subprocess.Popen] = None

    def is_installed(self) -> bool:
        return _get_tor_exe() is not None

    def is_running(self) -> bool:
        # Check if our own process is running
        if self._proc is not None and self._proc.poll() is None:
            return True
        # Or if any Tor socks port is active (dedicated 9055 or standard 9050/9150)
        return get_tor_socks_port() is not None

    def install(self, progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None) -> Tuple[bool, str]:
        tor_dir = _get_tor_dir()
        dest_archive = os.path.join(tor_dir, "tor-expert-bundle.tar.gz")

        py_exe = sys.executable
        if os.path.isfile(r"C:\Hecos\python_env\python.exe"):
            py_exe = r"C:\Hecos\python_env\python.exe"

        from hecos.core.progress import progress
        from hecos.core.progress.adapters.pip import run_pip

        phases = [
            ("deps", 20, "PySocks & stem"),
            ("download", 60, "Tor Expert Bundle"),
            ("extract", 15, "Estrazione binari"),
            ("config", 5, "Configurazione torrc"),
        ]

        task_id = "search_comp_tor_daemon"
        with progress.task(task_id, title="Setup Tor Daemon", source="HSEARCH", phases=phases, cancellable=True) as ptask:
            # 1. Install required Python SOCKS dependencies first
            ptask.phase("deps", message="Installazione dipendenze PySocks & stem...")
            if progress_cb:
                progress_cb({"step": "prep", "message": "Installing PySocks & stem for Python Tor routing..."})
            try:
                ret, _ = run_pip(["install", "PySocks", "stem"], task=ptask, python_exe=py_exe, on_progress=progress_cb)
                if ret != 0:
                    hecos_logger.warning(f"[TOR] pip install PySocks stem returned code {ret}")
            except Exception as e:
                hecos_logger.warning(f"[TOR] Failed to install stem/pysocks: {e}")

            # 2. Download Tor Expert Bundle
            ptask.phase("download", message="Download Tor Expert Bundle...")
            downloaded = False
            last_error = ""
            for url in TOR_DOWNLOAD_URLS:
                try:
                    if progress_cb:
                        progress_cb({"step": "download_start", "message": f"Downloading Tor binary from {url[:50]}..."})
                    hecos_logger.info(f"[TOR] Downloading Tor Expert Bundle: {url}...")
                    with requests.get(url, stream=True, timeout=30.0) as r:
                        r.raise_for_status()
                        total_bytes = int(r.headers.get("content-length", 0))
                        downloaded_bytes = 0
                        with open(dest_archive, "wb") as f:
                            for chunk in r.iter_content(chunk_size=131072):
                                if chunk:
                                    f.write(chunk)
                                    downloaded_bytes += len(chunk)
                                    pct = round((downloaded_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0
                                    ptask.advance(delta_bytes=len(chunk), total_bytes=total_bytes, message=f"Downloading Tor: {pct}%")
                                    if progress_cb and total_bytes > 0:
                                        progress_cb({
                                            "step": "downloading",
                                            "percent": pct,
                                            "bytes_done": downloaded_bytes,
                                            "bytes_total": total_bytes,
                                            "message": f"Downloading Tor: {pct}%"
                                        })
                    downloaded = True
                    break
                except Exception as e:
                    last_error = str(e)
                    hecos_logger.warning(f"[TOR] Download attempt failed from {url}: {e}")

            if not downloaded:
                err_msg = f"Failed to download Tor bundle: {last_error}"
                ptask.fail(err_msg)
                return False, err_msg

            # 3. Extract archive
            ptask.phase("extract", message="Estrazione archivio Tor...")
            if progress_cb:
                progress_cb({"step": "extracting", "percent": 90.0, "message": "Extracting Tor archive..."})
            try:
                with tarfile.open(dest_archive, "r:gz") as tar:
                    tar.extractall(path=tor_dir)
                if os.path.exists(dest_archive):
                    os.remove(dest_archive)
                ptask.advance(percent=95.0)
            except Exception as e:
                err_msg = f"Failed to extract Tor bundle: {e}"
                ptask.fail(err_msg)
                return False, err_msg

            # 4. Generate torrc configuration
            ptask.phase("config", message="Generazione configurazione torrc...")
            self._write_torrc()

            ptask.done("Tor daemon configurato con successo.")
            if progress_cb:
                progress_cb({"step": "done", "percent": 100.0, "message": "Tor successfully installed and configured."})

            return True, "Tor installed successfully."

    def _write_torrc(self) -> str:
        tor_dir = _get_tor_dir()
        cfg = get_search_config().get("tor", {})
        socks_port = int(cfg.get("socks_port", 9055))
        control_port = int(cfg.get("control_port", 9056))

        torrc_path = os.path.join(tor_dir, "torrc")
        data_dir = os.path.join(tor_dir, "data").replace("\\", "/")
        geoip_path = os.path.join(tor_dir, "data", "geoip").replace("\\", "/")
        geoip6_path = os.path.join(tor_dir, "data", "geoip6").replace("\\", "/")

        content = f"""# Hecos Managed Tor Configuration
SocksPort 127.0.0.1:{socks_port}
ControlPort 127.0.0.1:{control_port}
DataDirectory {data_dir}
GeoIPFile {geoip_path}
GeoIPv6File {geoip6_path}
AvoidDiskWrites 1
Log notice stdout
"""
        with open(torrc_path, "w", encoding="utf-8") as f:
            f.write(content)
        return torrc_path

    def start(self) -> Tuple[bool, str]:
        # If already listening on SOCKS, don't double start
        if self.is_running():
            port = get_tor_socks_port()
            return True, f"Tor is already running on port {port}."

        tor_exe = _get_tor_exe()
        if not tor_exe:
            return False, "Tor executable not found. Please install the Tor component first."

        tor_dir = os.path.dirname(os.path.dirname(tor_exe)) if os.path.basename(os.path.dirname(tor_exe)) == "tor" else os.path.dirname(tor_exe)
        torrc_path = self._write_torrc()

        cfg = get_search_config().get("tor", {})
        socks_port = int(cfg.get("socks_port", 9055))

        hecos_logger.info(f"[TOR] Launching {tor_exe} with config {torrc_path}...")

        # Flags to suppress CMD window on Windows
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            self._proc = subprocess.Popen(
                [tor_exe, "-f", torrc_path],
                cwd=tor_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags
            )

            # Wait for socket to become active (up to 8 seconds)
            import time
            start_t = time.time()
            while time.time() - start_t < 8.0:
                if is_port_open(socks_port):
                    hecos_logger.info(f"[TOR] Tor daemon successfully active on port {socks_port}")
                    return True, f"Tor service started on port {socks_port}"
                if self._proc.poll() is not None:
                    return False, f"Tor process exited prematurely with code {self._proc.returncode}"
                time.sleep(0.3)

            return True, f"Tor launched (port {socks_port} initializing...)"
        except Exception as e:
            hecos_logger.error(f"[TOR] Failed to launch Tor: {e}")
            return False, str(e)

    def stop(self) -> Tuple[bool, str]:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
            return True, "Tor process stopped."
        return True, "Tor process was not managed by this session."

    def new_circuit(self) -> Tuple[bool, str]:
        """Requests a new Tor circuit (IP rotation) via ControlPort."""
        cfg = get_search_config().get("tor", {})
        ctrl_port = int(cfg.get("control_port", 9056))

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3.0)
                s.connect(("127.0.0.1", ctrl_port))
                s.sendall(b"AUTHENTICATE \"\"\r\n")
                resp = s.recv(1024).decode()
                if not resp.startswith("250"):
                    return False, f"Tor auth failed: {resp.strip()}"
                s.sendall(b"SIGNAL NEWNYM\r\n")
                resp2 = s.recv(1024).decode()
                if resp2.startswith("250"):
                    return True, "New Tor identity requested successfully."
                return False, f"Tor signal failed: {resp2.strip()}"
        except Exception as e:
            return False, f"Could not connect to Tor ControlPort on {ctrl_port}: {e}"

    def uninstall(self) -> Tuple[bool, str]:
        self.stop()
        tor_dir = _get_tor_dir()
        try:
            import shutil
            if os.path.isdir(tor_dir):
                shutil.rmtree(tor_dir, ignore_errors=True)
            return True, "Tor files removed."
        except Exception as e:
            return False, str(e)

    def get_details(self) -> Dict[str, Any]:
        port = get_tor_socks_port()
        return {
            "exe_path": _get_tor_exe() or "Not found",
            "active_port": port,
            "is_system_tor": port in (9050, 9150) if port else False
        }
