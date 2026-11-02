"""
web/search_copilot_routes.py
Dedicated Flask API routes for Deep Search AI Copilot:
- Global Preset (SoulProfile) discovery & selection
- Real-time SSE streaming copilot chat with search-aware context
- Live Presenter telemetry stream for sidebar commentary
"""
from __future__ import annotations

import os
import json
import time
import queue
import logging
import threading
from typing import Dict, Any, Optional
from flask import request, jsonify, Response, stream_with_context
from flask_login import login_required

try:
    from hecos.modules.net_search.search.sessions import get_session_store
except (ImportError, ValueError):
    from ..search.sessions import get_session_store

try:
    from hecos.core.logging import logger as hecos_logger
except (ImportError, ValueError):
    hecos_logger = logging.getLogger("net_search.web.copilot")

logger = hecos_logger


def register_copilot_routes(app, logger=None):
    """Registers copilot chat and presenter telemetry routes on the Flask app."""
    if "api_copilot_presets" in app.view_functions:
        return

    log = logger or hecos_logger
    log.info("[DeepSearch] Registering AI Copilot routes...")
    session_store = get_session_store()

    # Ensure PresenterEngine is running and subscribed to search events
    try:
        from hecos.modules.web_ui.extensions.presenter.engine import get_engine
        get_engine().start()
        log.info("[DeepSearch] PresenterEngine started and subscribed.")
    except Exception as _pe_err:
        log.warning(f"[DeepSearch] Could not start PresenterEngine: {_pe_err}")

    # ── 1. Presets Discovery ───────────────────────────────────────────────────
    def _format_soul_name(soul_file: str) -> str:
        if not soul_file:
            return "Hecos AI"
        s = str(soul_file).replace(".yaml", "").strip()
        parts = s.split("_")
        cap_parts = [p.capitalize() if p.islower() else p for p in parts]
        return " ".join(cap_parts).strip()

    @app.route("/api/hsearch/copilot/presets", methods=["GET"])
    @login_required
    def api_copilot_presets():
        """Lists available Global Presets (SoulProfiles) with resolved avatar URLs and internal soul names."""
        try:
            from hecos.core.global_presets.manager import list_souls
            from hecos.core.persona.persona_media import PersonaMediaManager
            souls = list_souls()
            presets = []
            for s in souls:
                if s and s.meta and s.meta.id:
                    pname = getattr(s.persona, "soul_file", None) or s.meta.id
                    av_info = PersonaMediaManager.resolve_avatar(pname)
                    soul_raw = getattr(s.persona, "soul_file", None) or ""
                    soul_clean = _format_soul_name(soul_raw) if soul_raw else (s.meta.name or s.meta.id)
                    presets.append({
                        "id": s.meta.id,
                        "name": s.meta.name or s.meta.id,
                        "soul_file": soul_raw,
                        "soul_name": soul_clean,
                        "icon": getattr(s.meta, "icon", "🧠") or "🧠",
                        "avatar_url": av_info.get("url", "/assets/Hecos_Logo_NBG.png"),
                        "avatar_type": av_info.get("type", "image"),
                        "description": getattr(s.meta, "description", "") or ""
                    })
            if not presets:
                presets = [{"id": "default", "name": "Default Soul", "soul_file": "Hecos_System_Soul", "soul_name": "Hecos AI", "icon": "🧠", "avatar_url": "/assets/Hecos_Logo_NBG.png", "avatar_type": "image", "description": "Standard Assistant"}]
            return jsonify({"ok": True, "presets": presets})
        except Exception as e:
            log.warning(f"[HecosAI] Failed to list soul presets: {e}")
            return jsonify({
                "ok": True,
                "presets": [
                    {"id": "balanced", "name": "Balanced Assistant", "soul_file": "balanced", "soul_name": "Balanced Assistant", "icon": "🧠", "avatar_url": "/assets/Hecos_Logo_NBG.png", "avatar_type": "image", "description": "General AI"},
                    {"id": "creative", "name": "Creative Investigator", "soul_file": "creative", "soul_name": "Creative Investigator", "icon": "🎨", "avatar_url": "/assets/Hecos_Logo_NBG.png", "avatar_type": "image", "description": "Open exploration"},
                    {"id": "precise", "name": "Precise Analyst", "soul_file": "precise", "soul_name": "Precise Analyst", "icon": "🎯", "avatar_url": "/assets/Hecos_Logo_NBG.png", "avatar_type": "image", "description": "Accurate & concise"}
                ]
            })

    # ── 2. Copilot Chat (SSE Streaming & Single Turn) ─────────────────────────
    @app.route("/api/hsearch/copilot/chat", methods=["POST"])
    @login_required
    def api_copilot_chat():
        """
        Executes a conversation turn with the AI Copilot.
        Receives { message, preset_id?, session_id?, stream? }.
        Streams tokens back via Server-Sent Events (SSE) or returns JSON.
        """
        data = request.get_json(silent=True) or {}
        user_message = (data.get("message") or "").strip()
        if not user_message:
            return jsonify({"ok": False, "error": "Empty message"}), 400

        preset_id = data.get("preset_id") or "default"
        session_id = data.get("session_id") or ""
        want_stream = data.get("stream", True) is not False

        # Build search-specific context
        search_context = ""
        resolved_session = None
        if session_id:
            try:
                resolved_session = session_store.get_session(session_id)
            except Exception as se:
                log.warning(f"[HecosAI] Could not load session {session_id} for context: {se}")

        # If no active session with results, check if message has search intent or is a query
        if not (resolved_session and resolved_session.results):
            import re
            m = re.match(r'^(?:cerca(?:\s+su|\s+nel|\s+in)?|cercami|trova(?:\s+su|\s+nel|\s+in)?|search(?:\s+for)?|find(?:\s+for)?|\/search|\/hsearch)\s+(.+)$', user_message, re.IGNORECASE)
            search_query_str = m.group(1).strip() if m else None

            # If not explicit prefix but short message without ending in '?'
            if not search_query_str and len(user_message.split()) <= 10 and not user_message.endswith("?"):
                search_query_str = user_message.strip()

            if search_query_str:
                try:
                    from hecos.modules.net_search.search.service import HecosSearchService
                    from hecos.modules.net_search.search.models import SearchQuery

                    search_mode = "clear"
                    lower_msg = user_message.lower()
                    if any(w in lower_msg for w in ["dark web", ".onion", "tor"]):
                        search_mode = "dark"
                    elif any(w in lower_msg for w in ["deep search", "ricerca profonda"]):
                        search_mode = "deep"
                    elif any(w in lower_msg for w in ["video", "immagine", "immagini", "foto", "audio", "musica"]):
                        search_mode = "media"
                    elif any(w in lower_msg for w in ["file", "pdf", "docx", "dork"]):
                        search_mode = "files"

                    log.info(f"[HecosAI] Executing auto-search for copilot: '{search_query_str}' ({search_mode})")
                    svc = HecosSearchService()
                    sq = SearchQuery(query=search_query_str, mode=search_mode, limit=12)
                    resolved_session = svc.search(sq)
                    if resolved_session:
                        session_id = resolved_session.id
                except Exception as ex:
                    log.warning(f"[HecosAI] Auto-search execution note: {ex}")

        if resolved_session and resolved_session.results:
            items_summary = []
            for i, r in enumerate(resolved_session.results[:12], 1):
                snip = (r.snippet or "")[:140].replace("\n", " ").strip()
                items_summary.append(f"[{i}] {r.title} ({r.engine}, {r.category}): {snip} (URL: {r.url})")
            search_context = (
                f"\n\n[SEARCH RESULTS FOR \"{resolved_session.query}\"]\n"
                f"Total results: {resolved_session.total_results} | Duration: {resolved_session.duration_ms}ms\n"
                f"Top indexed sources:\n" + "\n".join(items_summary)
            )

        # Build System Prompt
        system_prompt = (
            "You are the Hecos AI Assistant integrated into Hecos Net Search. "
            "Your role is to assist the user in analyzing, summarizing, filtering, comparing, and synthesizing search results "
            "across clear web, dark web, and media discovery. "
            "Respond in a sharp, clear, and concise manner, citing sources using reference numbers [1], [2] when appropriate."
        )
        if search_context:
            system_prompt += search_context

        # Merge selected Soul Profile (Global Preset)
        try:
            import copy
            from hecos.core.llm.brain import load_config, generate_response
            from hecos.core.global_presets.manager import get_soul
            from hecos.core.global_presets.merger import merge_soul_into_config

            base_cfg = copy.deepcopy(load_config() or {})
            merged_cfg = base_cfg
            if preset_id and preset_id != "default":
                soul = get_soul(preset_id)
                if soul:
                    merged_cfg = merge_soul_into_config(base_cfg, soul)
                    preset_inst = merged_cfg.get("ai", {}).get("custom_instructions", "").strip()
                    if preset_inst:
                        system_prompt += f"\n\n[PERSONALITY DIRECTIVES ({soul.meta.name})]:\n{preset_inst}"

            if "ai" not in merged_cfg:
                merged_cfg["ai"] = {}
            merged_cfg["ai"]["special_instructions"] = system_prompt
        except Exception as ce:
            log.warning(f"[HecosAI] Configuration merge note: {ce}")
            merged_cfg = None

        # SSE Streaming Path
        if want_stream:
            event_queue = queue.Queue()

            def _llm_worker():
                try:
                    if resolved_session:
                        event_queue.put({
                            "type": "session",
                            "session_id": resolved_session.id,
                            "query": resolved_session.query,
                            "total": resolved_session.total_results
                        })

                    from hecos.core.llm.brain import generate_response
                    res = generate_response(
                        user_text=user_message,
                        external_config=merged_cfg,
                        save_history=False,
                        tag="NETSEARCH_AI"
                    )
                    full_text = res or "No response generated."
                    # Tokenize into natural chunks for a smooth stream
                    words = full_text.split(" ")
                    for i, w in enumerate(words):
                        chunk = w + (" " if i < len(words) - 1 else "")
                        event_queue.put({"type": "token", "text": chunk})
                        time.sleep(0.015)
                    event_queue.put({"type": "done", "text": full_text})
                except Exception as e:
                    log.error(f"[Copilot] Generation error: {e}", exc_info=True)
                    event_queue.put({"type": "error", "error": str(e)})

            threading.Thread(target=_llm_worker, daemon=True, name="HSearchCopilotWorker").start()

            def sse_generator():
                full_reply = ""
                while True:
                    try:
                        ev = event_queue.get(timeout=0.4)
                        yield f"data: {json.dumps(ev)}\n\n"
                        if ev.get("type") in ("done", "error"):
                            break
                    except queue.Empty:
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

            return Response(
                stream_with_context(sse_generator()),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "Access-Control-Allow-Origin": "*"
                }
            )

        # Single JSON Turn Path
        try:
            from hecos.core.llm.brain import generate_response
            reply = generate_response(
                user_text=user_message,
                external_config=merged_cfg,
                save_history=False,
                tag="NETSEARCH_COPILOT"
            )
            return jsonify({"ok": True, "reply": reply or ""})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # ── 3. Live Presenter Stream for Net Search Sidebar ────────────────────────
    @app.route("/api/hsearch/presenter/stream", methods=["GET"])
    @login_required
    def api_hsearch_presenter_stream():
        """SSE stream pushing live Presenter telecronaca entries to the Net Search sidebar."""
        try:
            from hecos.modules.web_ui.extensions.presenter.engine import get_engine
            get_engine().start()
        except Exception:
            pass

        def generate():
            seen_entries = set()
            while True:
                try:
                    from hecos.modules.web_ui.extensions.presenter.feed import get_feed_entries
                    entries = get_feed_entries(limit=10) or []
                    for entry in reversed(entries):
                        ts = entry.get("timestamp") or str(entry.get("text", ""))[:40]
                        if ts not in seen_entries:
                            seen_entries.add(ts)
                            # Keep set bounded
                            if len(seen_entries) > 100:
                                seen_entries.clear()
                            yield f"data: {json.dumps(entry)}\n\n"
                    time.sleep(2.0)
                except Exception as ex:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                    time.sleep(3.0)

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"
            }
        )

