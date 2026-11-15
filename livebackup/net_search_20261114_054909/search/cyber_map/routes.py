"""
search/cyber_map/routes.py
Dedicated modular Flask routes for Cyber Map telemetry, live Tor circuits,
privacy-aware batch host resolution, and the standalone detached Cyber Map window.
"""
from __future__ import annotations

import time
import logging
from flask import jsonify, render_template, request
from flask_login import login_required

from .geo_resolver import get_base_topology, resolve_host_batch
from .tor_circuit_probe import get_live_tor_circuits

try:
    from ..components.catalog import get_component
    from ..http_client import is_tor_online
except (ImportError, ValueError):
    from hecos.modules.net_search.search.components.catalog import get_component
    from hecos.modules.net_search.search.http_client import is_tor_online

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("net_search.cyber_map.routes")


def register_cyber_map_routes(app, logger=None):
    """Registers Cyber Map UI and JSON API endpoints safely without double registration."""
    if "search_cyber_map_page" in app.view_functions:
        return

    log = logger or hecos_logger
    log.info("[CyberMap] Registering modular Cyber Map UI and telemetry routes...")

    @app.route("/search/cyber_map", methods=["GET"])
    @login_required
    def search_cyber_map_page():
        """Renders the standalone detached Cyber Map window."""
        session_id = request.args.get("session", "").strip()
        view_mode = request.args.get("view", "").strip()
        return render_template(
            "cyber_map/standalone_map.html",
            initial_session=session_id,
            initial_view=view_mode,
            tor_online=is_tor_online(),
            version=int(time.time()),
        )

    @app.route("/api/hsearch/cyber_map/topology", methods=["GET"])
    @login_required
    def api_cyber_map_topology():
        try:
            return jsonify(get_base_topology())
        except Exception as e:
            log.warning(f"[CyberMap] topology error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/hsearch/cyber_map/tor_circuits", methods=["GET"])
    @login_required
    def api_cyber_map_tor_circuits():
        try:
            force = request.args.get("force", "false").lower() in ("1", "true")
            return jsonify({"ok": True, **get_live_tor_circuits(force_refresh=force)})
        except Exception as e:
            log.warning(f"[CyberMap] tor_circuits error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/hsearch/cyber_map/resolve_batch", methods=["POST"])
    @login_required
    def api_cyber_map_resolve_batch():
        try:
            data = request.get_json(force=True, silent=True) or {}
            items = data.get("items") or []
            if not isinstance(items, list):
                return jsonify({"ok": False, "error": "items must be a list"}), 400
            local_only = data.get("local_only")
            if local_only is not None:
                local_only = bool(local_only)
            return jsonify(resolve_host_batch(items=items, local_only=local_only))
        except Exception as e:
            log.warning(f"[CyberMap] resolve_batch error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/hsearch/cyber_map/new_circuit", methods=["POST"])
    @login_required
    def api_cyber_map_new_circuit():
        try:
            tor_comp = get_component("tor_daemon")
            if not tor_comp:
                return jsonify({"ok": False, "error": "Tor component unavailable"}), 404
            ok, msg = tor_comp.new_circuit()
            time.sleep(0.35 if ok else 0.0)
            circuits_info = get_live_tor_circuits(force_refresh=True)
            return jsonify({"ok": ok, "message": msg, **circuits_info})
        except Exception as e:
            log.warning(f"[CyberMap] new_circuit error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
