"""
search/stream_hunter/vlc_bridge.py
VLC Desktop & LibVLC (python-vlc) Bridge for Hecos NetSearch Stream Hunter.
Supports:
- Launching single live streams (HLS, RTSP, RTMP, MMS, Icecast, DASH) in VLC Desktop.
- Generating and opening multi-channel .m3u8 playlists in VLC Desktop for channel zapping.
- Background audio/radio playback & ICY NowPlaying metadata inspection via python-vlc (libvlc.dll).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("net_search.vlc_bridge")


def _setup_vlc_path_win() -> Optional[str]:
    """Configures Windows DLL search path for libvlc.dll (matching Hecos media_player)."""
    if sys.platform != "win32":
        return None
    candidates = [
        os.environ.get("PYTHON_VLC_MODULE_PATH", ""),
        r"C:\Program Files\VideoLAN\VLC",
        r"C:\Program Files (x86)\VideoLAN\VLC",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\VideoLAN\VLC"),
    ]
    for path in candidates:
        if path and os.path.isfile(os.path.join(path, "libvlc.dll")):
            os.environ["PYTHON_VLC_MODULE_PATH"] = path
            try:
                os.add_dll_directory(path)
            except Exception:
                pass
            return path
    return None


def find_vlc_exe() -> Optional[str]:
    """Finds the VLC desktop executable across Windows, Linux, and macOS."""
    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\VideoLAN\VLC\vlc.exe"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
    which_vlc = shutil.which("vlc")
    if which_vlc:
        return which_vlc
    return None


def get_vlc_capabilities() -> Dict[str, Any]:
    """Reports availability of VLC Desktop executable and python-vlc (libvlc.dll)."""
    dll_dir = _setup_vlc_path_win()
    exe_path = find_vlc_exe()
    has_libvlc = False
    libvlc_version = ""
    try:
        import vlc  # type: ignore
        has_libvlc = True
        try:
            libvlc_version = vlc.libvlc_get_version().decode("utf-8", errors="ignore")
        except Exception:
            libvlc_version = "available"
    except Exception as e:
        has_libvlc = False
        hecos_logger.debug(f"[StreamVLC] python-vlc / libvlc capability check failed: {e}")

    hecos_logger.debug(
        f"[StreamVLC] Capabilities: desktop={bool(exe_path)} ({exe_path}), "
        f"libvlc={has_libvlc} ({libvlc_version or 'n/a'})"
    )
    return {
        "vlc_exe": exe_path,
        "has_vlc_desktop": bool(exe_path),
        "has_libvlc": has_libvlc,
        "libvlc_dir": dll_dir,
        "libvlc_version": libvlc_version,
    }


def generate_m3u_playlist_text(streams: List[Dict[str, Any]]) -> str:
    """Builds a standard #EXTM3U playlist string from a list of stream dicts."""
    lines = ["#EXTM3U"]
    for idx, st in enumerate(streams or [], 1):
        stream_url = (st.get("stream_url") or st.get("url") or "").strip()
        if not stream_url:
            continue
        title = (st.get("title") or f"Stream {idx}").replace("\n", " ").replace("\r", " ").strip()
        cat = (st.get("category") or st.get("stream_category") or "Live").upper()
        country = (st.get("country") or "INT").upper()
        logo = (st.get("logo") or st.get("thumbnail") or "").strip()
        attrs = [f'group-title="{cat} ({country})"']
        if logo:
            attrs.append(f'tvg-logo="{logo}"')
        if country:
            attrs.append(f'tvg-country="{country}"')
        attr_str = " ".join(attrs)
        lines.append(f"#EXTINF:-1 {attr_str},{title}")
        lines.append(stream_url)
    return "\n".join(lines) + "\n"


