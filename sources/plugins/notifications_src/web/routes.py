"""
Notifications Center — API Routes
Loaded dynamically via importlib by routes_packages.py.
MUST use absolute imports only (no relative imports).
"""
from hecos.core.logging import logger


def init_plugin_routes(app, cfg_mgr=None, root_dir=None, log=None, get_sm=None):
    """Registers all API routes for the Notifications Center plugin."""
    from flask import jsonify, request as flask_request

    @app.route('/hecos/api/plugins/notifications/config', methods=['GET'])
    def get_notifications_config():
        try:
            from hecos.hpm.notifications.config import load_config
            cfg = load_config()
            return jsonify({"status": "success", "config": cfg})
        except Exception as e:
            logger.error(f"[NOTIFICATIONS API] GET error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/hecos/api/plugins/notifications/config', methods=['POST'])
    def update_notifications_config():
        try:
            from hecos.hpm.notifications.config import save_config
            data = flask_request.json
            if not data:
                return jsonify({"status": "error", "message": "No data provided"}), 400
            success = save_config(data)
            if success:
                return jsonify({"status": "success"})
            return jsonify({"status": "error", "message": "Failed to save"}), 500
        except Exception as e:
            logger.error(f"[NOTIFICATIONS API] POST error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/hecos/api/plugins/notifications/test', methods=['POST'])
    def test_notification():
        try:
            from hecos.hpm.notifications.dispatcher import notify
            from hecos.hpm.notifications.event_types import SystemEvent
            notify(
                event=SystemEvent.CUSTOM,
                subject="Hecos Test Notification",
                message="If you are reading this message, the Hecos Notifications Center is configured correctly!"
            )
            return jsonify({"status": "success", "message": "Test notification dispatched."})
        except Exception as e:
            logger.error(f"[NOTIFICATIONS API] test error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/hecos/api/plugins/notifications/available_plugins', methods=['GET'])
    def get_available_plugins():
        """
        Returns the list of messaging plugins currently installed and loaded.
        The frontend uses this to dynamically build the destination form.
        """
        try:
            from hecos.core.system.module_state import get_plugin_module
            available = []

            # Check MAIL plugin
            mail_mod = get_plugin_module("MAIL")
            if mail_mod and hasattr(mail_mod, "tools"):
                available.append({
                    "tag": "MAIL",
                    "label": "Email (MAIL)",
                    "icon": "fas fa-envelope",
                    "placeholder": "address@email.com",
                    "hint": "Format: MAIL:your@email.com"
                })

            # Check MESSENGER plugin — detect available platforms
            msg_mod = get_plugin_module("MESSENGER")
            if msg_mod and hasattr(msg_mod, "tools"):
                platforms = []
                try:
                    # Attempt to get configured platforms from MESSENGER
                    if hasattr(msg_mod.tools, "get_available_platforms"):
                        platforms = msg_mod.tools.get_available_platforms()
                    elif hasattr(msg_mod.tools, "_platforms"):
                        platforms = list(msg_mod.tools._platforms.keys())
                except Exception:
                    platforms = ["Telegram", "WhatsApp"]

                for platform in platforms:
                    available.append({
                        "tag": "MESSENGER",
                        "label": f"Messenger – {platform}",
                        "icon": "fas fa-comments",
                        "platform": platform,
                        "placeholder": "@username or number",
                        "hint": f"Format: MESSENGER:{platform}:@username"
                    })

                if not platforms:
                    available.append({
                        "tag": "MESSENGER",
                        "label": "Messenger",
                        "icon": "fas fa-comments",
                        "platform": "",
                        "placeholder": "Platform:@username",
                        "hint": "Format: MESSENGER:Telegram:@username"
                    })

            return jsonify({"status": "success", "plugins": available})
        except Exception as e:
            logger.error(f"[NOTIFICATIONS API] available_plugins error: {e}")
            return jsonify({"status": "error", "message": str(e), "plugins": []}), 500

    logger.info("[NOTIFICATIONS] API routes registered.")
