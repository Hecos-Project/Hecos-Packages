import threading
from hecos.core.logging import logger
from hecos.core.system.module_state import get_plugin_module
from .event_types import SystemEvent
from .config import load_config


def _dispatch_async(event_type_str: str, subject: str, message: str):
    """Dispatch notification in a separate thread (fire & forget)."""
    cfg = load_config()

    if not cfg.get("enabled", False):
        return

    rules = cfg.get("rules", {})
    destinations = cfg.get("destinations", {})

    target_dest_keys = rules.get(event_type_str, [])
    if not target_dest_keys:
        return

    for dest_key in target_dest_keys:
        target_uri = destinations.get(dest_key)
        if not target_uri:
            logger.warning(f"[NOTIFICATIONS] Destination key '{dest_key}' not found in destinations.")
            continue

        # Parse URI: "PLUGIN_TAG:address" — e.g. MAIL:admin@example.com
        if ":" not in target_uri:
            logger.warning(f"[NOTIFICATIONS] Invalid destination format: '{target_uri}'. Expected PLUGIN_TAG:address.")
            continue

        plugin_tag, target_address = target_uri.split(":", 1)
        plugin_tag = plugin_tag.upper().strip()
        target_address = target_address.strip()

        plugin = get_plugin_module(plugin_tag)
        if not plugin or not hasattr(plugin, "tools"):
            logger.warning(f"[NOTIFICATIONS] Plugin '{plugin_tag}' not found or inactive. Cannot send to '{target_uri}'.")
            continue

        try:
            if plugin_tag == "MAIL":
                if hasattr(plugin.tools, "send_email"):
                    res = plugin.tools.send_email(to=target_address, subject=subject, body=message)
                    logger.info(f"[NOTIFICATIONS] Sent '{event_type_str}' via MAIL to {target_address}: {res}")
                else:
                    logger.error("[NOTIFICATIONS] MAIL plugin does not have send_email tool.")

            elif plugin_tag == "MESSENGER":
                if hasattr(plugin.tools, "send_message"):
                    # Format: MESSENGER:Telegram:@Username
                    if ":" in target_address:
                        platform, recipient = target_address.split(":", 1)
                    else:
                        platform = None
                        recipient = target_address
                    full_text = f"*{subject}*\n\n{message}"
                    res = plugin.tools.send_message(to=recipient, text=full_text, platform=platform)
                    logger.info(f"[NOTIFICATIONS] Sent '{event_type_str}' via MESSENGER to {target_address}: {res}")
                else:
                    logger.error("[NOTIFICATIONS] MESSENGER plugin does not have send_message tool.")

            else:
                logger.warning(f"[NOTIFICATIONS] Plugin tag '{plugin_tag}' is not supported for notifications.")

        except Exception as e:
            logger.error(f"[NOTIFICATIONS] Error sending to '{target_uri}' via '{plugin_tag}': {e}")


def notify(event, subject: str, message: str):
    """
    Public entry point for emitting a notification.

    :param event: Event type (SystemEvent enum or string).
    :param subject: Short notification title.
    :param message: Notification body.
    """
    event_type_str = event.value if isinstance(event, SystemEvent) else str(event)

    t = threading.Thread(
        target=_dispatch_async,
        args=(event_type_str, subject, message),
        daemon=True,
        name=f"NotifyThread_{event_type_str}"
    )
    t.start()
