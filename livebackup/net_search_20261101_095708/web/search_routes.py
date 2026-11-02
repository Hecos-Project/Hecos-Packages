"""
web/search_routes.py
Flask API and UI routes for Hecos Deep Search & Intelligence.
Provides dedicated /search page, sandbox /search/viewer, SSE streaming query API, and orchestrates domain sub-routes.
"""
from __future__ import annotations

import os
import time
import json
import queue
import threading
import logging
import urllib.parse
from flask import request, jsonify, render_template, Response, stream_with_context
from flask_login import login_required

try:
    from hecos.modules.net_search.search.service import get_search_service
    from hecos.modules.net_search.search.models import SearchQuery
    from hecos.modules.net_search.search.http_client import is_tor_online
    from hecos.modules.net_search.search.extract.fetcher import fetch_and_clean_page
    from hecos.modules.net_search.web.search_bookmarks_routes import register_bookmarks_routes
    from hecos.modules.net_search.web.search_session_routes import register_session_routes
    from hecos.modules.net_search.web.search_component_routes import register_component_routes
    from hecos.modules.net_search.web.search_endpoint_routes import register_endpoint_routes
    from hecos.modules.net_search.web.search_copilot_routes import register_copilot_routes
except (ImportError, ValueError):
    from ..search.service import get_search_service
    from ..search.models import SearchQuery
    from ..search.http_client import is_tor_online
    from ..search.extract.fetcher import fetch_and_clean_page
    from .search_bookmarks_routes import register_bookmarks_routes
    from .search_session_routes import register_session_routes
    from .search_component_routes import register_component_routes
    from .search_endpoint_routes import register_endpoint_routes
    from .search_copilot_routes import register_copilot_routes

try:
    from hecos.core.logging import logger as hecos_logger
except (ImportError, ValueError):
    hecos_logger = logging.getLogger("net_search.web")

logger = hecos_logger


