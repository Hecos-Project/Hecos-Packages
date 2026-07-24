"""
Autonomous routes for weather_pro package.
Handles config persistence and weather data proxy.
Mapped via 'api_routes_file' in hpkg_manifest.toml.
"""
from flask import request, jsonify


def init_plugin_routes(app, cfg_mgr, root_dir, logger, get_sm=None):
    import sys
    import os
    plugin_path = os.path.dirname(os.path.abspath(__file__))
    if plugin_path not in sys.path:
        sys.path.insert(0, plugin_path)
    from weather_pro_config.config_manager import get_config, save_config

    # ── 1. Config GET ──────────────────────────────────────────────────────────

    @app.route("/hecos/api/plugins/weather_pro/config", methods=["GET"])
    def get_weather_pro_config_api():
        return jsonify(get_config())

    # ── 2. Config POST ─────────────────────────────────────────────────────────

    @app.route("/hecos/api/plugins/weather_pro/config", methods=["POST"])
    def post_weather_pro_config_api():
        try:
            incoming = request.get_json(force=True)
            if not isinstance(incoming, dict):
                return jsonify({"ok": False, "error": "Invalid payload"}), 400

            cfg = get_config()
            wp_incoming = incoming.get("weather_pro", {})

            existing = cfg.get("weather_pro", {})
            existing.update(wp_incoming)
            cfg["weather_pro"] = existing

            if save_config(cfg):
                return jsonify({"ok": True})
            return jsonify({"ok": False, "error": "Save failed"}), 500

        except Exception as exc:
            logger.error(f"[WeatherPro] POST config error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    # ── 3. Weather data proxy (used by the widget and config panel preview) ───

    @app.route("/api/weather_pro/data", methods=["GET"])
    def weather_pro_data_api():
        """
        Returns live weather data for the configured city.
        Used by the widget and the config panel live preview.
        """
        try:
            # Dynamically locate the plugin module
            import importlib
            import sys as _sys

            plugin_dir = os.path.join(root_dir, "plugin", "weather_pro")
            if plugin_dir not in _sys.path:
                _sys.path.insert(0, os.path.join(root_dir, "plugin"))

            from weather_pro.main import WeatherProPlugin
            wp = WeatherProPlugin.__new__(WeatherProPlugin)
            wp._ip_cache = None

            # Inject a lightweight config_manager shim
            cfg = get_config().get("weather_pro", {})

            class _CfgShim:
                config = {"plugins": {"WEATHER_PRO": cfg}}

            wp.config_manager = _CfgShim()

            city = request.args.get("city", "")
            data = wp.get_weather_data(city)
            return jsonify(data)
        except Exception as exc:
            logger.error(f"[WeatherPro] data endpoint error: {exc}")
            return jsonify({"error": str(exc)}), 500
