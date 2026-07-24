"""
Autonomous API routes for the Reminder package.
Handles config persistence and ringtone listing.
Mapped via 'api_routes_file' in hpkg_manifest.toml.
"""


def init_plugin_routes(app, cfg_mgr, root_dir, logger, get_sm=None):
    import os
    import sys
    from flask import request, jsonify
    from flask_login import login_required

    # Ensure the plugin directory is importable
    plugin_path = os.path.dirname(os.path.abspath(__file__))  # web/
    pkg_root    = os.path.dirname(plugin_path)               # reminder/
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)

    from reminder_config.config_manager import get_reminder_config, save_reminder_section

    # Register backup routes
    from web.backup_api import register_backup_routes
    register_backup_routes(app)

    # ── 1. Config GET ─────────────────────────────────────────────────────────

    @app.route("/hecos/api/plugins/reminder/config", methods=["GET"])
    @login_required
    def get_reminder_config_api():
        try:
            return jsonify({"ok": True, "reminder": get_reminder_config()})
        except Exception as exc:
            logger.error(f"[Reminder] GET config error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    # ── 2. Config POST ────────────────────────────────────────────────────────

    @app.route("/hecos/api/plugins/reminder/config", methods=["POST"])
    @login_required
    def post_reminder_config_api():
        try:
            incoming = request.get_json(force=True)
            if not isinstance(incoming, dict):
                return jsonify({"ok": False, "error": "Invalid payload"}), 400

            section = incoming.get("reminder", incoming)   # accept both wrapped and flat
            if save_reminder_section(section):
                return jsonify({"ok": True})
            return jsonify({"ok": False, "error": "Save failed"}), 500

        except Exception as exc:
            logger.error(f"[Reminder] POST config error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    # ── 3. Ringtone listing ───────────────────────────────────────────────────

    @app.route("/api/ext/reminder/ringtones", methods=["GET"])
    def list_reminder_ringtones():
        """Return available ringtone files from the plugin's assets/sounds folder."""
        try:
            sounds_dir = os.path.join(root_dir, "assets", "sounds")
            if not os.path.isdir(sounds_dir):
                return jsonify({"ok": True, "ringtones": []})
            files = sorted([
                f for f in os.listdir(sounds_dir)
                if f.lower().endswith((".mp3", ".wav", ".ogg"))
            ])
            return jsonify({"ok": True, "ringtones": files})
        except Exception as exc:
            logger.error(f"[Reminder] ringtones error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500
    # -- DELETE /api/ext/reminder/history � clear history ------------------------
    @app.route("/api/ext/reminder/history", methods=["DELETE"])
    @login_required
    def reminder_clear_history():
        from hecos.hpm.reminder.main import tools
        store = getattr(tools, "_store", None)  # Fallback logic if needed, but normally store is in hecos.hpm.reminder.store
        from hecos.hpm.reminder.store import ReminderStore
        ok = ReminderStore().clear_history()
        return jsonify({"ok": ok})

    # -- POST /api/ext/reminder/<id>/snooze � snooze ---------------------------
    @app.route("/api/ext/reminder/<reminder_id>/snooze", methods=["POST"])
    @login_required
    def reminder_snooze(reminder_id):
        data    = request.get_json(force=True) or {}
        minutes = int(data.get("minutes", 15))
        from hecos.hpm.reminder.main import tools
        result = tools.snooze_reminder(reminder_id, minutes)
        return jsonify({"ok": "?" not in result, "message": result})

    # -- POST /api/ext/reminder/stop � stop audio ------------------------------
    @app.route("/api/ext/reminder/stop", methods=["POST"])
    @login_required
    def reminder_stop_audio():
        from hecos.hpm.reminder.main import tools
        result = tools.stop_audio()
        return jsonify({"ok": True, "message": result})

    # -- POST /api/ext/reminder/<id>/interactive � toggle mode -----------------
    @app.route("/api/ext/reminder/<reminder_id>/interactive", methods=["POST"])
    @login_required
    def reminder_set_interactive(reminder_id):
        from hecos.hpm.reminder.store import ReminderStore
        body = request.get_json(silent=True) or {}
        interactive = body.get("interactive")
        if interactive is None:
            return jsonify({"ok": False, "error": "Missing 'interactive' field"}), 400
        ok = ReminderStore().update_interactive(reminder_id, bool(interactive))
        return jsonify({"ok": ok})

    # -- GET /hecos/api/ext/sounds/<filename> � stream sound file for browser preview --
    @app.route("/hecos/api/ext/sounds/<path:filename>", methods=["GET"])
    def reminder_serve_sound(filename):
        from flask import send_from_directory, abort
        _base = root_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        sounds_dir = os.path.join(_base, "assets", "sounds")
        safe_name = os.path.basename(filename)
        full_path = os.path.join(sounds_dir, safe_name)
        if not os.path.isfile(full_path):
            abort(404)
        return send_from_directory(sounds_dir, safe_name)

