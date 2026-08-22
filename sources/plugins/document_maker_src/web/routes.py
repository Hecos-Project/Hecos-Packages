"""
Autonomous routes for document_maker package.
Handles config persistence for the web UI.
"""
from flask import request, jsonify
import os
import json

def init_plugin_routes(app, cfg_mgr, root_dir, logger, get_sm=None):
    plugin_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_file = os.path.join(plugin_path, "docs_config.json")

    def get_config():
        if os.path.exists(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[DOCS] Error reading config: {e}")
        return {"pdf_save_path": "media/documents"}

    def save_config(data):
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"[DOCS] Error writing config: {e}")
            return False

    @app.route("/hecos/api/plugins/document_maker/config", methods=["GET"])
    def get_docs_config_api():
        return jsonify(get_config())

    @app.route("/hecos/api/plugins/document_maker/config", methods=["POST"])
    def post_docs_config_api():
        try:
            incoming = request.get_json(force=True)
            if not isinstance(incoming, dict):
                return jsonify({"ok": False, "error": "Invalid payload"}), 400
            
            current_config = get_config()
            current_config.update(incoming)
            
            if save_config(current_config):
                return jsonify({"ok": True})
            return jsonify({"ok": False, "error": "Save failed"}), 500
        except Exception as exc:
            logger.error(f"[DOCS] POST config error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500
