"""
web/routes.py
Routes registration for browser_automation and Deep Search submodule.
"""
import os
from flask import Blueprint, jsonify, request, send_from_directory
from jinja2 import FileSystemLoader, ChoiceLoader
from hecos.core.logging import logger

def init_plugin_routes(app, cfg_mgr, root_dir, logger=None):
    """
    Initializes custom API routes for the browser_automation plugin and Deep Search.
    """
    from hecos.core.logging import logger as hecos_logger
    log = logger or hecos_logger
    log.info("[BROWSER] Initializing browser_automation and Deep Search routes...")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tpl_dir = os.path.join(base_dir, "web", "templates")
    stc_dir = os.path.join(base_dir, "web", "static")

    # ── Extend Jinja loader so templates like search.html are found ───────────
    try:
        if isinstance(app.jinja_loader, ChoiceLoader):
            if not any(isinstance(l, FileSystemLoader) and l.searchpath == [tpl_dir] for l in app.jinja_loader.loaders):
                app.jinja_loader.loaders.append(FileSystemLoader(tpl_dir))
        elif app.jinja_loader:
            app.jinja_loader = ChoiceLoader([app.jinja_loader, FileSystemLoader(tpl_dir)])
        else:
            app.jinja_loader = FileSystemLoader(tpl_dir)
    except Exception as je:
        log.warning(f"[BROWSER] Could not extend Jinja loader: {je}")

    # ── Static files route for browser & search ───────────────────────────────
    @app.route("/browser_static/<path:filename>")
    def browser_static_files(filename):
        return send_from_directory(stc_dir, filename)

    # ── Browser Automation Config Routes (Legacy & Core) ──────────────────────
    @app.route("/hecos/api/plugins/browser_automation/config", methods=["GET"])
    def browser_automation_get_config():
        try:
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
                    "search": cfg.get("search", {}),
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
            # Dynamic engine import
            here = os.path.dirname(os.path.abspath(__file__))
            eng_path = os.path.normpath(os.path.join(here, "..", "plugin", "engine.py"))
            import importlib.util
            spec = importlib.util.spec_from_file_location("browser_engine_dyn", eng_path)
            engine = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(engine)

            root_cfg = cfg_mgr.config
            cfg = root_cfg.get("plugins", {}).get("BROWSER", {})
            port = cfg.get("cdp_port", 9222)
            msg = engine.launch_external_browser(port=port)
            return jsonify({"ok": True, "message": msg})
        except Exception as exc:
            log.error(f"[WebUI] browser_launch_external error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    log.info("[BROWSER] Routes and static assets registered successfully.")
