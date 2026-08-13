from hecos.modules.flows.core_logic.registry import _REGISTRY, log
import time

def _auto_register_hecos_modules():
    """
    Scan active Hecos modules and register their public methods as Flow actions.
    This uses the existing registry.json commands catalog as the source of truth.
    """
    try:
        from hecos.core.system import module_loader
        from hecos.core.system.module_loader import get_plugin_module

        registry_path = module_loader.REGISTRY_PATH
        import json, os
        if not os.path.exists(registry_path):
            return

        with open(registry_path, encoding="utf-8") as f:
            reg = json.load(f)

        CATEGORY_MAP = {
            "AUDIO": "AUDIO", "REMINDER": "TIME", "CALENDAR": "TIME",
            "MAIL": "MAIL", "MESSENGER": "MESSAGING", "WEATHER": "DATA",
            "EXECUTOR": "SYSTEM", "BROWSER": "BROWSER", "WEB": "BROWSER",
            "WEBCAM": "VISION", "AUTOMATION": "AUTOMATION", "MEMORY": "MEMORY",
            "IMAGE_GEN": "MEDIA", "MEDIA_PLAYER": "MEDIA",
        }
        ICON_MAP = {
            "AUDIO": "🔊", "REMINDER": "⏰", "CALENDAR": "📅",
            "MAIL": "📧", "MESSENGER": "💬", "WEATHER": "🌤️",
            "EXECUTOR": "⚙️", "BROWSER": "🌐", "WEB": "🌐",
            "WEBCAM": "📷", "AUTOMATION": "🖱️", "MEMORY": "🧠",
            "IMAGE_GEN": "🎨", "MEDIA_PLAYER": "🎵",
        }

        KNOWN_PARAMS = {
            "EXECUTOR__execute_slash_command": {"command": "string"},
            "EXECUTOR__execute_background_command": {"command": "string"},
            "EXECUTOR__execute_shell_command": {"command": "string"},
            "EXECUTOR__run_python_code": {"code": "string"},
            "EXECUTOR__read_file": {"file_path": "string", "start_line": "integer", "end_line": "integer"},
            "EXECUTOR__write_file": {"file_path": "string", "content": "string", "mode": "string"},
            "EXECUTOR__patch_file": {"file_path": "string", "old_text": "string", "new_text": "string"},
            "EXECUTOR__delete_file": {"file_path": "string"},
            "EXECUTOR__create_dir": {"directory_path": "string"},
            "EXECUTOR__list_dir": {"directory_path": "string"},
            "EXECUTOR__kill_process": {"name": "string"},
            # ── Mail ──────────────────────────────────────────────────────────────
            "MAIL__send_email": {
                "to":            "string (recipient email or contact name)",
                "subject":       "string (email subject — overridden if template_id is set)",
                "body":          "string (email body — overridden if template_id is set)",
                "cc":            "string (optional CC addresses)",
                "bcc":           "string (optional BCC addresses)",
                "is_html":       "boolean (true = body is HTML)",
                "template_id":   "string (optional — ID of an email template to use)",
                "template_vars": "dict   (optional — variable values to interpolate in the template, e.g. {\"nome\": \"Mario\"})",
            },
            # ── Messenger ─────────────────────────────────────────────────────────
            "MESSENGER__send_message": {
                "to":            "string (recipient — prefix with platform, e.g. 'telegram:@username')",
                "text":          "string (message text — overridden if template_id is set)",
                "platform":      "string (optional — 'telegram' | 'whatsapp' | 'discord')",
                "template_id":   "string (optional — ID of a messenger template to use)",
                "template_vars": "dict   (optional — variable values to interpolate in the template)",
            },
            "WEATHER__get_forecast": {"location": "string"},
        }

        for module_tag, module_info in reg.items():
            commands = module_info.get("commands", {})
            category = CATEGORY_MAP.get(module_tag, "PLUGINS")
            icon = ICON_MAP.get(module_tag, "⚡")

            for cmd_name, cmd_desc in commands.items():
                action_name = f"{module_tag}__{cmd_name}"
                if action_name not in _REGISTRY:
                    _REGISTRY[action_name] = {
                        "name":        action_name,
                        "description": cmd_desc,
                        "params":      KNOWN_PARAMS.get(action_name, {}),
                        "category":    category,
                        "icon":        icon,
                        "fn":          None,   # resolved at execute time via module_loader
                    }

        log.info(f"[Flows.Registry] Auto-registered {len(_REGISTRY)} actions from Hecos modules.")
    except Exception as e:
        log.warning(f"[Flows.Registry] Auto-registration incomplete: {e}")


