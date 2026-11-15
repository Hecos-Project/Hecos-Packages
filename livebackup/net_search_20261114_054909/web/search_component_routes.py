"""
web/search_component_routes.py
Dedicated Flask API routes for Deep Search components management and Tor lifecycle.
"""
from __future__ import annotations

import logging
from flask import request, jsonify
from flask_login import login_required

try:
    from hecos.modules.net_search.search.components.catalog import get_component, get_all_statuses
    from hecos.modules.net_search.search.http_client import check_tor_connection
except (ImportError, ValueError):
    from ..search.components.catalog import get_component, get_all_statuses
    from ..search.http_client import check_tor_connection

try:
    from hecos.core.logging import logger as hecos_logger
except (ImportError, ValueError):
    hecos_logger = logging.getLogger("net_search.web.components")


def register_component_routes(app, logger=None):
    """Registers components lifecycle and Tor diagnostic endpoints on the Flask application."""
    if "api_search_components" in app.view_functions:
        return
    log = logger or hecos_logger
    log.info("[DeepSearch] Registering component and Tor diagnostic routes...")

    @app.route("/api/hsearch/components", methods=["GET"])
    @login_required
    def api_search_components():
        return jsonify({"ok": True, "components": get_all_statuses()})

    @app.route("/api/hsearch/components/<component_id>/install", methods=["POST"])
    @login_required
    def api_search_component_install(component_id):
        comp = get_component(component_id)
        if not comp:
            log.warning(f"[DeepSearch] Install requested for unknown component: {component_id}")
            return jsonify({"ok": False, "error": f"Unknown component {component_id}"}), 404

        log.info(f"[DeepSearch] Installing component '{component_id}'...")
        ok, msg = comp.install()
        if ok:
            log.info(f"[DeepSearch] Component '{component_id}' installed: {msg}")
        else:
            log.error(f"[DeepSearch] Component '{component_id}' install failed: {msg}")
        return jsonify({"ok": ok, "message": msg, "status": comp.get_status().to_dict()})

    @app.route("/api/hsearch/components/<component_id>/uninstall", methods=["POST"])
    @login_required
    def api_search_component_uninstall(component_id):
        comp = get_component(component_id)
        if not comp:
            return jsonify({"ok": False, "error": f"Unknown component {component_id}"}), 404
        ok, msg = comp.uninstall()
        log.info(f"[DeepSearch] Component '{component_id}' uninstall ok={ok}: {msg}")
        return jsonify({"ok": ok, "message": msg, "status": comp.get_status().to_dict()})

    @app.route("/api/hsearch/components/<component_id>/start", methods=["POST"])
    @login_required
    def api_search_component_start(component_id):
        comp = get_component(component_id)
        if not comp:
            return jsonify({"ok": False, "error": f"Unknown component {component_id}"}), 404
        log.info(f"[DeepSearch] Starting component '{component_id}'...")
        ok, msg = comp.start()
        if ok:
            log.info(f"[DeepSearch] Component '{component_id}' started: {msg}")
        else:
            log.error(f"[DeepSearch] Component '{component_id}' start failed: {msg}")
        return jsonify({"ok": ok, "message": msg, "status": comp.get_status().to_dict()})

    @app.route("/api/hsearch/components/<component_id>/stop", methods=["POST"])
    @login_required
    def api_search_component_stop(component_id):
        comp = get_component(component_id)
        if not comp:
            return jsonify({"ok": False, "error": f"Unknown component {component_id}"}), 404
        ok, msg = comp.stop()
        log.info(f"[DeepSearch] Component '{component_id}' stop ok={ok}: {msg}")
        return jsonify({"ok": ok, "message": msg, "status": comp.get_status().to_dict()})

    @app.route("/api/hsearch/tor_status", methods=["GET"])
    @login_required
    def api_search_tor_status():
        info = check_tor_connection()
        log.debug(f"[DeepSearch] Tor status check: {info}")
        return jsonify(info)

    @app.route("/api/hsearch/tor_newnym", methods=["POST"])
    @login_required
    def api_search_tor_newnym():
        tor_comp = get_component("tor_daemon")
        if not tor_comp:
            return jsonify({"ok": False, "error": "Tor component not found"}), 404
        ok, msg = tor_comp.new_circuit()
        log.info(f"[DeepSearch] Tor NEWNYM ok={ok}: {msg}")
        return jsonify({"ok": ok, "message": msg})
