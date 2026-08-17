import threading
from hecos.core.logging import logger
from hecos.core.system.module_state import get_plugin_module
from .event_types import SystemEvent
from .config import load_config


def _dispatch_async(event_type_str: str, subject: str, message: str):
    """Dispatch notification in a separate thread (fire & forget)."""
    cfg = load_config()

    rules = cfg.get("rules", {})
    destinations = cfg.get("destinations", {})


    target_dest_keys = rules.get(event_type_str, [])
    if not target_dest_keys:
        return

    # Render Template if configured
    event_templates = cfg.get("event_templates", {})
    template_id = event_templates.get(event_type_str)
    
    mail_subject = subject
    mail_body = message
    
    if template_id:
        try:
            from hecos.hpm.libraries.templates import store as tpl_store
            rendered = tpl_store.render_template(template_id, variables={"subject": subject, "message": message, "event": event_type_str})
            if rendered:
                mail_subject = rendered.get("subject") or subject
                mail_body = rendered.get("body_html") or rendered.get("body_text") or message
        except Exception as e:
            logger.error(f"[NOTIFICATIONS] Template render error for '{template_id}': {e}")


    for dest_key in target_dest_keys:
        target_uri = destinations.get(dest_key)
        if not target_uri:
            logger.warning(f"[NOTIFICATIONS] Destination key '{dest_key}' not found in destinations.")
            continue


        if target_uri.startswith("CONTACT:"):
            contact_id = target_uri.split(":", 1)[1].strip()
            try:
                from hecos.hpm.contacts import store as contact_store
                contact = contact_store.get_by_id(contact_id)
                if not contact:
                    logger.warning(f"[NOTIFICATIONS] Contact '{contact_id}' not found.")
                    continue
                fields = contact.get("fields", [])
                emails = [f for f in fields if f.get("field_type") == "email"]
                phones = [f for f in fields if f.get("field_type") == "phone"]
                
                primary_email = next((e for e in emails if e.get("is_primary") == 1), emails[0] if emails else None)
                primary_phone = next((p for p in phones if p.get("is_primary") == 1), phones[0] if phones else None)
                
                if primary_email:
                    target_uri = f"MAIL:{primary_email['value']}"
                elif primary_phone:
                    target_uri = f"MESSENGER:Telegram:{primary_phone['value']}"
                else:
                    logger.warning(f"[NOTIFICATIONS] Contact '{contact_id}' has no email or phone.")
                    continue
            except Exception as e:
                logger.error(f"[NOTIFICATIONS] Error resolving contact: {e}")
                continue

        # Parse URI: "PLUGIN_TAG:address" — e.g. MAIL:admin@example.com

        if ":" not in target_uri:
            logger.warning(f"[NOTIFICATIONS] Invalid destination format: '{target_uri}'. Expected PLUGIN_TAG:address.")
            continue

        plugin_tag, target_address = target_uri.split(":", 1)
        plugin_tag = plugin_tag.upper().strip()
        target_address = target_address.strip()

        # Retry loop: handles race condition where another thread is simultaneously
        # lazy-loading the same plugin (KeyError on del _lazy_plugins_paths[tag]).
        plugin = None
        for attempt in range(3):
            plugin = get_plugin_module(plugin_tag)
            if plugin and hasattr(plugin, "tools"):
                break
            if attempt < 2:
                import time
                logger.debug(f"[NOTIFICATIONS] Plugin '{plugin_tag}' not ready yet, retrying ({attempt+1}/3)...")
                time.sleep(0.5)

        if not plugin or not hasattr(plugin, "tools"):
            logger.warning(f"[NOTIFICATIONS] Plugin '{plugin_tag}' not found or inactive. Cannot send to '{target_uri}'.")
            continue

        try:
            from .history import log_notification
            
            if plugin_tag == "MAIL":
                if hasattr(plugin.tools, "send_email"):
                    is_html = "<html" in mail_body.lower() or "<body" in mail_body.lower() or "<!doctype html" in mail_body.lower()
                    res = plugin.tools.send_email(to=target_address, subject=mail_subject, body=mail_body, is_html=is_html)
                    logger.info(f"[NOTIFICATIONS] Sent '{event_type_str}' via MAIL to {target_address}: {res}")
                    log_notification(event_type_str, target_address, mail_subject, "SUCCESS" if res else "ERROR", None if res else "Plugin returned false")
                else:
                    logger.error("[NOTIFICATIONS] MAIL plugin does not have send_email tool.")
                    log_notification(event_type_str, target_address, mail_subject, "ERROR", "MAIL plugin does not have send_email tool")

            elif plugin_tag == "MESSENGER":
                if hasattr(plugin.tools, "send_message"):
                    # Format: MESSENGER:Telegram:@Username
                    if ":" in target_address:
                        platform, recipient = target_address.split(":", 1)
                    else:
                        platform = "Telegram" # fallback default
                        recipient = target_address
                    res = plugin.tools.send_message(recipient=recipient, message=mail_body, platform=platform)
                    logger.info(f"[NOTIFICATIONS] Sent '{event_type_str}' via MESSENGER ({platform}) to {recipient}: {res}")
                    log_notification(event_type_str, target_address, mail_subject, "SUCCESS" if res else "ERROR", None if res else "Plugin returned false")
                else:
                    logger.error("[NOTIFICATIONS] MESSENGER plugin does not have send_message tool.")
                    log_notification(event_type_str, target_address, mail_subject, "ERROR", "MESSENGER plugin does not have send_message tool")

            else:
                logger.warning(f"[NOTIFICATIONS] Unknown plugin tag '{plugin_tag}'. Cannot dispatch.")
                log_notification(event_type_str, target_address, mail_subject, "ERROR", f"Unknown plugin tag: {plugin_tag}")

        except Exception as e:
            logger.error(f"[NOTIFICATIONS] Error sending to '{target_uri}': {e}")
            from .history import log_notification
            log_notification(event_type_str, target_uri, mail_subject, "ERROR", str(e))


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
