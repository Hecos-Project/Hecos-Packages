import os
from flask import Blueprint, jsonify, request
from hecos.core.logging import logger

def init_plugin_routes(app, cfg_mgr, root_dir, logger=None):
    """
    Initializes custom API routes for the browser_automation plugin.
    """
    from hecos.core.logging import logger as hecos_logger
    log = logger or hecos_logger
    log.info("[BROWSER] Initializing plugin routes...")
    
    @app.route("/hecos/api/plugins/browser_automation/config", methods=["GET"])
    def browser_automation_get_config():
        try:
            # We fetch the configuration from the BROWSER key inside plugins
            # Since the core pydantic schema was removed, it's just a dict in plugins.yaml
            root_cfg = cfg_mgr.config
            cfg = root_cfg.get("plugins", {}).get("BROWSER", {})
            return jsonify({
                "ok": True,
                "config": {
                    "enabled": cfg.get("enabled", True),
                    "headless": cfg.get("headless", False),
                    "block_ads": cfg.get("block_ads", True),
                    "startup_url": cfg.get("startup_url", "http://localhost:7070"),
                    "browser_type": cfg.get("browser_type", "chromium"),
                    "browser_engine_mode": cfg.get("browser_engine_mode", "cdp_mode"),
                    "cdp_port": cfg.get("cdp_port", 9222),
                    "thread_timeout": cfg.get("thread_timeout", 60.0),
                    "nav_timeout": cfg.get("nav_timeout", 30),
                    "wait_timeout": cfg.get("wait_timeout", 8),
                    "action_timeout": cfg.get("action_timeout", 5),
                    "routing_override": root_cfg.get("routing_overrides", {}).get("overrides", {}).get("BROWSER", "")
                }
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/hecos/api/plugins/browser_automation/config", methods=["POST"])
    def browser_automation_post_config():
        try:
            incoming = request.get_json(force=True)
            if not isinstance(incoming, dict):
                return jsonify({"ok": False, "error": "Invalid payload"}), 400
            
            routing_override = incoming.pop("routing_override", None)

            # Update the configuration in plugins.BROWSER
            # This uses the same update payload format as the main config endpoint
            payload = {
                "plugins": {
                    "BROWSER": incoming
                }
            }
            if routing_override is not None:
                payload["routing_overrides"] = {
                    "overrides": {
                        "BROWSER": routing_override
                    }
                }

            save_result = cfg_mgr.update_config(payload)
            if save_result:
                return jsonify({"ok": True})
            return jsonify({"ok": False, "error": "Save failed"}), 500
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/browser/launch_external", methods=["POST"])
    def browser_launch_external():
        """Launches the external browser and connects via CDP."""
        try:
            # Import the engine dynamically from our plugin package
            from hecos.hpm.browser_automation.plugin import engine
            root_cfg = cfg_mgr.config
            cfg = root_cfg.get("plugins", {}).get("BROWSER", {})
            port = cfg.get("cdp_port", 9222)
            msg = engine.launch_external_browser(port=port)
            return jsonify({"ok": True, "message": msg})
        except Exception as exc:
            logger.error(f"[WebUI] browser_launch_external error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500
