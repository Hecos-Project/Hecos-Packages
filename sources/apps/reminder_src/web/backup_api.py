"""
MODULE: Reminder Backup API
DESCRIPTION: Provides /api/reminders/backup and /api/reminders/restore routes for Global Backup.
"""

from flask import jsonify, request
from hecos.core.logging import logger

def register_backup_routes(app):
    """Registers the backup routes for the reminder plugin."""

    @app.route("/api/reminders/backup", methods=["GET"], endpoint="mbkp_reminders_backup_pkg")
    def reminders_backup():
        """Esporta tutti i promemoria come JSON."""
        try:
            from .. import store
            reminders = store.get_all()
            return jsonify({"ok": True, "count": len(reminders), "data": reminders})
        except Exception as e:
            logger.error(f"[REMINDERS BACKUP] reminders_backup error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/reminders/restore", methods=["POST"], endpoint="mbkp_reminders_restore_pkg")
    def reminders_restore():
        """
        Ripristina promemoria da JSON.
        Body: { data: [...], mode: "duplicate"|"replace" }
        """
        try:
            from .. import store
            body = request.get_json(force=True) or {}
            reminders = body.get("data", [])
            mode = body.get("mode", "duplicate")

            if not isinstance(reminders, list):
                return jsonify({"ok": False, "error": "data must be a list"}), 400

            count = store.import_reminders(reminders, mode=mode)
            return jsonify({"ok": True, "imported": count})
        except Exception as e:
            logger.error(f"[REMINDERS BACKUP] reminders_restore error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
