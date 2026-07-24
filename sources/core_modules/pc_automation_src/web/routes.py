"""
web/routes.py
API routes for pc_automation package config panel.
Mapped via 'api_routes_file' in hpkg_manifest.toml.
"""
from flask import request, jsonify


def init_plugin_routes(app, cfg_mgr, root_dir, logger, get_sm=None):

    @app.route("/hecos/api/plugins/pc_automation/config", methods=["GET"])
    def get_pc_automation_config():
        try:
            cfg = cfg_mgr.config
            auto_cfg = cfg.get("plugins", {}).get("AUTOMATION", {})
            return jsonify({
                "enabled": auto_cfg.get("enabled", True),
                "move_duration": auto_cfg.get("move_duration", 0.15),
                "type_interval": auto_cfg.get("type_interval", 0.02),
                "allow_window_control": auto_cfg.get("allow_window_control", True),
            })
        except Exception as e:
            logger.error(f"[PC_AUTOMATION] GET config error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/hecos/api/plugins/pc_automation/config", methods=["POST"])
    def post_pc_automation_config():
        try:
            incoming = request.get_json(force=True)
            if not isinstance(incoming, dict):
                return jsonify({"ok": False, "error": "Invalid payload"}), 400

            allowed_keys = {"enabled", "move_duration", "type_interval", "allow_window_control"}
            cfg = cfg_mgr.config
            plugins = cfg.setdefault("plugins", {})
            auto_cfg = plugins.setdefault("AUTOMATION", {})

            for k, v in incoming.items():
                if k in allowed_keys:
                    auto_cfg[k] = v

            cfg_mgr.save()
            return jsonify({"ok": True})
        except Exception as e:
            logger.error(f"[PC_AUTOMATION] POST config error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
