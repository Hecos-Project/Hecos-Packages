"""
MODULE: Notifications Center
PACKAGE: notifications
DESCRIPTION: Plugin-driven notification router for Hecos.
             Listens to system events and forwards them to MAIL/MESSENGER
             plugins if installed. No credentials stored here.
"""

from hecos.core.logging import logger
from .dispatcher import notify
from .event_types import SystemEvent


class NotificationsTools:
    """Hecos Notifications Center — event routing to MAIL/MESSENGER plugins."""

    def __init__(self):
        self.tag  = "NOTIFICATIONS"
        self.desc = "Sistema di notifiche per eventi Hecos."
        self.slash_commands = [
            {
                "id": "notify",
                "aliases": ["/notify"],
                "description": "Manage notifications: list rules, add/remove destinations, bind events, or send ad-hoc alerts.",
                "usage": "/notify [list rules | bind <event> to <dest> | add <name> <uri> | send <subject>]",
                "example": "/notify list rules",
                "icon": "🔔",
                "method": "get_status",
                "args_schema": {},
                "requires_args": False,
            },
            {
                "id": "alert",
                "aliases": ["/alert"],
                "description": "Send an immediate notification to all configured destinations.",
                "usage": "/alert <message>",
                "example": "/alert System backup completed!",
                "icon": "🔔",
                "method": "send_notification",
                "args_schema": {"subject": "str", "message": "str"},
                "requires_args": True,
            }
        ]

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _load_cfg(self) -> dict:
        from .config import load_config
        return load_config()

    def _save_cfg(self, cfg: dict) -> bool:
        from .config import save_config
        return save_config(cfg)

    def _valid_events(self) -> list:
        return [e.value for e in SystemEvent]

    # ── LLM Tools ─────────────────────────────────────────────────────────────

    def get_status(self) -> str:
        """Returns the current status of the Notifications Center."""
        cfg = self._load_cfg()
        n_destinations = len(cfg.get("destinations", {}))
        n_events_active = sum(1 for v in cfg.get("rules", {}).values() if v)
        return (
            f"[NOTIFICATIONS] Status: ACTIVE. "
            f"Destinations: {n_destinations}. "
            f"Events with rules: {n_events_active}/{len(cfg.get('rules', {}))}."
        )

    def list_destinations(self) -> str:
        """Lists all currently configured notification destinations."""
        cfg = self._load_cfg()
        dests = cfg.get("destinations", {})
        if not dests:
            return "📭 No destinations configured. Use add_destination to create one."
        lines = []
        for name, uri in dests.items():
            lines.append(f"  • {name} → {uri}")
        return f"📋 Destinations ({len(dests)}):\n" + "\n".join(lines)

    def add_destination(self, name: str, uri: str) -> str:
        """Adds a new notification destination.
        
        Args:
            name: Friendly name for the destination (e.g. 'admin_email').
            uri: Destination URI. Formats:
                 - MAIL:user@example.com
                 - CONTACT:<uuid>
                 - MESSENGER:Telegram:@username
        """
        if not name or not uri:
            return "⚠️ Both 'name' and 'uri' are required."
        name = name.strip().replace(" ", "_").lower()
        cfg = self._load_cfg()
        dests = cfg.setdefault("destinations", {})
        if name in dests:
            return f"⚠️ Destination '{name}' already exists with URI: {dests[name]}. Remove it first to change."
        dests[name] = uri.strip()
        if self._save_cfg(cfg):
            return f"✅ Destination '{name}' added → {uri}"
        return "⚠️ Failed to save configuration."

    def remove_destination(self, name: str) -> str:
        """Removes a notification destination by name.
        
        Args:
            name: The name of the destination to remove.
        """
        if not name:
            return "⚠️ Destination name is required."
        cfg = self._load_cfg()
        dests = cfg.get("destinations", {})
        if name not in dests:
            return f"⚠️ Destination '{name}' not found. Available: {', '.join(dests.keys()) or 'none'}"
        del dests[name]
        # Also remove from any rules that reference it
        rules = cfg.get("rules", {})
        removed_from = []
        for evt, dest_list in rules.items():
            if name in dest_list:
                dest_list.remove(name)
                removed_from.append(evt)
        if self._save_cfg(cfg):
            msg = f"✅ Destination '{name}' removed."
            if removed_from:
                msg += f" Also unbound from events: {', '.join(removed_from)}."
            return msg
        return "⚠️ Failed to save configuration."

    def list_rules(self) -> str:
        """Lists all system events and which destinations are bound to each."""
        cfg = self._load_cfg()
        rules = cfg.get("rules", {})
        dests = cfg.get("destinations", {})
        if not rules:
            return "📭 No event rules configured."
        lines = []
        for evt, dest_keys in sorted(rules.items()):
            if dest_keys:
                dest_names = ", ".join(dest_keys)
                lines.append(f"  🔔 {evt} → [{dest_names}]")
            else:
                lines.append(f"  🔕 {evt} → (no destinations)")
        avail = ", ".join(dests.keys()) if dests else "none"
        return f"📋 Event Rules:\n" + "\n".join(lines) + f"\n\nAvailable destinations: {avail}"

    def bind_event_destination(self, event: str, destination_name: str) -> str:
        """Binds a destination to a system event, so notifications for that event are sent there.
        
        Args:
            event: The event type string (e.g. 'system_boot', 'flow_completed').
            destination_name: The name of an existing destination.
        """
        if not event or not destination_name:
            return "⚠️ Both 'event' and 'destination_name' are required."
        cfg = self._load_cfg()
        rules = cfg.get("rules", {})
        dests = cfg.get("destinations", {})
        valid = self._valid_events()
        if event not in valid and event not in rules:
            return f"⚠️ Unknown event '{event}'. Valid events: {', '.join(valid)}"
        if destination_name not in dests:
            return f"⚠️ Destination '{destination_name}' not found. Available: {', '.join(dests.keys()) or 'none'}"
        event_dests = rules.setdefault(event, [])
        if destination_name in event_dests:
            return f"ℹ️ Destination '{destination_name}' is already bound to '{event}'."
        event_dests.append(destination_name)
        if self._save_cfg(cfg):
            return f"✅ Destination '{destination_name}' bound to event '{event}'."
        return "⚠️ Failed to save configuration."

    def unbind_event_destination(self, event: str, destination_name: str) -> str:
        """Removes a destination from a system event.
        
        Args:
            event: The event type string (e.g. 'system_boot').
            destination_name: The destination name to unbind.
        """
        if not event or not destination_name:
            return "⚠️ Both 'event' and 'destination_name' are required."
        cfg = self._load_cfg()
        rules = cfg.get("rules", {})
        if event not in rules:
            return f"⚠️ Event '{event}' not found in rules."
        if destination_name not in rules[event]:
            return f"⚠️ Destination '{destination_name}' is not bound to '{event}'."
        rules[event].remove(destination_name)
        if self._save_cfg(cfg):
            return f"✅ Destination '{destination_name}' unbound from event '{event}'."
        return "⚠️ Failed to save configuration."

    def set_event_template(self, event: str, template_id: str = "", variables: str = "") -> str:
        """Configures an HTML template and its variables for a given event.
        
        Args:
            event: The event type string (e.g. 'system_boot').
            template_id: UUID of the template to use. Pass empty string to clear.
            variables: JSON string of key-value pairs for template variables (e.g. '{"subject":"Hello","message":"World"}').
        """
        import json as _json
        if not event:
            return "⚠️ Event name is required."
        cfg = self._load_cfg()
        valid = self._valid_events()
        if event not in valid:
            return f"⚠️ Unknown event '{event}'. Valid events: {', '.join(valid)}"
        templates = cfg.setdefault("event_templates", {})
        tpl_data = templates.setdefault(event, {"template_id": "", "variables": {}})
        if not isinstance(tpl_data, dict):
            tpl_data = {"template_id": str(tpl_data), "variables": {}}
            templates[event] = tpl_data
        tpl_data["template_id"] = template_id or ""
        if variables:
            try:
                parsed = _json.loads(variables) if isinstance(variables, str) else variables
                if isinstance(parsed, dict):
                    tpl_data["variables"] = parsed
            except _json.JSONDecodeError:
                return f"⚠️ Invalid JSON for variables: {variables}"
        if self._save_cfg(cfg):
            return f"✅ Template for event '{event}' set to '{template_id or '(none)'}' with {len(tpl_data.get('variables', {}))} variables."
        return "⚠️ Failed to save configuration."

    def send_notification(self, subject: str, message: str, destination: str = "", template_id: str = "") -> str:
        """Sends an ad-hoc notification immediately.
        
        Args:
            subject: Notification subject line.
            message: Notification body text.
            destination: Optional destination URI (e.g. 'MAIL:user@example.com'). If omitted, sends to all configured destinations.
            template_id: Optional template UUID to render the message with.
        """
        if not subject or not message:
            return "⚠️ Both 'subject' and 'message' are required."
        dest_list = None
        if destination:
            dest_list = [d.strip() for d in destination.split(",") if d.strip()]
        try:
            notify(
                event="custom",
                subject=subject,
                message=message,
                template_id=template_id or None,
                destinations=dest_list
            )
            dest_info = f"to {destination}" if destination else "to all configured destinations"
            return f"📨 Notification dispatched {dest_info}. Subject: '{subject}'"
        except Exception as e:
            return f"⚠️ Error dispatching notification: {e}"


