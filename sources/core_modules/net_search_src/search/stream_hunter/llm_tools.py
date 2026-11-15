"""
search/stream_hunter/llm_tools.py
Global Hecos LLM Tools and Slash Command Handlers for Live Streams (TV, Radio, Webcams)
and the TV Remote Control Bus. Works identically whether triggered by voice/chat in main
Hecos Assistant or headlessly (falling back to VLC Desktop / LibVLC when /search UI is closed).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from hecos.modules.net_search.search.config import get_stream_preset_settings
from .remote_bus import (
    VALID_CATEGORIES,
    VALID_TARGETS,
    get_remote_bus,
    normalize_target,
    parse_channel_or_query,
)

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("net_search.stream_llm_tools")


def _format_channel_line(idx: int, st: Dict[str, Any]) -> str:
    ch = f"CH {idx:02d}"
    title = st.get("title") or "Untitled Stream"
    cat = (st.get("category") or "tv").upper()
    proto = (st.get("protocol") or "HLS").upper()
    country = f" · {st['country']}" if st.get("country") else ""
    url = st.get("stream_url") or st.get("url") or ""
    return f"- **{ch}** — [{title}]({url}) `[{cat} | {proto}{country}]`"


def _format_bus_status(state: Dict[str, Any]) -> str:
    active = state.get("active_stream")
    ch = state.get("active_channel")
    vol = state.get("volume", 85)
    muted = " (MUTED)" if state.get("muted") else ""
    paused = " [PAUSED]" if state.get("paused") else ""
    tgt = str(state.get("target") or "app").upper()
    q_cnt = state.get("queue_count", 0)
    preset_cfg = state.get("preset_settings") or get_stream_preset_settings()
    preset_flag = "ON" if preset_cfg.get("use_global_preset", True) else "OFF"
    if active:
        ch_str = f"CH {int(ch):02d} — **{active.get('title')}**" if ch else f"**{active.get('title')}**"
    else:
        ch_str = "STANDBY (no channel tuned)"
    return (
        f"📺 **TV / Stream Remote Status**\n"
        f"- **Channel**: {ch_str}{paused}\n"
        f"- **Target**: `{tgt}` | **Volume**: `{vol}%`{muted} | **Lineup**: `{q_cnt}` channels\n"
        f"- **Global Preset Sync**: `{preset_flag}`"
    )


def _trace_progress(msg: str, level: str = "tool") -> None:
    try:
        from hecos.core.agent.traces import AgentTracer
        AgentTracer.progress(msg, level=level)
    except Exception:
        pass


def _trace_action(command: str, output: str = "") -> None:
    try:
        from hecos.core.agent.traces import AgentTracer
        AgentTracer.emit_action("NETSEARCH", command, output)
    except Exception:
        pass


class StreamLLMTools:
    """Modular Live Stream search & TV Remote execution methods exposed via NetSearchTools."""

    def stream_search(
        self,
        query: str = "",
        category: str = "all",
        max_results: Optional[int] = None,
        full_list: bool = False,
    ) -> str:
        """Search live TV channels, radio stations, webcams, or raw streams into a numbered lineup."""
        bus = get_remote_bus()
        cat = (category or "all").strip().lower()
        if cat not in VALID_CATEGORIES:
            cat = "all"

        raw_q = (query or "").strip()
        is_all_keyword = raw_q.lower() in {"", "all", "tutti", "tutte", "lista", "list", "*"}
        effective_query = "" if is_all_keyword else raw_q
        show_full = bool(full_list or is_all_keyword)

        if max_results is None or int(max_results) <= 0:
            effective_limit = 500 if show_full else 12
        else:
            effective_limit = max(1, min(1000, int(max_results)))
            if show_full and effective_limit < 200:
                effective_limit = 500

        hecos_logger.info(
            f"[StreamLLMTools] stream_search(query={effective_query!r}, category={cat!r}, "
            f"limit={effective_limit}, full_list={show_full})"
        )
        _trace_progress(
            f"Loading full {cat.upper()} live channels list..."
            if show_full and not effective_query
            else f"Searching {cat.upper()} live streams for '{effective_query or cat}'..."
        )
        try:
            from hecos.modules.net_search.search.stream_hunter import search_streams

            res = search_streams(query=effective_query, category=cat, max_results=effective_limit)
            streams: List[Dict[str, Any]] = res.get("streams") or []
        except Exception as e:
            hecos_logger.warning(f"[StreamLLMTools] stream_search failed: {e}")
            return f"⚠️ Live Stream discovery error: {e}"

        hecos_logger.info(f"[StreamLLMTools] stream_search found {len(streams)} streams for query={effective_query!r}")
        _trace_progress(f"Loaded {len(streams)} live channels into CH 01..{max(1, len(streams)):02d}")

        # Sync into command bus so both browser UI and remote share numbered CH 01..NN
        bus.sync_state({"queue": streams, "category": cat, "query": effective_query})
        if bus.has_active_browser_client():
            bus.dispatch_command(
                "search",
                {"query": effective_query, "category": cat},
                source="llm",
                allow_headless_fallback=False,
            )

        if not streams:
            return f"📡 No live streams matched `{raw_q or cat}`."

        lines = [f"### 📡 Live Stream Lineup (`{cat.upper()}` — `{len(streams)}` channels)\n"]
        if cat == "all" and len(streams) > 1:
            cat_headers = [
                ("tv", "📺 Live TV"),
                ("radio", "📻 Live Radio"),
                ("webcam", "📷 Webcams"),
                ("raw", "📡 Raw Streams"),
            ]
            numbered = [(idx, st) for idx, st in enumerate(streams, 1)]
            shown_indices = set()
            for cat_key, header_label in cat_headers:
                group = [
                    (idx, st)
                    for idx, st in numbered
                    if (st.get("category") or "raw").lower() == cat_key
                ]
                if not group:
                    continue
                lines.append(f"\n#### {header_label} (`{len(group)}`)")
                for idx, st in group:
                    lines.append(_format_channel_line(idx, st))
                    shown_indices.add(idx)
            leftovers = [(idx, st) for idx, st in numbered if idx not in shown_indices]
            if leftovers:
                lines.append(f"\n#### 📡 Other Streams (`{len(leftovers)}`)")
                for idx, st in leftovers:
                    lines.append(_format_channel_line(idx, st))
        else:
            for i, st in enumerate(streams, 1):
                lines.append(_format_channel_line(i, st))
        lines.append("\n*Say or run `/canale <number|name>` or `NETSEARCH__stream_control(action='play', channel=1)` to tune in.*")
        return "\n".join(lines)

    def stream_control(
        self,
        action: str,
        channel: Optional[Any] = None,
        query: str = "",
        volume: Optional[int] = None,
        target: str = "",
        category: str = "",
    ) -> str:
        """
        Control Live TV/Radio playback and the TV Remote:
        action in {play, list, channel, ch_up, ch_down, last, stop, pause, vol_up, vol_down, set_volume, mute, fullscreen, target, toggle_proxy, open_vlc, status}.
        """
        act = (action or "status").strip().lower()
        bus = get_remote_bus()
        hecos_logger.info(
            f"[StreamLLMTools] stream_control invoked: action={act!r}, channel={channel!r}, "
            f"query={query!r}, volume={volume!r}, target={target!r}, category={category!r}"
        )

        if act == "status":
            return _format_bus_status(bus.get_state())

        if act in ("list", "lista", "canali", "channels", "lineup"):
            cat_arg = (category or "").strip().lower()
            if cat_arg not in VALID_CATEGORIES:
                cat_arg = "all"
            return self.stream_search(query=(query or "").strip(), category=cat_arg, max_results=500, full_list=True)

        ch_int, eff_query = parse_channel_or_query(channel, query)
        norm_target = normalize_target(target)

        cmd_map = {
            "play": "play_channel" if ch_int is not None else "play_query",
            "tune": "play_channel" if ch_int is not None else "play_query",
            "channel": "play_channel" if ch_int is not None else "play_query",
            "next": "ch_up",
            "ch_up": "ch_up",
            "prev": "ch_down",
            "ch_down": "ch_down",
            "back": "last",
            "last": "last",
            "stop": "stop",
            "pause": "pause",
            "play_pause": "pause",
            "vol_up": "vol_up",
            "vol_down": "vol_down",
            "volume": "set_volume",
            "set_volume": "set_volume",
            "mute": "mute",
            "target": "target",
            "proxy": "toggle_proxy",
            "toggle_proxy": "toggle_proxy",
            "vlc": "open_vlc",
            "open_vlc": "open_vlc",
            "fullscreen": "fullscreen",
            "schermo_intero": "fullscreen",
            "schermo intero": "fullscreen",
            "category": "category",
        }
        mapped = cmd_map.get(act, act)
        payload: Dict[str, Any] = {}
        if ch_int is not None:
            payload["channel"] = ch_int
        if eff_query:
            payload["query"] = eff_query
        if volume is not None:
            try:
                payload["volume"] = max(0, min(100, int(volume)))
            except (TypeError, ValueError):
                pass
        if norm_target:
            payload["target"] = norm_target
        if category and category.strip().lower() in VALID_CATEGORIES:
            payload["category"] = category.strip().lower()

        # If action is play without channel or query, fall back to playing CH 01 or active channel
        if mapped in ("play_query", "play_channel") and not payload.get("channel") and not payload.get("query"):
            st = bus.get_state()
            if st.get("active_channel"):
                payload["channel"] = st["active_channel"]
                mapped = "play_channel"
            elif st.get("queue_count", 0) > 0:
                payload["channel"] = 1
                mapped = "play_channel"

        hecos_logger.info(
            f"[StreamLLMTools] Dispatching remote cmd={mapped!r} payload={payload}"
        )
        _trace_progress(
            f"Executing stream remote command: {mapped} ({eff_query or (f'CH {ch_int}' if ch_int is not None else 'remote')})"
        )
        res = bus.dispatch_command(mapped, payload, source="llm", allow_headless_fallback=True)
        if not res.get("ok"):
            hecos_logger.warning(
                f"[StreamLLMTools] Remote command {mapped!r} failed: {res.get('error', 'unknown error')}"
            )
            _trace_progress(f"Remote error: {res.get('error', 'unknown error')}", level="error")
            return f"⚠️ Remote command `{mapped}` failed: {res.get('error', 'unknown error')}"

        state = res.get("state") or bus.get_state()
        cmd_data = (res.get("command") or {}).get("payload") or {}
        backend_exec = res.get("backend_exec") or {}
        active = state.get("active_stream") or cmd_data.get("stream")
        ch = state.get("active_channel")

        extra_note = ""
        if backend_exec.get("vlc_exe"):
            extra_note = " *(Launched in VLC Desktop)*"
            _trace_progress(f"Launched VLC Desktop: CH {int(ch or 1):02d} — {(active or {}).get('title', '')}")
            _trace_action(
                f"vlc_desktop({(active or {}).get('title', 'stream')})",
                f"Stream: {(active or {}).get('stream_url', '')} ({backend_exec.get('launch_method', 'vlc')})",
            )
        elif backend_exec.get("is_playing") and state.get("target") == "libvlc":
            extra_note = " *(Playing via LibVLC audio engine)*"
            _trace_progress(f"Playing via LibVLC: {(active or {}).get('title', '')}")
        elif backend_exec.get("ok") is False and backend_exec.get("error"):
            hecos_logger.warning(f"[StreamLLMTools] Headless playback error: {backend_exec.get('error')}")
            extra_note = f" *(Playback warning: {backend_exec.get('error')})*"
            _trace_progress(f"Playback warning: {backend_exec.get('error')}", level="error")
        elif state.get("browser_active"):
            extra_note = " *(Synced to /search Live Streams & Remote)*"
            _trace_progress(f"Synced CH {int(ch or 1):02d} — {(active or {}).get('title', '')} to WebUI player")

        hecos_logger.info(
            f"[StreamLLMTools] stream_control done: cmd={mapped!r}, ch={ch}, "
            f"title={active.get('title') if isinstance(active, dict) else None!r}, extra={extra_note!r}"
        )

        if mapped in ("play_channel", "play_query", "ch_up", "ch_down", "last", "open_vlc") and active:
            return f"📺 Tuned to **CH {int(ch or 1):02d} — {active.get('title')}** (`{active.get('protocol', 'HLS')}`){extra_note}"
        if mapped == "stop":
            return f"⏹️ Live Stream stopped.{extra_note}"
        if mapped == "pause":
            return f"⏯️ Playback {'paused' if state.get('paused') else 'resumed'}.{extra_note}"
        if mapped in ("vol_up", "vol_down", "set_volume"):
            return f"🔊 Volume set to **{state.get('volume')}%**.{extra_note}"
        if mapped == "mute":
            return f"{'🔇 Muted' if state.get('muted') else '🔊 Unmuted'} (Vol `{state.get('volume')}%`).{extra_note}"
        if mapped == "fullscreen":
            fs_state = backend_exec.get("fullscreen") if "fullscreen" in backend_exec else state.get("fullscreen")
            return f"🖥️ Fullscreen **{'ON' if fs_state else 'OFF'}**."
        if mapped == "target":
            return f"🖥️ Playback target switched to **`{str(state.get('target')).upper()}`**."
        if mapped == "toggle_proxy":
            return f"🛡️ Anti-CORS Stream Proxy is now **{'ON' if state.get('proxy_enabled') else 'OFF'}**."
        return _format_bus_status(state)

    # ── Slash Commands ───────────────────────────────────────────────────
    def slash_streams(self, args: str = "") -> str:
        return self.stream_search(query=(args or "").strip(), category="all", full_list=True)

    def slash_canali(self, args: str = "") -> str:
        raw = (args or "").strip()
        low = raw.lower()
        if low in ("tv", "iptv"):
            return self.stream_search(query="", category="tv", max_results=500, full_list=True)
        if low in ("radio", "fm"):
            return self.stream_search(query="", category="radio", max_results=500, full_list=True)
        if low in ("webcam", "webcams", "cam", "cams"):
            return self.stream_search(query="", category="webcam", max_results=500, full_list=True)
        if low == "raw":
            return self.stream_search(query="", category="raw", max_results=500, full_list=True)
        return self.stream_search(query=raw, category="all", max_results=500, full_list=True)

    def slash_tv(self, args: str = "") -> str:
        return self.stream_search(query=(args or "").strip(), category="tv", full_list=True)

    def slash_radio(self, args: str = "") -> str:
        return self.stream_search(query=(args or "").strip(), category="radio", full_list=True)

    def slash_webcam(self, args: str = "") -> str:
        return self.stream_search(query=(args or "").strip(), category="webcam", full_list=True)

    def slash_canale(self, args: str = "") -> str:
        raw = (args or "").strip()
        if not raw:
            return self.stream_control(action="status")

        low = raw.lower()
        if low in ("+", "up", "next", "avanti", "su"):
            return self.stream_control(action="ch_up")
        if low in ("-", "down", "prev", "indietro", "giu", "giù"):
            return self.stream_control(action="ch_down")
        if low in ("last", "precedente", "back"):
            return self.stream_control(action="last")
        if low in ("stop", "spegni", "off"):
            return self.stream_control(action="stop")
        if low in ("pause", "pausa"):
            return self.stream_control(action="pause")
        if low in ("mute", "muto", "unmute"):
            return self.stream_control(action="mute")
        if low in ("vlc", "desktop"):
            return self.stream_control(action="open_vlc")
        if low in ("fullscreen", "schermo intero", "schermo_intero", "fs"):
            return self.stream_control(action="fullscreen")
        if low in ("list", "lista", "tutti", "all", "canali", "channels"):
            return self.stream_search(query="", category="all", max_results=500, full_list=True)
        if low.startswith("vol"):
            m = re.search(r"(\d{1,3})", low)
            if m:
                return self.stream_control(action="set_volume", volume=int(m.group(1)))
            if "+" in low or "up" in low:
                return self.stream_control(action="vol_up")
            if "-" in low or "down" in low:
                return self.stream_control(action="vol_down")

        m_ch = re.match(r"^(?:ch|canale)?\s*#?(\d{1,3})$", low)
        if m_ch:
            return self.stream_control(action="play", channel=int(m_ch.group(1)))

        return self.stream_control(action="play", query=raw)


__all__ = ["StreamLLMTools"]