def _build_desktop_vlc_env() -> Dict[str, str]:
    """Builds a clean child environment for desktop vlc.exe without broken plugin overrides."""
    env = os.environ.copy()
    plugin_path = env.get("VLC_PLUGIN_PATH", "")
    # python-vlc setup sometimes points VLC_PLUGIN_PATH to the root VLC dir instead of plugins\;
    # desktop vlc.exe resolves its own plugins folder cleanly when that override is omitted.
    if plugin_path and not plugin_path.lower().rstrip("\\/").endswith("plugins"):
        env.pop("VLC_PLUGIN_PATH", None)
    return env


def _is_vlc_desktop_process_running() -> bool:
    """Returns True if a desktop VLC GUI process (vlc.exe / vlc) is currently alive."""
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq vlc.exe", "/NH"],
                text=True,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=2.0,
            )
            return "vlc.exe" in (out or "").lower()
        res = subprocess.run(
            ["pgrep", "-x", "vlc"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
        return res.returncode == 0
    except Exception:
        return False


def _spawn_vlc_desktop_process(vlc_exe: str, extra_args: List[str], silent: bool = False) -> str:
    """Spawns desktop VLC, suppressing window/taskbar activation when passing IPC args silently."""
    if sys.platform == "win32":
        if silent:
            subprocess.Popen(
                [vlc_exe, *extra_args],
                env=_build_desktop_vlc_env(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            return "popen_silent_ipc"

        # Prefer ShellExecuteW(SW_SHOWNORMAL=1) for initial cold launch so background daemon parents
        # still activate and display the VLC GUI window on the user's interactive desktop.
        try:
            import ctypes
            params = subprocess.list2cmdline(extra_args)
            work_dir = os.path.dirname(vlc_exe) or None
            ret = ctypes.windll.shell32.ShellExecuteW(None, "open", vlc_exe, params, work_dir, 1)
            if int(ret) > 32:
                return f"shell_execute:{int(ret)}"
            hecos_logger.debug(f"[StreamVLC] ShellExecuteW returned {ret}, falling back to Popen")
        except Exception as e:
            hecos_logger.debug(f"[StreamVLC] ShellExecuteW error, falling back to Popen: {e}")

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 1  # SW_SHOWNORMAL
        subprocess.Popen(
            [vlc_exe, *extra_args],
            env=_build_desktop_vlc_env(),
            startupinfo=startupinfo,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        return "popen_shownormal"

    subprocess.Popen(
        [vlc_exe, *extra_args],
        env=_build_desktop_vlc_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return "popen_posix"


class _VLCDesktopController:
    """Manages an active VLC Desktop window via its local loopback HTTP interface.

    Switching channels over HTTP avoids spawning secondary `vlc.exe` processes via
    `ShellExecuteW`, preventing Windows taskbar popups and keeping VLC in fullscreen.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._port: Optional[int] = None
        self._password: str = secrets.token_urlsafe(12)
        self._fullscreen_intent: Optional[bool] = None
        self._fs_guard_gen: int = 0

    def _ensure_credentials(self) -> tuple[int, str]:
        if self._port is None:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                self._port = int(sock.getsockname()[1])
        return self._port, self._password

    def http_command(
        self, params: Optional[Dict[str, str]] = None, timeout: float = 1.5
    ) -> Optional[Dict[str, Any]]:
        port = self._port
        if not port:
            return None
        url = f"http://127.0.0.1:{port}/requests/status.json"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        auth_b64 = base64.b64encode(f":{self._password}".encode("utf-8")).decode("ascii")
        req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth_b64}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace").strip()
                if not raw:
                    return {}
                try:
                    data = json.loads(raw)
                    return data if isinstance(data, dict) else {}
                except json.JSONDecodeError:
                    return {}
        except (urllib.error.URLError, OSError, TimeoutError):
            return None

    def is_http_alive(self) -> bool:
        return self.http_command(timeout=0.4) is not None

    def _schedule_fullscreen_guard(self) -> None:
        with self._lock:
            self._fs_guard_gen += 1
            gen = self._fs_guard_gen

        def _guard() -> None:
            for delay in (0.18, 0.45, 0.9, 1.5):
                time.sleep(delay)
                with self._lock:
                    if gen != self._fs_guard_gen or self._fullscreen_intent is False:
                        return
                st = self.http_command(timeout=0.8)
                if st is None:
                    return
                if bool(st.get("fullscreen")):
                    if st.get("state") == "playing":
                        return
                    continue
                if st.get("state") in ("playing", "opening", "buffering") or delay >= 0.45:
                    res = self.http_command({"command": "fullscreen"}, timeout=0.8)
                    if res and bool(res.get("fullscreen")):
                        hecos_logger.debug(f"[StreamVLC] Restored VLC fullscreen after channel switch ({delay}s)")
                        return

        threading.Thread(target=_guard, name="vlc-fs-guard", daemon=True).start()

    def play_or_switch(
        self, vlc_exe: str, stream_url: str, title: str = "", fullscreen: Optional[bool] = None
    ) -> Dict[str, Any]:
        u = (stream_url or "").strip()
        clean_title = (title or "").replace("\r", " ").replace("\n", " ").strip()

        # 1. Fast path: VLC already running with Hecos HTTP RC active -> seamless in-process switch
        status_before = self.http_command(timeout=0.5)
        if status_before is not None:
            was_fs = bool(status_before.get("fullscreen"))
            keep_fs = bool(fullscreen) if fullscreen is not None else was_fs
            self._fullscreen_intent = keep_fs

            sw_status = self.http_command({"command": "in_play", "input": u}, timeout=2.0)
            if sw_status is not None:
                if fullscreen is False and bool(sw_status.get("fullscreen")):
                    self.http_command({"command": "fullscreen"}, timeout=0.8)
                elif keep_fs:
                    if not bool(sw_status.get("fullscreen")):
                        self.http_command({"command": "fullscreen"}, timeout=0.8)
                    self._schedule_fullscreen_guard()
                hecos_logger.info(
                    f"[StreamVLC] Switched channel seamlessly via VLC HTTP "
                    f"(keep_fullscreen={keep_fs}) for '{clean_title or u}' -> {u}"
                )
                return {
                    "ok": True,
                    "vlc_exe": vlc_exe,
                    "stream_url": u,
                    "title": clean_title,
                    "launch_method": "vlc_http_switch",
                    "fullscreen": keep_fs,
                }

        # 2. Fallback / cold launch
        already_running = _is_vlc_desktop_process_running()
        want_fs = bool(fullscreen) if fullscreen is not None else (self._fullscreen_intent is True)
        if fullscreen is not None:
            self._fullscreen_intent = bool(fullscreen)

        if already_running:
            # VLC was opened manually without HTTP RC: spawn IPC helper silently so taskbar does not pop
            extra_args = [
                "--one-instance",
                "--no-playlist-enqueue",
                "--no-qt-video-autoresize",
                "--network-caching=1500",
                "--no-video-title-show" if not clean_title else f"--meta-title={clean_title}",
            ]
            if want_fs:
                extra_args.append("--fullscreen")
            extra_args.append(u)
            method = _spawn_vlc_desktop_process(vlc_exe, extra_args, silent=True)
            hecos_logger.info(
                f"[StreamVLC] Dispatched silent IPC switch ({method}) to existing VLC for '{clean_title or u}' -> {u}"
            )
            return {
                "ok": True,
                "vlc_exe": vlc_exe,
                "stream_url": u,
                "title": clean_title,
                "launch_method": method,
                "fullscreen": want_fs,
            }

        port, pwd = self._ensure_credentials()
        extra_args = [
            "--one-instance",
            "--no-playlist-enqueue",
            "--extraintf=http",
            "--http-host=127.0.0.1",
            f"--http-port={port}",
            f"--http-password={pwd}",
            "--no-qt-video-autoresize",
            "--no-qt-privacy-ask",
            "--network-caching=1500",
            "--no-video-title-show" if not clean_title else f"--meta-title={clean_title}",
        ]
        if want_fs:
            extra_args.append("--fullscreen")
        extra_args.append(u)

        method = _spawn_vlc_desktop_process(vlc_exe, extra_args, silent=False)
        # Wait briefly for VLC HTTP interface to bind so rapid consecutive switches stay seamless
        for _ in range(12):
            if self.http_command(timeout=0.15) is not None:
                break
            time.sleep(0.1)

        hecos_logger.info(
            f"[StreamVLC] Launched desktop VLC ({method}, http_port={port}, fs={want_fs}) "
            f"for '{clean_title or u}' -> {u}"
        )
        return {
            "ok": True,
            "vlc_exe": vlc_exe,
            "stream_url": u,
            "title": clean_title,
            "launch_method": method,
            "fullscreen": want_fs,
        }

    def control(
        self, action: str, fullscreen: Optional[bool] = None, volume: Optional[int] = None
    ) -> Dict[str, Any]:
        act = (action or "").strip().lower()
        st = self.http_command(timeout=0.6)
        if st is None:
            if act == "fullscreen":
                desired = (not bool(self._fullscreen_intent)) if fullscreen is None else bool(fullscreen)
                self._fullscreen_intent = desired
                return {
                    "ok": True,
                    "launch_method": "deferred_fullscreen",
                    "fullscreen": desired,
                }
            return {"ok": False, "error": "VLC Desktop HTTP remote not active"}

        res = st
        if act == "stop":
            with self._lock:
                self._fs_guard_gen += 1
            res = self.http_command({"command": "pl_stop"}, timeout=1.0) or st
        elif act == "pause":
            res = self.http_command({"command": "pl_pause"}, timeout=1.0) or st
        elif act in ("volume", "mute") and volume is not None:
            vlc_vol = max(0, min(256, round(int(volume) * 256 / 100)))
            res = self.http_command({"command": "volume", "val": str(vlc_vol)}, timeout=1.0) or st
        elif act == "fullscreen":
            cur_fs = bool(st.get("fullscreen"))
            desired = (not cur_fs) if fullscreen is None else bool(fullscreen)
            self._fullscreen_intent = desired
            if cur_fs != desired:
                res = self.http_command({"command": "fullscreen"}, timeout=1.0) or st
                # Verify final toggle state
                if bool(res.get("fullscreen")) != desired:
                    time.sleep(0.12)
                    res = self.http_command(timeout=0.8) or res
        fs_now = bool(res.get("fullscreen"))
        return {
            "ok": True,
            "launch_method": "vlc_http_control",
            "fullscreen": fs_now,
            "state": res.get("state"),
            "volume": res.get("volume"),
        }


_VLC_DESKTOP = _VLCDesktopController()


def is_vlc_desktop_http_active() -> bool:
    return _VLC_DESKTOP.is_http_alive()


def control_vlc_desktop(
    action: str, fullscreen: Optional[bool] = None, volume: Optional[int] = None
) -> Dict[str, Any]:
    return _VLC_DESKTOP.control(action=action, fullscreen=fullscreen, volume=volume)


def launch_in_vlc_desktop(
    stream_url: str, title: str = "", fullscreen: Optional[bool] = None
) -> Dict[str, Any]:
    """Launches or seamlessly switches a live stream in VLC Desktop, preserving fullscreen."""
    u = (stream_url or "").strip()
    if not u:
        return {"ok": False, "error": "Missing stream_url"}

    vlc_exe = find_vlc_exe()
    if not vlc_exe:
        hecos_logger.warning("[StreamVLC] VLC Desktop (vlc.exe) not found on this system.")
        return {"ok": False, "error": "VLC Desktop (vlc.exe) not found on this system."}

    try:
        return _VLC_DESKTOP.play_or_switch(vlc_exe, u, title=title, fullscreen=fullscreen)
    except Exception as e:
        hecos_logger.warning(f"[StreamVLC] Failed to launch desktop VLC for {u}: {e}")
        return {"ok": False, "error": str(e)}


def launch_playlist_in_vlc(streams: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Writes an .m3u8 playlist of the provided streams and opens it in VLC Desktop."""
    if not streams:
        return {"ok": False, "error": "No streams provided for playlist"}

    vlc_exe = find_vlc_exe()
    if not vlc_exe:
        hecos_logger.warning("[StreamVLC] VLC Desktop (vlc.exe) not found on this system.")
        return {"ok": False, "error": "VLC Desktop (vlc.exe) not found on this system."}

    m3u_content = generate_m3u_playlist_text(streams)
    tmp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "stream_hunter_cache"))
    os.makedirs(tmp_dir, exist_ok=True)
    playlist_path = os.path.join(tmp_dir, "hecos_netsearch_live.m3u8")

    try:
        with open(playlist_path, "w", encoding="utf-8") as f:
            f.write(m3u_content)

        method = _spawn_vlc_desktop_process(
            vlc_exe,
            ["--one-instance", "--no-playlist-enqueue", "--network-caching=1500", playlist_path],
        )
        hecos_logger.info(f"[StreamVLC] Launched desktop VLC playlist ({method}, {len(streams)} streams) -> {playlist_path}")
        return {
            "ok": True,
            "playlist_path": playlist_path,
            "count": len(streams),
            "vlc_exe": vlc_exe,
            "launch_method": method,
        }
    except Exception as e:
        hecos_logger.warning(f"[StreamVLC] Failed to launch playlist in VLC: {e}")
        return {"ok": False, "error": str(e)}


class _LibVLCAudioBridge:
    """Optional background LibVLC instance for headless audio/radio playback & ICY metadata."""

    def __init__(self):
        self._lock = threading.Lock()
        self._instance = None
        self._player = None
        self._current_url = ""
        self._current_title = ""

    def _ensure_player(self) -> bool:
        if self._player is not None:
            return True
        _setup_vlc_path_win()
        try:
            import vlc  # type: ignore
            self._instance = vlc.Instance("--no-xlib", "--quiet", "--no-video", "--network-caching=1500")
            self._player = self._instance.media_player_new()
            hecos_logger.info("[StreamVLC] Initialized headless LibVLC audio player instance")
            return True
        except Exception as e:
            hecos_logger.warning(f"[StreamVLC] LibVLC player initialization failed: {e}")
            return False

    def control(self, action: str, url: str = "", title: str = "", volume: int = 85) -> Dict[str, Any]:
        with self._lock:
            if not self._ensure_player():
                return {"ok": False, "error": "python-vlc / libvlc.dll not available"}
            import vlc  # type: ignore

            act = (action or "status").lower()
            if act == "play" and url:
                media = self._instance.media_new(url)
                self._player.set_media(media)
                self._player.audio_set_volume(max(0, min(100, int(volume))))
                self._player.play()
                self._current_url = url
                self._current_title = title
                hecos_logger.info(f"[StreamVLC] LibVLC play '{title or url}' vol={volume}% -> {url}")
            elif act == "stop":
                self._player.stop()
                hecos_logger.info(f"[StreamVLC] LibVLC stopped ({self._current_title or self._current_url})")
            elif act == "pause":
                self._player.pause()
                hecos_logger.info("[StreamVLC] LibVLC pause toggled")
            elif act == "volume":
                self._player.audio_set_volume(max(0, min(100, int(volume))))
                hecos_logger.debug(f"[StreamVLC] LibVLC volume set to {volume}%")

            now_playing = ""
            try:
                media = self._player.get_media()
                if media:
                    np = media.get_meta(vlc.Meta.NowPlaying) or media.get_meta(vlc.Meta.Title) or ""
                    if np and np != self._current_url:
                        now_playing = np
            except Exception:
                pass

            return {
                "ok": True,
                "is_playing": bool(self._player.is_playing()),
                "url": self._current_url,
                "title": self._current_title,
                "now_playing": now_playing,
                "volume": self._player.audio_get_volume(),
            }


_LIBVLC_BRIDGE = _LibVLCAudioBridge()


def control_libvlc_bg(action: str, url: str = "", title: str = "", volume: int = 85) -> Dict[str, Any]:
    return _LIBVLC_BRIDGE.control(action=action, url=url, title=title, volume=volume)
