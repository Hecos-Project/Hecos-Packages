"""
web/routes.py
Routes registration for Net Search (Deep Search & Intelligence System App).

Designed to be loaded safely in TWO contexts:
  1. Via HPM routes_packages.py  → importlib.util.spec_from_file_location
                                    (relative imports FAIL, no parent package)
  2. Via server_flask.py explicit → hecos.modules.net_search.web.routes
                                    (relative imports WORK)

Guard logic on every @app.route prevents AssertionError on double-load.
"""
from __future__ import annotations

import os
import logging
from flask import jsonify, request, send_from_directory, redirect
from jinja2 import FileSystemLoader, ChoiceLoader

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("net_search.web")


def _try_import_search_modules():
    """
    Returns (init_search_subsystem, register_search_routes, register_bookmarks_routes)
    or raises ImportError if neither relative nor absolute imports work.
    """
    # Try absolute imports first (always works, regardless of load context)
    try:
        from hecos.modules.net_search.search import init_search_subsystem
        from hecos.modules.net_search.web.search_routes import register_search_routes
        from hecos.modules.net_search.web.search_bookmarks_routes import register_bookmarks_routes
        return init_search_subsystem, register_search_routes, register_bookmarks_routes
    except ImportError:
        pass

    # Fallback: relative imports (works when loaded as hecos.modules.net_search.web.routes)
    from ..search import init_search_subsystem          # noqa: E402
    from .search_routes import register_search_routes   # noqa: E402
    from .search_bookmarks_routes import register_bookmarks_routes  # noqa: E402
    return init_search_subsystem, register_search_routes, register_bookmarks_routes


def _safe_route(app, rule, endpoint, view_func, **options):
    """Register a Flask route only if the endpoint is not already registered."""
    if endpoint in app.view_functions:
        return False
    app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, **options)
    return True


def init_plugin_routes(app, cfg_mgr, root_dir, logger=None):
    """
    Initializes standalone routes and services for the Net Search System App.
    Safe to call multiple times — all routes are guarded against double-registration.
    """
    log = logger or hecos_logger
    log.info("[NetSearch] Initializing Net Search routes and services...")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tpl_dir = os.path.join(base_dir, "web", "templates")
    stc_dir = os.path.join(base_dir, "web", "static")

    # ── Extend Jinja loader so search templates are discoverable ─────────────
    try:
        if isinstance(app.jinja_loader, ChoiceLoader):
            if not any(isinstance(l, FileSystemLoader) and l.searchpath == [tpl_dir]
                       for l in app.jinja_loader.loaders):
                app.jinja_loader.loaders.append(FileSystemLoader(tpl_dir))
        elif app.jinja_loader:
            app.jinja_loader = ChoiceLoader([app.jinja_loader, FileSystemLoader(tpl_dir)])
        else:
            app.jinja_loader = FileSystemLoader(tpl_dir)
    except Exception as je:
        log.warning(f"[NetSearch] Could not extend Jinja loader: {je}")

    # ── Static files routes ──────────────────────────────────────────────────
    _stc_dir = stc_dir  # capture for closures

    def netsearch_static_files(filename):
        return send_from_directory(_stc_dir, filename)

    def browser_static_files_alias(filename):
        target = os.path.join(_stc_dir, filename)
        if os.path.exists(target):
            return send_from_directory(_stc_dir, filename)
        ba_stc = os.path.join(root_dir, "hecos", "modules", "browser_automation", "web", "static")
        if os.path.exists(os.path.join(ba_stc, filename)):
            return send_from_directory(ba_stc, filename)
        return send_from_directory(_stc_dir, filename)

    def route_netsearch_redirect():
        return redirect("/search")

    _safe_route(app, "/netsearch_static/<path:filename>",
                "netsearch_static_files", netsearch_static_files)
    _safe_route(app, "/browser_static/<path:filename>",
                "browser_static_files_alias", browser_static_files_alias)
    _safe_route(app, "/netsearch",
                "route_netsearch_redirect", route_netsearch_redirect, methods=["GET"])

    # ── Net Search Config API Routes for Central Hub ──────────────────────────
    def net_search_get_config():
        try:
            try:
                from hecos.modules.net_search.search.config import get_search_config
            except ImportError:
                from ..search.config import get_search_config
            return jsonify({"ok": True, "config": get_search_config()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    def net_search_post_config():
        try:
            incoming = request.get_json(force=True)
            if not isinstance(incoming, dict):
                return jsonify({"ok": False, "error": "Invalid payload"}), 400
            try:
                from hecos.modules.net_search.search.config import update_search_config
            except ImportError:
                from ..search.config import update_search_config
            return jsonify({"ok": update_search_config(incoming)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    _safe_route(app, "/hecos/api/plugins/net_search/config",
                "net_search_get_config", net_search_get_config, methods=["GET"])
    _safe_route(app, "/hecos/api/plugins/net_search/config",
                "net_search_post_config", net_search_post_config, methods=["POST"])

    # ── Initialize Search Subsystem & Register Core Search Routes ────────────
    # Only register /search and all /api/hsearch/* routes if not already present
    if "search_page" not in app.view_functions:
        try:
            init_ss, reg_search, reg_bookmarks = _try_import_search_modules()
            init_ss()
            reg_search(app, cfg_mgr, root_dir, log)
            reg_bookmarks(app, log)
            log.info("[NetSearch] /search page and API routes registered successfully.")
        except Exception as se:
            log.error(f"[NetSearch] Failed to register search routes: {se}", exc_info=True)
    else:
        log.debug("[NetSearch] /search already registered — skipping duplicate.")

    # ── Chat Auto-Injection for Search Cards ──────────────────────────────────
    _CHAT_MARKER = b'HECOS_ROOM_CHAT_V2_ACTIVE'
    _INJECT_SEARCH_CARD = (
        '\n<!-- Hecos Net Search Card Injection -->'
        '\n<script src="/netsearch_static/js/search/search_chat_card.js?t=20261029"></script>'
        '\n<!-- /Hecos Net Search -->'
    ).encode('utf-8')

    # Guard: only register the after_request hook once
    if not getattr(app, "_netsearch_card_hook_registered", False):
        @app.after_request
        def _search_card_inject_hook(response):
            try:
                ct = response.content_type or ''
                if 'text/html' not in ct:
                    return response
                data = response.get_data()
                if _CHAT_MARKER in data and b'search_chat_card.js' not in data:
                    close_body = b'</body>'
                    if close_body in data:
                        data = data.replace(close_body, _INJECT_SEARCH_CARD + b'\n' + close_body, 1)
                        response.set_data(data)
                        if response.content_length:
                            response.content_length = len(data)
            except Exception:
                pass
            return response

        app._netsearch_card_hook_registered = True

    log.info("[NetSearch] Routes, static assets, and Deep Search subsystem registered successfully.")