tools = NotificationsTools()


def on_load(full_cfg: dict):
    """
    Hook called by the HPM Loader when the plugin is loaded.
    Registers a global notify() hook so other HPM packages can call it
    without creating a hard import dependency on this plugin.
    """
    try:
        import sys
        # Expose notify() as a lightweight callable accessible from any module.
        # Usage: sys.hecos_notify(event_str, subject, message)
        sys.hecos_notify = notify
        sys.hecos_system_event = SystemEvent
        logger.info("[NOTIFICATIONS] Plugin loaded. Global notify hook registered on sys.hecos_notify.")

        # Pre-warm child plugins (MAIL/MESSENGER) to prevent lazy-load races
        # during the first background dispatch.
        # Destinations can be direct (MAIL:addr) or indirect (CONTACT:uuid),
        # so we always pre-warm MAIL and MESSENGER if any destination exists.
        try:
            from hecos.core.system.module_state import get_plugin_module
            from .config import load_config
            ntf_cfg = load_config()
            destinations = ntf_cfg.get("destinations", {})
            
            if destinations:
                # Always pre-warm MAIL and MESSENGER — CONTACT: URIs resolve
                # to one of these at dispatch time, so both must be ready.
                for ptag in ("MAIL", "MESSENGER"):
                    logger.info(f"[NOTIFICATIONS] Pre-warming plugin '{ptag}' at boot...")
                    mod = get_plugin_module(ptag)
                    if mod and hasattr(mod, "tools"):
                        logger.info(f"[NOTIFICATIONS] Plugin '{ptag}' is READY.")
                    else:
                        logger.debug(f"[NOTIFICATIONS] Plugin '{ptag}' could not be loaded (may not be installed).")
        except Exception as e_warm:
            logger.warning(f"[NOTIFICATIONS] Failed to pre-warm child plugins: {e_warm}")

    except Exception as e:
        logger.warning(f"[NOTIFICATIONS] on_load error: {e}")

