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
    from hecos.modules.net_search.search.copilot_planner import (
        load_copilot_presets_payload,
        resolve_active_soul,
        get_soul_display_name,
        build_preset_instructions,
        plan_copilot_turn,
        build_responder_config,
    )
except (ImportError, ValueError):
    from ..search.sessions import get_session_store
    from ..search.copilot_planner import (
        load_copilot_presets_payload,
        resolve_active_soul,
        get_soul_display_name,
        build_preset_instructions,
        plan_copilot_turn,
        build_responder_config,
    )

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
    @app.route("/api/hsearch/copilot/presets", methods=["GET"])
    @login_required
    def api_copilot_presets():
        """Lists available Global Presets (SoulProfiles) with full model/inference/voice metadata and tooltips."""
        return jsonify(load_copilot_presets_payload(log=log))

    # ── 2. Copilot Chat (SSE Streaming & Single Turn) ─────────────────────────
    @app.route("/api/hsearch/copilot/chat", methods=["POST"])
    @login_required
    def api_copilot_chat():
        """
        Executes a conversation turn with the AI Copilot.
        Receives { message, preset_id?, session_id?, active_mode?, auto_mode?, current_query?, has_results?, limit?, safe_search?, dark_bypass?, local_only?, stream? }.
        Plans intent/query/mode once, runs at most one search, and streams commentary via SSE.
        """
        data = request.get_json(silent=True) or {}
        user_message = (data.get("message") or "").strip()
        if not user_message:
            return jsonify({"ok": False, "error": "Empty message"}), 400

        preset_id = data.get("preset_id") or "default"
        session_id = (data.get("session_id") or "").strip()
        active_mode = (data.get("active_mode") or "clear").strip().lower()
        auto_mode = data.get("auto_mode", True) is not False
        current_query = (data.get("current_query") or "").strip()
        has_results = bool(data.get("has_results", False))
        try:
            req_limit = int(data.get("limit", 100))
        except (TypeError, ValueError):
            req_limit = 100
        req_safe_search = bool(data.get("safe_search", False))
        req_dark_bypass = data.get("dark_bypass", True) is not False
        req_local_only = data.get("local_only", True) is not False
        want_stream = data.get("stream", True) is not False

        # Resolve active soul (preset) — reads system config if payload says "default"
        import copy
        try:
            from hecos.core.llm.brain import load_config
            from hecos.core.global_presets.merger import merge_soul_into_config
            base_cfg = copy.deepcopy(load_config() or {})
        except Exception as cfg_err:
            log.warning(f"[Copilot] Could not load base config: {cfg_err}")
            base_cfg = {}

        soul = resolve_active_soul(preset_id, log=log)
        soul_display_name = get_soul_display_name(soul)
        preset_instructions = build_preset_instructions(soul)

        if soul:
            try:
                merged_cfg = merge_soul_into_config(base_cfg, soul)
                log.info(f"[Copilot] Active soul: '{soul.meta.name}' | instructions: {len(preset_instructions)} chars")
            except Exception as me:
                log.warning(f"[Copilot] Soul merge failed: {me}")
                merged_cfg = base_cfg
        else:
            merged_cfg = base_cfg

        # Disable unrelated tools (including IMAGE_GEN) inside Net Search Copilot
        if isinstance(merged_cfg, dict):
            merged_cfg["disable_tools"] = True

        existing_session = None
        if session_id:
            try:
                existing_session = session_store.get_session(session_id)
                if existing_session and existing_session.results:
                    has_results = True
                    if not current_query:
                        current_query = existing_session.query
            except Exception as se:
                log.warning(f"[HecosAI] Could not load session {session_id} for context: {se}")

        def _execute_turn_plan(status_cb=None, stream_cb=None):
            t_turn = time.time()
            if status_cb:
                status_cb("Analyzing search intent & optimizing query...")
            plan = plan_copilot_turn(
                user_message=user_message,
                current_query=current_query,
                has_results=has_results,
                active_mode=active_mode,
                auto_mode=auto_mode,
                preset_instructions=preset_instructions,
                cfg=merged_cfg,
                log=log,
            )

            resolved_sess = existing_session if plan["action"] == "analyze_current" else None

            if plan["action"] == "new_search" and plan["query"]:
                if status_cb:
                    status_cb(f"Searching {plan['mode'].upper()} for \"{plan['query']}\"...", plan=plan)
                try:
                    from hecos.modules.net_search.search.service import get_search_service
                    from hecos.modules.net_search.search.models import SearchQuery

                    # Focus engines for clear visual/media intents so slow news/podcast scrapers don't stall Copilot
                    targeted_engines = []
                    if plan["mode"] == "clear":
                        if plan["filter"] == "images":
                            targeted_engines = ["media_images", "clear_searxng", "clear_ddgs"]
                        elif plan["filter"] == "videos":
                            targeted_engines = ["media_videos", "clear_searxng", "clear_ddgs"]
                        elif plan["filter"] == "audio":
                            targeted_engines = ["media_audio", "clear_searxng"]

                    copilot_limit = 60 if (req_limit <= 0 or req_limit > 60) else req_limit
                    log.info(
                        f"[Copilot] Dispatching search: query='{plan['query']}', mode={plan['mode']}, "
                        f"filter={plan['filter']}, limit={copilot_limit}, engines={targeted_engines or 'all'}"
                    )

                    svc = get_search_service()
                    sq = SearchQuery(
                        query=plan["query"],
                        mode=plan["mode"],
                        engines=targeted_engines,
                        limit=copilot_limit,
                        safe_search=req_safe_search,
                        dark_bypass=req_dark_bypass,
                        local_only=req_local_only,
                    )
                    resolved_sess = svc.search(sq, stream_cb=stream_cb)
                    log.info(
                        f"[Copilot] Search completed in {round((time.time() - t_turn) * 1000)}ms: "
                        f"session={getattr(resolved_sess, 'id', None)}, results={getattr(resolved_sess, 'total_results', 0)}"
                    )
                except Exception as ex:
                    log.warning(f"[HecosAI] Copilot search execution note: {ex}", exc_info=True)
            return plan, resolved_sess

        # SSE Streaming Path
        if want_stream:
            event_queue = queue.Queue()
            cancel_event = threading.Event()

            def _llm_worker():
                try:
                    t_worker = time.time()
                    def _on_status(msg_text, plan=None):
                        if cancel_event.is_set():
                            return
                        if plan is not None:
                            event_queue.put({
                                "type": "search_plan",
                                "action": plan["action"],
                                "query": plan["query"],
                                "mode": plan["mode"],
                                "filter": plan["filter"],
                                "auto_mode": auto_mode,
                            })
                        event_queue.put({"type": "status", "text": msg_text})

                    def _on_search_stream(evt):
                        if cancel_event.is_set():
                            return
                        if evt.get("type") == "engine_done":
                            eng = evt.get("engine", "engine")
                            total_so_far = evt.get("total_so_far", 0)
                            raw_cnt = evt.get("raw_count", 0)
                            dur_ms = evt.get("duration_ms", 0)
                            log.debug(f"[Copilot:Stream] Engine '{eng}' done in {dur_ms}ms (+{raw_cnt}, total={total_so_far})")
                            event_queue.put({
                                "type": "status",
                                "text": f"Querying engines: {eng} finished ({total_so_far} results collected)..."
                            })

                    plan, resolved_sess = _execute_turn_plan(status_cb=_on_status, stream_cb=_on_search_stream)
                    if cancel_event.is_set():
                        log.info("[Copilot] Request cancelled by client before synthesis.")
                        return

                    if resolved_sess:
                        event_queue.put({
                            "type": "session",
                            "session_id": resolved_sess.id,
                            "query": resolved_sess.query,
                            "mode": resolved_sess.mode,
                            "filter": plan["filter"],
                            "total": resolved_sess.total_results,
                        })

                    if cancel_event.is_set():
                        return

                    event_queue.put({"type": "status", "text": f"Synthesizing results with {soul_display_name}..."})
                    t_llm = time.time()
                    responder_cfg = build_responder_config(resolved_sess, merged_cfg, soul, preset_instructions)
                    from hecos.core.llm.brain import generate_response
                    res = generate_response(
                        user_text=user_message,
                        external_config=responder_cfg,
                        save_history=False,
                        tag="NETSEARCH_AI"
                    )
                    if cancel_event.is_set():
                        log.info("[Copilot] Request cancelled by client before streaming tokens.")
                        return

                    full_text = res or "No response generated."
                    log.info(
                        f"[Copilot] LLM synthesis completed in {round((time.time() - t_llm) * 1000)}ms "
                        f"(total_turn={round((time.time() - t_worker) * 1000)}ms, chars={len(full_text)})"
                    )
                    words = full_text.split(" ")
                    for i, w in enumerate(words):
                        if cancel_event.is_set():
                            return
                        chunk = w + (" " if i < len(words) - 1 else "")
                        event_queue.put({"type": "token", "text": chunk})
                        time.sleep(0.015)
                    if not cancel_event.is_set():
                        event_queue.put({"type": "done", "text": full_text})
                except Exception as e:
                    if not cancel_event.is_set():
                        log.error(f"[Copilot] Generation error: {e}", exc_info=True)
                        event_queue.put({"type": "error", "error": str(e)})

            threading.Thread(target=_llm_worker, daemon=True, name="HSearchCopilotWorker").start()

            def sse_generator():
                try:
                    while not cancel_event.is_set():
                        try:
                            ev = event_queue.get(timeout=0.4)
                            yield f"data: {json.dumps(ev)}\n\n"
                            if ev.get("type") in ("done", "error"):
                                break
                        except queue.Empty:
                            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                finally:
                    cancel_event.set()

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
            plan, resolved_sess = _execute_turn_plan()
            responder_cfg = build_responder_config(resolved_sess, merged_cfg, soul, preset_instructions)
            from hecos.core.llm.brain import generate_response
            reply = generate_response(
                user_text=user_message,
                external_config=responder_cfg,
                save_history=False,
                tag="NETSEARCH_COPILOT"
            )
            return jsonify({
                "ok": True,
                "reply": reply or "",
                "plan": plan,
                "session_id": resolved_sess.id if resolved_sess else None,
            })
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

