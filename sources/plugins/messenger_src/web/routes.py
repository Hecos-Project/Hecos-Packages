"""
MODULE: Messenger — Flask API Routes (v2.1)
PACKAGE: messenger
DESCRIPTION: Exposes configuration CRUD (including 3-tier AI routing overrides,
             15-minute follow-up memory, and anti-hallucination guard settings),
             live provider diagnostics, and interactive WhatsApp session management.
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any
from flask import jsonify, request


def _get_config_module() -> Any:
    try:
        import hecos.hpm.messenger.messenger_config.config_manager as cm
        return cm
    except ImportError:
        import messenger_config.config_manager as cm  # type: ignore[import-not-found]
        return cm


def _get_defaults_dict() -> dict[str, Any]:
    try:
        from hecos.hpm.messenger.core.defaults import get_ui_defaults
        return get_ui_defaults()
    except ImportError:
        from core.defaults import get_ui_defaults  # type: ignore[import-not-found]
        return get_ui_defaults()


def _get_plugin_main() -> Any:
    for mod_path in ("hecos.hpm.messenger.main", "messenger.main"):
        try:
            return importlib.import_module(mod_path)
        except ImportError:
            continue
    return None


_TOP_LEVEL_KEYS = (
    "remember_last_channel",
    "last_channel_ttl_minutes",
    "general_override_enabled",
    "general_override",
    "anti_hallucination_guard_enabled",
    "anti_hallucination_prompt",
)


def init_plugin_routes(app: Any, cfg_mgr: Any, root_dir: str, logger: Any, get_sm: Any = None) -> None:
    plugin_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if plugin_path not in sys.path:
        sys.path.insert(0, plugin_path)

    @app.route("/hecos/api/plugins/messenger/config", methods=["GET"])
    def hpm_messenger_get_config():
        try:
            cm = _get_config_module()
            return jsonify({
                "ok": True,
                "config": cm.get_config(),
                "defaults": _get_defaults_dict(),
            })
        except Exception as exc:
            logger.error(f"[Messenger] GET config error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/hecos/api/plugins/messenger/config", methods=["POST"])
    def hpm_messenger_post_config():
        try:
            data = request.get_json(force=True) or {}
            cm = _get_config_module()
            cfg = cm.get_config()

            for key in _TOP_LEVEL_KEYS:
                if key in data:
                    cfg[key] = data[key]

            for section in ("telegram", "whatsapp"):
                if section in data and isinstance(data[section], dict):
                    cfg.setdefault(section, {}).update(data[section])

            saved = cm.save_config(cfg)
            if not saved:
                return jsonify({"ok": False, "error": "Configuration validation or save failed."}), 400

            try:
                plugin_main = _get_plugin_main()
                if plugin_main:
                    plugin_main.on_load()
                    logger.info("[Messenger] Configuration saved, routing_override.yaml synced, and hot-reloaded.")
            except Exception as reload_exc:
                logger.error(f"[Messenger] Error hot-reloading config: {reload_exc}")

            return jsonify({
                "ok": True,
                "config": cm.get_config(),
                "defaults": _get_defaults_dict(),
            })
        except Exception as exc:
            logger.error(f"[Messenger] POST config error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/hecos/api/plugins/messenger/status", methods=["GET"])
    def hpm_messenger_live_status():
        try:
            cm = _get_config_module()
            cfg_obj = cm.get_config_obj()
            plugin_main = _get_plugin_main()
            if not plugin_main:
                return jsonify({"ok": False, "error": "Messenger module not loaded."}), 500

            providers_status = {}
            for prov in plugin_main.registry.all():
                health = prov.check_health(prov.get_provider_config(cfg_obj))
                providers_status[prov.name] = {
                    "enabled": health.enabled,
                    "state": health.state,
                    "summary": health.summary,
                    "method_used": health.method_used,
                    "details": health.details,
                }
            return jsonify({"ok": True, "providers": providers_status})
        except Exception as exc:
            logger.error(f"[Messenger] GET status error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/hecos/api/plugins/messenger/whatsapp/open-session", methods=["POST"])
    def hpm_messenger_open_whatsapp_session():
        try:
            cm = _get_config_module()
            cfg_obj = cm.get_config_obj()
            plugin_main = _get_plugin_main()
            if not plugin_main:
                return jsonify({"ok": False, "error": "Messenger module not loaded."}), 500

            wa_prov = plugin_main.registry.get("whatsapp")
            if not wa_prov or not hasattr(wa_prov, "open_session"):
                return jsonify({"ok": False, "error": "WhatsApp provider unavailable."}), 500

            result = wa_prov.open_session(cfg_obj.whatsapp)
            status_code = 200 if result.get("ok") else 400
            return jsonify(result), status_code
        except Exception as exc:
            logger.error(f"[Messenger] Open WhatsApp session error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/hecos/api/plugins/messenger/whatsapp/scan-groups", methods=["POST"])
    def hpm_messenger_scan_whatsapp_groups():
        try:
            cm = _get_config_module()
            cfg_obj = cm.get_config_obj()
            plugin_main = _get_plugin_main()
            if not plugin_main:
                return jsonify({"ok": False, "error": "Messenger module not loaded."}), 500

            wa_prov = plugin_main.registry.get("whatsapp")
            if not wa_prov or not hasattr(wa_prov, "scan_groups"):
                return jsonify({"ok": False, "error": "WhatsApp provider unavailable."}), 500

            result = wa_prov.scan_groups(cfg_obj.whatsapp)
            status_code = 200 if result.get("ok") else 400
            return jsonify(result), status_code
        except Exception as exc:
            logger.error(f"[Messenger] Scan WhatsApp groups error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/hecos/api/plugins/messenger/telegram/resolve-chat", methods=["POST"])
    def hpm_messenger_resolve_telegram_chat():
        try:
            payload = request.get_json(force=True) or {}
            chat_ref = str(payload.get("chat_id") or "").strip()
            cm = _get_config_module()
            cfg_obj = cm.get_config_obj()
            plugin_main = _get_plugin_main()
            if not plugin_main:
                return jsonify({"ok": False, "error": "Messenger module not loaded."}), 500

            tg_prov = plugin_main.registry.get("telegram")
            if not tg_prov or not hasattr(tg_prov, "probe_chat"):
                return jsonify({"ok": False, "error": "Telegram provider unavailable."}), 500

            result = tg_prov.probe_chat(cfg_obj.telegram, chat_ref)
            status_code = 200 if result.get("ok") else 400
            return jsonify(result), status_code
        except Exception as exc:
            logger.error(f"[Messenger] Resolve Telegram chat error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500
