"""
web/search_bookmarks_routes.py
Dedicated Flask API routes for Deep Search saved links & bookmarks management.
"""
from __future__ import annotations

import logging
from flask import request, jsonify
from flask_login import login_required

try:
    from hecos.modules.net_search.search.bookmarks import get_bookmark_store
except (ImportError, ValueError):
    from ..search.bookmarks import get_bookmark_store

try:
    from hecos.core.logging import logger as hecos_logger
except (ImportError, ValueError):
    hecos_logger = logging.getLogger("net_search.web.bookmarks")


def register_bookmarks_routes(app, logger=None):
    """Registers bookmarks REST API endpoints on the Flask application."""
    log = logger or hecos_logger
    log.info("[DeepSearch] Registering bookmarks routes...")
    store = get_bookmark_store()

    @app.route("/api/hsearch/bookmarks", methods=["GET"])
    @login_required
    def api_bookmarks_list():
        network = request.args.get("network") or None
        category = request.args.get("category") or None
        q = request.args.get("q") or None
        limit = int(request.args.get("limit", 200))
        items = store.list_bookmarks(network=network, category=category, search_term=q, limit=limit)
        return jsonify({
            "ok": True,
            "bookmarks": items,
            "total": store.get_count()
        })

    @app.route("/api/hsearch/bookmarks/urls", methods=["GET"])
    @login_required
    def api_bookmarks_urls():
        urls = store.get_all_bookmarked_urls()
        return jsonify({
            "ok": True,
            "urls": list(urls),
            "total": len(urls)
        })

    @app.route("/api/hsearch/bookmarks/toggle", methods=["POST"])
    @login_required
    def api_bookmarks_toggle():
        data = request.get_json(force=True) or {}
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify({"ok": False, "error": "Missing URL"}), 400

        title = data.get("title") or url
        snippet = data.get("snippet") or ""
        engine = data.get("engine") or "web"
        network = data.get("network") or ("tor" if ".onion" in url else "clear")
        category = data.get("category") or "web"

        res = store.toggle_bookmark(
            url=url,
            title=title,
            snippet=snippet,
            engine=engine,
            network=network,
            category=category
        )
        return jsonify({
            "ok": True,
            "bookmarked": res.get("bookmarked", False),
            "bookmark": res,
            "total": store.get_count()
        })

    @app.route("/api/hsearch/bookmarks", methods=["DELETE"])
    @login_required
    def api_bookmarks_delete():
        data = request.get_json(force=True) or {}
        url = (data.get("url") or "").strip()
        bookmark_id = (data.get("id") or "").strip()

        if url:
            ok = store.remove_bookmark(url)
        elif bookmark_id:
            ok = store.remove_bookmark_by_id(bookmark_id)
        else:
            return jsonify({"ok": False, "error": "Missing url or id"}), 400

        return jsonify({
            "ok": ok,
            "total": store.get_count()
        })
