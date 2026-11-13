"""
web/search_session_routes.py
Dedicated Flask API routes for Deep Search session history, favorite tagging, and cleanup.
"""
from __future__ import annotations

import logging
from flask import request, jsonify
from flask_login import login_required

try:
    from hecos.modules.net_search.search.sessions import get_session_store
except (ImportError, ValueError):
    from ..search.sessions import get_session_store

try:
    from hecos.core.logging import logger as hecos_logger
except (ImportError, ValueError):
    hecos_logger = logging.getLogger("net_search.web.sessions")


def register_session_routes(app, logger=None):
    """Registers search session history endpoints on the Flask application."""
    if "api_search_sessions" in app.view_functions:
        return
    log = logger or hecos_logger
    log.info("[DeepSearch] Registering session routes...")
    session_store = get_session_store()

    @app.route("/api/hsearch/sessions", methods=["GET"])
    @login_required
    def api_search_sessions():
        limit = int(request.args.get("limit", 40))
        fav_only = request.args.get("favorites", "false").lower() == "true"
        sessions = session_store.list_sessions(limit=limit, favorite_only=fav_only)
        return jsonify({"ok": True, "sessions": sessions})

    @app.route("/api/hsearch/sessions/<session_id>", methods=["GET"])
    @login_required
    def api_search_session_detail(session_id):
        session = session_store.get_session(session_id)
        if not session:
            return jsonify({"ok": False, "error": "Session not found"}), 404
        return jsonify({"ok": True, "session": session.to_dict()})

    @app.route("/api/hsearch/sessions/<session_id>", methods=["DELETE"])
    @login_required
    def api_search_session_delete(session_id):
        ok = session_store.delete_session(session_id)
        if not ok:
            return jsonify({"ok": False, "error": "Session not found"}), 404
        return jsonify({"ok": True, "id": session_id})

    @app.route("/api/hsearch/sessions/<session_id>/rename", methods=["POST", "PATCH"])
    @app.route("/api/hsearch/sessions/<session_id>", methods=["PATCH"])
    @login_required
    def api_search_session_rename(session_id):
        data = request.get_json(silent=True) or {}
        raw_title = data.get("title")
        if raw_title is None:
            raw_title = data.get("name")
        if raw_title is None:
            raw_title = data.get("query")
        if raw_title is None:
            return jsonify({"ok": False, "error": "Missing title"}), 400

        clean_title = str(raw_title).strip()[:200]
        if not clean_title:
            return jsonify({"ok": False, "error": "Title cannot be empty"}), 400

        ok = session_store.rename_session(session_id, clean_title)
        if not ok:
            return jsonify({"ok": False, "error": "Session not found"}), 404
        return jsonify({"ok": True, "id": session_id, "title": clean_title})

    @app.route("/api/hsearch/sessions/clear", methods=["POST"])
    @login_required
    def api_search_sessions_clear():
        ok = session_store.clear_all()
        return jsonify({"ok": ok})

    @app.route("/api/hsearch/sessions/<session_id>/favorite", methods=["POST"])
    @login_required
    def api_search_session_favorite(session_id):
        ok = session_store.toggle_favorite(session_id)
        return jsonify({"ok": ok})