def register_search_routes(app, cfg_mgr, root_dir, logger=None):
    """
    Registers all Deep Search routes on the Flask app:
    - Dedicated web views (/search, /search/viewer)
    - Core search execution APIs (/api/hsearch/query, /api/hsearch/query_stream, /api/hsearch/fetch)
    - Sub-domain routes (bookmarks, sessions, components, endpoints & Tor)
    """
    if "search_page" in app.view_functions:
        return
    log = logger or logging.getLogger("browser.web.search")
    log.info("[DeepSearch] Registering search routes and /search page...")

    service = get_search_service()

    # ── Register Sub-domain Route Modules ─────────────────────────────────────
    try:
        register_bookmarks_routes(app, logger=log)
    except Exception as e:
        log.warning(f"[DeepSearch] Could not register bookmarks routes: {e}")

    try:
        register_session_routes(app, logger=log)
    except Exception as e:
        log.warning(f"[DeepSearch] Could not register session routes: {e}")

    try:
        register_component_routes(app, logger=log)
    except Exception as e:
        log.warning(f"[DeepSearch] Could not register component routes: {e}")

    try:
        register_endpoint_routes(app, logger=log)
    except Exception as e:
        log.warning(f"[DeepSearch] Could not register endpoint routes: {e}")

    try:
        register_copilot_routes(app, logger=log)
    except Exception as e:
        log.warning(f"[DeepSearch] Could not register copilot routes: {e}")

    # ── Main Search Page ──────────────────────────────────────────────────────
    @app.route("/search", methods=["GET"])
    @login_required
    def search_page():
        """Renders the dedicated Hecos Deep Search & Media Discovery interface."""
        initial_q = request.args.get("q", "")
        initial_mode = request.args.get("mode", "clear")
        initial_session = request.args.get("session", "")
        return render_template(
            "search.html",
            initial_q=initial_q,
            initial_mode=initial_mode,
            initial_session=initial_session,
            tor_online=is_tor_online(),
            version=int(time.time())
        )

    # ── Tor Live Web Viewer Page ──────────────────────────────────────────────
    @app.route("/search/viewer", methods=["GET"])
    @login_required
    def search_viewer_page():
        """Renders the in-app Cross-Browser Tor Live Viewer."""
        target_url = request.args.get("url", "").strip()
        if not target_url:
            return "Missing url parameter", 400
        if not target_url.startswith("http://") and not target_url.startswith("https://"):
            target_url = "http://" + target_url

        target_encoded = urllib.parse.quote(target_url)
        return render_template(
            "search_viewer.html",
            target_url=target_url,
            target_url_encoded=target_encoded,
            tor_online=is_tor_online(),
            version=int(time.time())
        )

    # ── Search API (Standard JSON) ────────────────────────────────────────────
    @app.route("/api/hsearch/query", methods=["POST"])
    @login_required
    def api_search_query():
        try:
            data = request.get_json(force=True) or {}
            query_str = data.get("query", "").strip()
            if not query_str:
                return jsonify({"ok": False, "error": "Query cannot be empty"}), 400

            local_only_val = data.get("local_only")
            if local_only_val is not None:
                local_only_val = bool(local_only_val)

            sq = SearchQuery(
                query=query_str,
                mode=data.get("mode", "clear"),
                engines=data.get("engines", []),
                limit=int(data.get("limit", 50)),
                safe_search=bool(data.get("safe_search", False)),
                dark_bypass=bool(data.get("dark_bypass", True)),
                time_range=data.get("time_range"),
                file_types=data.get("file_types", []),
                auto_fallback_tor=bool(data.get("auto_fallback_tor", True)),
                target_username=data.get("target_username"),
                local_only=local_only_val
            )

            session = service.search(sq)
            return jsonify({
                "ok": True,
                "session": session.to_dict()
            })
        except Exception as e:
            log.error(f"Search API error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    # ── Streaming Search API (Server-Sent Events) ─────────────────────────────
    @app.route("/api/hsearch/query_stream", methods=["GET"])
    @login_required
    def api_search_stream():
        query_str = request.args.get("q", "").strip()
        if not query_str:
            return jsonify({"ok": False, "error": "Query cannot be empty"}), 400

        mode = request.args.get("mode", "clear")
        limit = int(request.args.get("limit", 50))
        safe_search = request.args.get("safe_search", "false").lower() == "true"
        dark_bypass = request.args.get("dark_bypass", "true").lower() == "true"
        file_types_raw = request.args.get("file_types", "")
        file_types = [f.strip() for f in file_types_raw.split(",") if f.strip()]
        engines_raw = request.args.get("engines", "")
        engines = [e.strip() for e in engines_raw.split(",") if e.strip()]
        local_only_arg = request.args.get("local_only")
        local_only = (local_only_arg.lower() in ("true", "1")) if local_only_arg is not None else None

        hecos_logger.info(f"[SEARCH:STREAM] Client connected: query='{query_str}' [mode={mode}, limit={limit}, safe_search={safe_search}, dark_bypass={dark_bypass}, local_only={local_only}]")

        sq = SearchQuery(
            query=query_str,
            mode=mode,
            engines=engines,
            limit=limit,
            safe_search=safe_search,
            dark_bypass=dark_bypass,
            file_types=file_types,
            local_only=local_only
        )

        event_queue = queue.Queue()

        def _stream_callback(event_dict):
            event_queue.put(event_dict)

        def _worker():
            try:
                service.search(sq, stream_cb=_stream_callback)
            except Exception as e:
                hecos_logger.error(f"[SEARCH:STREAM] Execution failed: {e}")
                event_queue.put({"type": "error", "error": str(e)})
            finally:
                event_queue.put(None)  # Sentinel

        threading.Thread(target=_worker, daemon=True).start()

        def _generate():
            while True:
                evt = event_queue.get()
                if evt is None:
                    break
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

        return Response(stream_with_context(_generate()), mimetype="text/event-stream")

    # ── Fetch & Clean Page API ────────────────────────────────────────────────
    @app.route("/api/hsearch/fetch", methods=["POST"])
    @login_required
    def api_search_fetch():
        data = request.get_json(force=True) or {}
        url = data.get("url", "").strip()
        max_chars = int(data.get("max_chars", 5000))
        if not url:
            return jsonify({"ok": False, "error": "Missing URL"}), 400

        res = fetch_and_clean_page(url=url, max_chars=max_chars)
        return jsonify(res)
