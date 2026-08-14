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
        self.desc = "Sistema di notifiche per eventi Hecos. Nessun tool LLM esposto."

    def get_status(self) -> str:
        """Returns the current status of the Notifications Center."""
        from .config import load_config
        cfg = load_config()
        enabled = cfg.get("enabled", False)
        n_destinations = len(cfg.get("destinations", {}))
        return (
            f"[NOTIFICATIONS] Status: {'ENABLED' if enabled else 'DISABLED'}. "
            f"Destinations configured: {n_destinations}."
        )


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
    except Exception as e:
        logger.warning(f"[NOTIFICATIONS] on_load error: {e}")
