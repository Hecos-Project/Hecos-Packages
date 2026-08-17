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
            from hecos.hpm.notifications.dispatcher import _dispatch_async
            from hecos.hpm.notifications.config import load_config, save_config
            import threading

            data = flask_request.get_json(silent=True) or {}
            template_id = data.get('template_id', '')

            cfg = load_config()
            destinations = cfg.get('destinations', {})

            if not destinations:
                return jsonify({"status": "error", "message": "No destinations configured. Add at least one destination first."}), 400

            # Temporarily force all destinations into the 'custom' rule so
            # _dispatch_async will send to everyone regardless of configured rules.
            original_rules = cfg.get('rules', {}).copy()
            original_tpl   = cfg.get('event_templates', {}).get('custom', '')

            cfg.setdefault('rules', {})['custom'] = list(destinations.keys())
            if template_id:
                cfg.setdefault('event_templates', {})['custom'] = template_id
            elif 'custom' in cfg.get('event_templates', {}):
                cfg['event_templates'].pop('custom', None)

            save_config(cfg)

            def _run_and_restore():
                try:
                    _dispatch_async(
                        event_type_str='custom',
                        subject='Hecos Test Notification',
                        message='If you are reading this, the Hecos Notifications Center is configured correctly!'
                    )
                finally:
                    # Restore original config
                    restored = load_config()
                    restored['rules'] = original_rules
                    if original_tpl:
                        restored.setdefault('event_templates', {})['custom'] = original_tpl
                    else:
                        restored.get('event_templates', {}).pop('custom', None)
                    save_config(restored)

            t = threading.Thread(target=_run_and_restore, daemon=True, name='NtfTestThread')
            t.start()

            return jsonify({"status": "success", "message": f"Test dispatched to {len(destinations)} destination(s)."})
        except Exception as e:
            logger.error(f"[NOTIFICATIONS API] test error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route('/hecos/api/plugins/notifications/history', methods=['GET'])
    def get_notifications_history():
        try:
            from hecos.hpm.notifications.history import get_history
            return jsonify(get_history())
        except Exception as e:
            logger.error(f"[NOTIFICATIONS API] history GET error: {e}")
            return jsonify([]), 500

    @app.route('/hecos/api/plugins/notifications/history/clear', methods=['POST'])
    def clear_notifications_history():
        try:
            from hecos.hpm.notifications.history import clear_history
            clear_history()
            return jsonify({"status": "ok"})
        except Exception as e:
            logger.error(f"[NOTIFICATIONS API] history CLEAR error: {e}")
            return jsonify({"status": "error"}), 500

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
