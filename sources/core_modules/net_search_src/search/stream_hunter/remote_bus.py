"""
search/stream_hunter/remote_bus.py
Thread-safe State & Command Bus for the Live Streams TV Remote & AI Voice/LLM Control.
Synchronizes channel lineup, active channel, playback target (In-App / VLC Desktop / LibVLC),
volume, mute, proxy mode, and remote commands across:
  - Main /search Stream Hunter UI
  - Floating / Pop-out Multi-Monitor TV Remote (/search/stream_remote)
  - Global Hecos LLM Tools (/streams, stream_control, stream_search)
  - Net Search AI Copilot & Voice Controller
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from hecos.modules.net_search.search.config import get_stream_preset_settings

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("net_search.stream_remote_bus")

VALID_TARGETS = {"app", "vlc", "libvlc"}
VALID_CATEGORIES = {"all", "tv", "radio", "webcam", "raw"}

_IT_WORDS = {"rai", "mediaset", "la7", "tv8", "nove", "sky", "rtl", "rds", "deejay", "105", "italia"}
_QUERY_FILLERS = {
    "live", "stream", "streaming", "diretta", "canale", "channel",
    "tv", "radio", "webcam", "hd", "fta", "online", "watch", "guarda",
}


def normalize_target(raw: Any) -> Optional[str]:
    """Normalize human/LLM target names ('VLC Desktop', 'in-app', 'libvlc') to valid target keys."""
    if not raw:
        return None
    s = str(raw).strip().lower()
    if s in VALID_TARGETS:
        return s
    if "libvlc" in s or "headless" in s or "background" in s:
        return "libvlc"
    if "vlc" in s or "desktop" in s or "external" in s:
        return "vlc"
    if "app" in s or "dock" in s or "web" in s or "browser" in s:
        return "app"
    return None


def parse_channel_or_query(channel_val: Any, query_val: str = "") -> Tuple[Optional[int], str]:
    """Safely separate an integer channel number from a string channel name passed in `channel`."""
    q = (query_val or "").strip()
    if channel_val is None or channel_val == "":
        return None, q
    if isinstance(channel_val, int):
        return channel_val, q
    s = str(channel_val).strip()
    if not s:
        return None, q
    m = re.match(r"^(?:ch|canale|channel)?\s*#?(\d{1,3})$", s, flags=re.IGNORECASE)
    if m:
        return int(m.group(1)), q
    # LLM passed a channel name like "Rai 1" in `channel`: treat as query
    if not q or s.lower() in q.lower():
        return None, s
    return None, q



def _compact_stream(st: Dict[str, Any], ch_num: int) -> Dict[str, Any]:
    """Return a clean UI/Remote-safe stream dict carrying its 1-based channel number."""
    url = str(st.get("stream_url") or st.get("url") or "").strip()
    return {
        "ch_num": ch_num,
        "id": st.get("id") or f"ch_{ch_num}",
        "title": str(st.get("title") or f"Channel {ch_num}").strip(),
        "stream_url": url,
        "url": url,
        "category": str(st.get("category") or "tv").lower(),
        "protocol": str(st.get("protocol") or "HLS").upper(),
        "country": str(st.get("country") or "").upper(),
        "language": str(st.get("language") or ""),
        "source": str(st.get("source") or ""),
        "thumbnail": str(st.get("thumbnail") or ""),
        "alive": st.get("alive"),
        "bitrate": st.get("bitrate"),
        "resolution": st.get("resolution"),
    }


def _score_stream_match(st: Dict[str, Any], tokens: List[str], full_query: str) -> float:
    title = (st.get("title") or "").lower()
    cat = (st.get("category") or "").lower()
    country = (st.get("country") or "").lower()
    proto = (st.get("protocol") or "").lower()
    src = (st.get("source") or "").lower()
    if not title and not url_str(st):
        return 0.0
    clean_tokens = [t for t in tokens if t and t not in _QUERY_FILLERS]
    if not clean_tokens and tokens:
        clean_tokens = tokens
    clean_query = " ".join(clean_tokens)
    score = 0.0
    if clean_query and clean_query == title:
        score += 120.0
    elif clean_query and clean_query in title:
        score += 85.0
    elif clean_query and clean_query.replace(" ", "") in title.replace(" ", ""):
        score += 75.0
    matched = 0
    for tok in clean_tokens:
        if re.search(rf"\b{re.escape(tok)}\b", title):
            score += 30.0
            matched += 1
        elif tok in title:
            score += 20.0
            matched += 1
        elif tok == country or tok == cat or tok == proto:
            score += 12.0
            matched += 1
        elif tok in src:
            score += 5.0
            matched += 1
    if len(clean_tokens) > 1 and matched < len(clean_tokens):
        return 0.0
    if clean_tokens and matched == len(clean_tokens):
        score += 30.0
    if st.get("alive") is True:
        score += 6.0
    elif st.get("alive") is False:
        score -= 10.0
    return score


def url_str(st: Dict[str, Any]) -> str:
    return str(st.get("stream_url") or st.get("url") or "").strip()


class StreamRemoteBus:
    """In-memory command & state bus shared between browser remotes and backend AI tools."""

    def __init__(self, max_pending: int = 80):
        self._lock = threading.RLock()
        self._max_pending = max_pending
        self._queue: List[Dict[str, Any]] = []
        self._active_index: int = -1
        self._last_index: int = -1
        self._volume: int = 85
        self._muted: bool = False
        self._paused: bool = False
        self._fullscreen: bool = False
        self._target: str = "app"  # app | vlc | libvlc
        self._proxy_enabled: bool = False
        self._category: str = "all"
        self._query: str = ""
        self._state_version: int = 1
        self._command_seq: int = 0
        self._pending_commands: List[Dict[str, Any]] = []
        self._last_client_sync: float = 0.0

    def has_active_browser_client(self, max_age_sec: float = 15.0) -> bool:
        with self._lock:
            return (time.time() - self._last_client_sync) <= max_age_sec

    def _enqueue_command_locked(
        self, command: str, payload: Optional[Dict[str, Any]] = None, source: str = "ui"
    ) -> Dict[str, Any]:
        self._command_seq += 1
        cmd_obj = {
            "seq": self._command_seq,
            "command": command,
            "payload": dict(payload or {}),
            "source": source,
            "ts": round(time.time(), 3),
        }
        self._pending_commands.append(cmd_obj)
        if len(self._pending_commands) > self._max_pending:
            self._pending_commands = self._pending_commands[-self._max_pending:]
        self._state_version += 1
        return cmd_obj

    def _set_active_index_locked(self, idx: int) -> Optional[Dict[str, Any]]:
        if 0 <= idx < len(self._queue):
            if self._active_index >= 0 and self._active_index != idx:
                self._last_index = self._active_index
            self._active_index = idx
            self._paused = False
            self._state_version += 1
            return self._queue[idx]
        return None

    def sync_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Accepts state updates from the primary /search Live Streams UI."""
        with self._lock:
            self._last_client_sync = time.time()
            if "queue" in payload and isinstance(payload["queue"], list):
                new_q: List[Dict[str, Any]] = []
                for idx, item in enumerate(payload["queue"][:1000], 1):
                    if isinstance(item, dict) and url_str(item):
                        new_q.append(_compact_stream(item, idx))
                self._queue = new_q
                if self._active_index >= len(self._queue):
                    self._active_index = -1

            if "active_index" in payload and payload["active_index"] is not None:
                try:
                    ai = int(payload["active_index"])
                    if -1 <= ai < len(self._queue):
                        if ai != self._active_index and self._active_index >= 0:
                            self._last_index = self._active_index
                        self._active_index = ai
                except (TypeError, ValueError):
                    pass
            elif "active_channel" in payload and payload["active_channel"] is not None:
                try:
                    ch = int(payload["active_channel"])
                    if 1 <= ch <= len(self._queue):
                        if (ch - 1) != self._active_index and self._active_index >= 0:
                            self._last_index = self._active_index
                        self._active_index = ch - 1
                except (TypeError, ValueError):
                    pass

            if "volume" in payload and payload["volume"] is not None:
                try:
                    self._volume = max(0, min(100, int(payload["volume"])))
                except (TypeError, ValueError):
                    pass
            if "muted" in payload:
                self._muted = bool(payload["muted"])
            if "paused" in payload:
                self._paused = bool(payload["paused"])
            if payload.get("target") in VALID_TARGETS:
                self._target = str(payload["target"])
            if "proxy_enabled" in payload:
                self._proxy_enabled = bool(payload["proxy_enabled"])
            if payload.get("category") in VALID_CATEGORIES:
                self._category = str(payload["category"])
            if "query" in payload and payload["query"] is not None:
                self._query = str(payload["query"])

            self._state_version += 1
            return self.get_state()

    def get_state(self, since_seq: int = 0) -> Dict[str, Any]:
        with self._lock:
            active_stream = (
                self._queue[self._active_index]
                if 0 <= self._active_index < len(self._queue)
                else None
            )
            last_stream = (
                self._queue[self._last_index]
                if 0 <= self._last_index < len(self._queue)
                else None
            )
            pending = [c for c in self._pending_commands if c["seq"] > since_seq]
            return {
                "ok": True,
                "state_version": self._state_version,
                "command_seq": self._command_seq,
                "pending_commands": pending,
                "queue_count": len(self._queue),
                "queue": list(self._queue),
                "active_index": self._active_index,
                "active_channel": (self._active_index + 1) if active_stream else None,
                "active_stream": active_stream,
                "last_index": self._last_index,
                "last_channel": (self._last_index + 1) if last_stream else None,
                "last_stream": last_stream,
                "volume": self._volume,
                "muted": self._muted,
                "paused": self._paused,
                "fullscreen": self._fullscreen,
                "target": self._target,
                "proxy_enabled": self._proxy_enabled,
                "category": self._category,
                "query": self._query,
                "browser_active": (time.time() - self._last_client_sync) <= 15.0,
                "preset_settings": get_stream_preset_settings(),
            }

    def resolve_channel(
        self, channel: Optional[int] = None, query: str = ""
    ) -> Optional[Tuple[int, Dict[str, Any]]]:
        with self._lock:
            if channel is not None:
                try:
                    idx = int(channel) - 1
                    if 0 <= idx < len(self._queue):
                        return idx, self._queue[idx]
                except (TypeError, ValueError):
                    pass

            clean_q = re.sub(r"[^\w\s\-+]", " ", (query or "").strip().lower()).strip()
            if not clean_q:
                return None
            tokens = [t for t in clean_q.split() if len(t) >= 2 or t.isdigit()]
            best_idx = -1
            best_score = 0.0
            for idx, st in enumerate(self._queue):
                sc = _score_stream_match(st, tokens, clean_q)
                if sc > best_score:
                    best_score = sc
                    best_idx = idx
            if best_idx >= 0 and best_score >= 20.0:
                return best_idx, self._queue[best_idx]
            return None

    def _populate_queue_from_search(
        self, query: str, category: str = "all", max_results: int = 40
    ) -> List[Dict[str, Any]]:
        """Run StreamHunter discovery and populate the shared queue."""
        try:
            from hecos.modules.net_search.search.stream_hunter import search_streams

            cat = category if category in VALID_CATEGORIES else "all"
            if cat == "all" and any(w in (query or "").lower() for w in _IT_WORDS):
                cat = "tv"
            res = search_streams(query=query or "", category=cat, max_results=max_results)
            streams = res.get("streams") or []
            compact = [
                _compact_stream(st, idx)
                for idx, st in enumerate(streams, 1)
                if url_str(st)
            ]
            with self._lock:
                self._queue = compact
                self._query = query or ""
                self._category = cat
                self._active_index = 0 if compact else -1
                self._state_version += 1
            return compact
        except Exception as e:
            hecos_logger.warning(f"[StreamRemoteBus] Headless discovery failed: {e}")
            return []

    def _execute_headless_target(
        self,
        action: str,
        stream_obj: Optional[Dict[str, Any]] = None,
        force_vlc: bool = False,
        fullscreen: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Executes playback actions directly in VLC Desktop or LibVLC when requested."""
        try:
            from hecos.modules.net_search.search.stream_hunter.vlc_bridge import (
                control_libvlc_bg,
                control_vlc_desktop,
                is_vlc_desktop_http_active,
                launch_in_vlc_desktop,
            )
        except Exception as e:
            return {"ok": False, "error": f"vlc_bridge unavailable: {e}"}

        target = "vlc" if force_vlc else self._target
        hecos_logger.info(
            f"[StreamRemoteBus] _execute_headless_target: action={action} target={target} "
            f"force_vlc={force_vlc} title={(stream_obj or {}).get('title')!r}"
        )
        if action == "play" and stream_obj:
            url = url_str(stream_obj)
            title = stream_obj.get("title") or "Hecos Live Stream"
            if target == "vlc":
                return launch_in_vlc_desktop(url, title=title, fullscreen=fullscreen)
            if target == "libvlc":
                return control_libvlc_bg("play", url=url, title=title, volume=0 if self._muted else self._volume)
        elif target == "vlc" or (self._target != "libvlc" and is_vlc_desktop_http_active()):
            if action in ("stop", "pause"):
                return control_vlc_desktop(action)
            if action in ("volume", "mute"):
                return control_vlc_desktop("volume", volume=0 if self._muted else self._volume)
            if action == "fullscreen":
                return control_vlc_desktop("fullscreen", fullscreen=fullscreen)
        elif target == "libvlc":
            if action == "stop":
                return control_libvlc_bg("stop")
            if action == "pause":
                return control_libvlc_bg("pause")
            if action in ("volume", "mute"):
                return control_libvlc_bg("volume", volume=0 if self._muted else self._volume)
        return {"ok": True, "deferred_to_browser": True}

    def dispatch_command(
        self,
        command: str,
        payload: Optional[Dict[str, Any]] = None,
        source: str = "ui",
        allow_headless_fallback: bool = True,
    ) -> Dict[str, Any]:
        """Process a remote command, update shared state, and broadcast to listeners."""
        cmd = (command or "").strip().lower()
        data = dict(payload or {})
        backend_exec: Dict[str, Any] = {}
        chosen_stream: Optional[Dict[str, Any]] = None

        with self._lock:
            if data.get("target"):
                norm_t = normalize_target(data.get("target"))
                if norm_t:
                    self._target = norm_t
                    data["target"] = norm_t

            if cmd in ("play_channel", "channel", "tune", "play_query", "play"):
                ch_int, eff_q = parse_channel_or_query(data.get("channel"), str(data.get("query") or ""))
                if ch_int is not None:
                    data["channel"] = ch_int
                else:
                    data.pop("channel", None)
                if eff_q:
                    data["query"] = eff_q
                if cmd in ("play_channel", "channel", "tune") and ch_int is None and eff_q:
                    cmd = "play_query"

            q_len = len(self._queue)
            if cmd in ("play_channel", "channel", "tune") and data.get("channel") is not None:
                resolved = self.resolve_channel(channel=data.get("channel"))
                if resolved:
                    idx, chosen_stream = resolved
                    self._set_active_index_locked(idx)
                    data["channel"] = idx + 1
                    data["index"] = idx
                    data["stream"] = chosen_stream
                else:
                    return {
                        "ok": False,
                        "error": f"Channel {data.get('channel')} not found in lineup (1..{q_len}).",
                        "state": self.get_state(),
                    }

            elif cmd in ("play_query", "play") and (data.get("query") or data.get("stream_url")):
                q_str = str(data.get("query") or "").strip()
                resolved = self.resolve_channel(channel=data.get("channel"), query=q_str) if q_str else None
                if resolved:
                    idx, chosen_stream = resolved
                    self._set_active_index_locked(idx)
                    data["channel"] = idx + 1
                    data["index"] = idx
                    data["stream"] = chosen_stream
                    cmd = "play_channel"
                elif data.get("stream_url"):
                    chosen_stream = _compact_stream(
                        {"stream_url": data["stream_url"], "title": data.get("title") or "Direct Stream"},
                        max(1, q_len + 1),
                    )
                    data["stream"] = chosen_stream
                elif q_str:
                    # Release lock during network search, then pick best channel
                    pass

            elif cmd in ("ch_up", "next"):
                if q_len > 0:
                    nxt = 0 if self._active_index < 0 else (self._active_index + 1) % q_len
                    chosen_stream = self._set_active_index_locked(nxt)
                    data["channel"] = nxt + 1
                    data["index"] = nxt
                    data["stream"] = chosen_stream
                else:
                    return {"ok": False, "error": "Channel lineup is empty.", "state": self.get_state()}

            elif cmd in ("ch_down", "prev"):
                if q_len > 0:
                    prv = (q_len - 1) if self._active_index <= 0 else (self._active_index - 1)
                    chosen_stream = self._set_active_index_locked(prv)
                    data["channel"] = prv + 1
                    data["index"] = prv
                    data["stream"] = chosen_stream
                else:
                    return {"ok": False, "error": "Channel lineup is empty.", "state": self.get_state()}

            elif cmd == "last":
                if 0 <= self._last_index < q_len:
                    chosen_stream = self._set_active_index_locked(self._last_index)
                    data["channel"] = self._active_index + 1
                    data["index"] = self._active_index
                    data["stream"] = chosen_stream
                else:
                    return {"ok": False, "error": "No previous channel in history.", "state": self.get_state()}

            elif cmd == "stop":
                self._paused = False
                self._active_index = -1
                self._state_version += 1

            elif cmd in ("pause", "play_pause"):
                self._paused = not self._paused
                self._state_version += 1

            elif cmd == "vol_up":
                step = int(data.get("step", 10))
                self._muted = False
                self._volume = max(0, min(100, self._volume + step))
                data["volume"] = self._volume
                self._state_version += 1

            elif cmd == "vol_down":
                step = int(data.get("step", 10))
                self._volume = max(0, min(100, self._volume - step))
                data["volume"] = self._volume
                self._state_version += 1

            elif cmd == "set_volume":
                vol = int(data.get("volume", self._volume))
                self._volume = max(0, min(100, vol))
                if self._volume > 0:
                    self._muted = False
                data["volume"] = self._volume
                self._state_version += 1

            elif cmd == "mute":
                if "muted" in data:
                    self._muted = bool(data["muted"])
                else:
                    self._muted = not self._muted
                data["muted"] = self._muted
                self._state_version += 1

            elif cmd == "target":
                tgt = str(data.get("target") or "").lower()
                if tgt not in VALID_TARGETS:
                    order = ["app", "vlc", "libvlc"]
                    tgt = order[(order.index(self._target) + 1) % len(order)] if self._target in order else "app"
                self._target = tgt
                data["target"] = tgt
                self._state_version += 1

            elif cmd == "toggle_proxy":
                self._proxy_enabled = bool(data["proxy_enabled"]) if "proxy_enabled" in data else (not self._proxy_enabled)
                data["proxy_enabled"] = self._proxy_enabled
                self._state_version += 1

            elif cmd == "fullscreen":
                if "fullscreen" in data:
                    self._fullscreen = bool(data["fullscreen"])
                else:
                    self._fullscreen = not self._fullscreen
                data["fullscreen"] = self._fullscreen
                self._state_version += 1

            elif cmd == "category":
                cat = str(data.get("category") or "all").lower()
                self._category = cat if cat in VALID_CATEGORIES else "all"
                data["category"] = self._category
                self._state_version += 1

            elif cmd == "open_vlc":
                if data.get("channel") is not None or data.get("query"):
                    resolved = self.resolve_channel(data.get("channel"), str(data.get("query") or ""))
                    if resolved:
                        idx, chosen_stream = resolved
                        self._set_active_index_locked(idx)
                        data["channel"] = idx + 1
                        data["index"] = idx
                        data["stream"] = chosen_stream
                elif 0 <= self._active_index < q_len:
                    chosen_stream = self._queue[self._active_index]
                    data["channel"] = self._active_index + 1
                    data["index"] = self._active_index
                    data["stream"] = chosen_stream

        # Handle play_query discovery outside lock if queue didn't contain a match
        if cmd in ("play_query", "play") and data.get("query") and not chosen_stream:
            cat = str(data.get("category") or self._category or "all").lower()
            found = self._populate_queue_from_search(str(data["query"]), category=cat)
            if not found and cat != "all":
                found = self._populate_queue_from_search(str(data["query"]), category="all")
            if found:
                resolved = self.resolve_channel(query=str(data["query"]))
                idx, chosen_stream = resolved if resolved else (0, found[0])
                with self._lock:
                    self._set_active_index_locked(idx)
                cmd = "play_channel"
                data["channel"] = idx + 1
                data["index"] = idx
                data["stream"] = chosen_stream
                data["discovered_new_lineup"] = True
            else:
                return {"ok": False, "error": f"No live stream found for '{data['query']}'.", "state": self.get_state()}

        if cmd == "search":
            q_str = str(data.get("query") or "")
            cat = str(data.get("category") or self._category or "all").lower()
            if allow_headless_fallback and not self.has_active_browser_client():
                self._populate_queue_from_search(q_str, category=cat)

        # Headless VLC Desktop / LibVLC execution when target requires backend or no browser is active
        browser_open = self.has_active_browser_client()
        if allow_headless_fallback:
            if cmd == "open_vlc" and chosen_stream:
                backend_exec = self._execute_headless_target("play", chosen_stream, force_vlc=True)
            elif cmd in ("play_channel", "ch_up", "ch_down", "last") and chosen_stream:
                if self._target in ("vlc", "libvlc") or ((not browser_open or source == "llm") and source != "ui"):
                    backend_exec = self._execute_headless_target(
                        "play",
                        chosen_stream,
                        force_vlc=((not browser_open or source == "llm") and self._target == "app"),
                    )
            elif cmd in ("stop", "pause", "vol_up", "vol_down", "set_volume", "mute", "fullscreen"):
                act = {"vol_up": "volume", "vol_down": "volume", "set_volume": "volume"}.get(cmd, cmd)
                force_vlc_ctrl = (not browser_open) and self._target == "app" and cmd in ("fullscreen", "stop", "pause", "vol_up", "vol_down", "set_volume", "mute")
                if cmd == "fullscreen":
                    req_fs = data["fullscreen"] if "fullscreen" in data else None
                    backend_exec = self._execute_headless_target(
                        "fullscreen", force_vlc=force_vlc_ctrl, fullscreen=req_fs
                    )
                    if backend_exec.get("ok") and "fullscreen" in backend_exec:
                        with self._lock:
                            self._fullscreen = bool(backend_exec["fullscreen"])
                            data["fullscreen"] = self._fullscreen
                else:
                    backend_exec = self._execute_headless_target(act, force_vlc=force_vlc_ctrl)

        with self._lock:
            cmd_obj = self._enqueue_command_locked(cmd, data, source=source)
            state = self.get_state()

        hecos_logger.info(
            f"[StreamRemoteBus] cmd={cmd} source={source} seq={cmd_obj['seq']} "
            f"ch={state.get('active_channel')} target={state.get('target')} "
            f"browser_open={browser_open} backend_ok={backend_exec.get('ok')} "
            f"vlc_method={backend_exec.get('launch_method')}"
        )
        return {
            "ok": True,
            "command": cmd_obj,
            "backend_exec": backend_exec,
            "state": state,
        }


_REMOTE_BUS = StreamRemoteBus()


def get_remote_bus() -> StreamRemoteBus:
    return _REMOTE_BUS


__all__ = [
    "StreamRemoteBus",
    "get_remote_bus",
    "VALID_TARGETS",
    "VALID_CATEGORIES",
    "normalize_target",
    "parse_channel_or_query",
]
