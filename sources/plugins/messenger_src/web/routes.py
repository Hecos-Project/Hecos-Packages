"""
MODULE: Messenger — API Routes
PACKAGE: messenger
"""

from flask import request, jsonify


def _get_config_module():
    """
    Returns the config_manager module using the canonical installed path first,
    then falls back to a bare import (dev/standalone mode via sys.path injection).

    This avoids the double-module bug where routes.py and main.py would each
    get a SEPARATE `_manager` singleton if different import paths were used.
    """
    try:
        import hecos.hpm.messenger.messenger_config.config_manager as _cm
        return _cm
    except ImportError:
        import messenger_config.config_manager as _cm
        return _cm


def init_plugin_routes(app, cfg_mgr, root_dir, logger, get_sm=None):
    import os
    import sys

    # Ensure the plugin root (messenger/) is on sys.path so bare imports work
    # when running in dev/standalone mode (before the plugin is installed).
    plugin_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if plugin_path not in sys.path:
        sys.path.insert(0, plugin_path)

    @app.route("/hecos/api/plugins/messenger/config", methods=["GET"])
    def hpm_messenger_get_config():
        try:
            cm = _get_config_module()
            cfg = cm.get_config()
            return jsonify({"ok": True, "config": cfg})
        except Exception as e:
            logger.error(f"[Messenger] GET config error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/hecos/api/plugins/messenger/config", methods=["POST"])
    def hpm_messenger_post_config():
        try:
            data = request.get_json(force=True) or {}
            cm = _get_config_module()
            cfg = cm.get_config()

            # Merge incoming fields into the current config dict
            for section in ("telegram", "whatsapp", "discord"):
                if section in data:
                    cfg.setdefault(section, {}).update(data[section])

            cm.save_config(cfg)

            # Hot-reload the plugin singleton so the new config is active immediately
            try:
                import importlib
                # Try the installed path first, then the bare name (dev mode)
                for mod_path in ("hecos.hpm.messenger.main", "messenger.main"):
                    try:
                        plugin_main = importlib.import_module(mod_path)
                        plugin_main.on_load()
                        logger.info(f"[Messenger] Config saved and hot-reloaded via '{mod_path}'.")
                        break
                    except ImportError:
                        continue
            except Exception as e:
                logger.error(f"[Messenger] Error hot-reloading config: {e}")

            return jsonify({"ok": True})
        except Exception as e:
            logger.error(f"[Messenger] POST config error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
