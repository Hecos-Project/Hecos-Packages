import threading
from hecos.core.logging import logger
from hecos.core.system.module_state import get_plugin_module
from .event_types import SystemEvent
from .config import load_config


def _dispatch_async(event_type_str: str, subject: str, message: str, override_template_id: str = None, override_variables: dict = None, override_destinations: list = None, **kwargs):
    """Dispatch notification in a separate thread (fire & forget)."""
    try:
        logger.info(f"[NOTIFICATIONS] _dispatch_async ENTERED: event='{event_type_str}', subject='{subject}', override_dests={override_destinations}")
        _dispatch_async_inner(event_type_str, subject, message, override_template_id, override_variables, override_destinations, sender_accounts=kwargs.get("sender_accounts"))
    except Exception as e:
        logger.error(f"[NOTIFICATIONS] _dispatch_async CRASHED: {e}")
        import traceback
        logger.error(f"[NOTIFICATIONS] Traceback: {traceback.format_exc()}")


def _dispatch_async_inner(event_type_str: str, subject: str, message: str, override_template_id: str = None, override_variables: dict = None, override_destinations: list = None, sender_accounts: list = None):
    """Inner dispatch logic. sender_accounts is a list of account IDs to use for MAIL (None = use config default)."""
    cfg = load_config()

    if override_destinations:
        target_uris = override_destinations
        logger.info(f"[NOTIFICATIONS] Using override destinations: {target_uris}")
    else:
        rules = cfg.get("rules", {})
        destinations = cfg.get("destinations", {})
        target_dest_keys = rules.get(event_type_str, [])
        if not target_dest_keys:
            logger.info(f"[NOTIFICATIONS] No rules configured for event '{event_type_str}' — notification dropped.")
            return
        
        target_uris = []
        for dest_key in target_dest_keys:
            uri = destinations.get(dest_key)
            if uri:
                target_uris.append(uri)
            else:
                logger.warning(f"[NOTIFICATIONS] Destination key '{dest_key}' not found in destinations.")

    # Render Template if configured
    event_templates = cfg.get("event_templates", {})
    event_tpl_config = event_templates.get(event_type_str)
    config_template_id = None
    config_variables = {}

    # Resolve sender_accounts: prefer override, then per-event config, then global config
    if not sender_accounts:
        if isinstance(event_tpl_config, dict):
            config_template_id = event_tpl_config.get("template_id")
            config_variables = event_tpl_config.get("variables", {})
            # per-event accounts list (new format) or legacy single account
            per_event_accounts = event_tpl_config.get("sender_accounts") or ()
            if isinstance(per_event_accounts, str):
                per_event_accounts = [per_event_accounts] if per_event_accounts else []
            sender_accounts = list(per_event_accounts) or None
        elif isinstance(event_tpl_config, str):
            config_template_id = event_tpl_config

    if not sender_accounts:
        # Fall back to global default_mail_accounts list
        global_accounts = cfg.get("default_mail_accounts") or cfg.get("default_mail_account")
        if isinstance(global_accounts, str):
            sender_accounts = [global_accounts] if global_accounts else [None]
        elif isinstance(global_accounts, list):
            sender_accounts = global_accounts or [None]
        else:
            sender_accounts = [None]  # use plugin's own default account

    template_id = override_template_id or config_template_id
    
    mail_subject = subject
    mail_body = message
    
    if template_id:
        try:
            from hecos.hpm.libraries.templates import store as tpl_store
            vars_dict = {"subject": subject, "message": message, "event": event_type_str}
            vars_dict.update(config_variables)
            
            if override_variables:
                vars_dict.update(override_variables)
                
            rendered = tpl_store.render_template(template_id, variables=vars_dict)
            if rendered:
                mail_subject = rendered.get("subject") or subject
                mail_body = rendered.get("body_html") or rendered.get("body_text") or message
        except Exception as e:
            logger.error(f"[NOTIFICATIONS] Template render error for '{template_id}': {e}")


    for target_uri in target_uris:


        if target_uri.startswith("CONTACT:"):
            contact_id = target_uri.split(":", 1)[1].strip()
            logger.info(f"[NOTIFICATIONS] Resolving CONTACT:{contact_id}...")
            try:
                from hecos.hpm.contacts import store as contact_store
                contact = contact_store.get_by_id(contact_id)
                if not contact:
                    logger.warning(f"[NOTIFICATIONS] Contact '{contact_id}' not found in database.")
                    continue
                fields = contact.get("fields", [])
                emails = [f for f in fields if f.get("field_type") == "email"]
                phones = [f for f in fields if f.get("field_type") == "phone"]
                
                primary_email = next((e for e in emails if e.get("is_primary") == 1), emails[0] if emails else None)
                primary_phone = next((p for p in phones if p.get("is_primary") == 1), phones[0] if phones else None)
                
                if primary_email:
                    target_uri = f"MAIL:{primary_email['value']}"
                    logger.info(f"[NOTIFICATIONS] Contact resolved to {target_uri}")
                elif primary_phone:
                    target_uri = f"MESSENGER:Telegram:{primary_phone['value']}"
                    logger.info(f"[NOTIFICATIONS] Contact resolved to {target_uri}")
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
        for attempt in range(6):
            plugin = get_plugin_module(plugin_tag)
            if plugin and hasattr(plugin, "tools"):
                break
            if attempt < 5:
                import time
                if attempt == 0:
                    logger.info(f"[NOTIFICATIONS] Plugin '{plugin_tag}' is still waking up, waiting...")
                else:
                    logger.debug(f"[NOTIFICATIONS] Plugin '{plugin_tag}' not ready yet, retrying ({attempt+1}/6)...")
                time.sleep(0.5)

        if not plugin or not hasattr(plugin, "tools"):
            logger.error(f"[NOTIFICATIONS] Plugin '{plugin_tag}' failed to initialize after retries. Cannot send to '{target_uri}'.")
            continue

        try:
            from .history import log_notification
            
            if plugin_tag == "MAIL":
                if hasattr(plugin.tools, "send_email"):
                    is_html = "<html" in mail_body.lower() or "<body" in mail_body.lower() or "<!doctype html" in mail_body.lower()
                    # Send once per selected account
                    for acc_id in (sender_accounts or [None]):
                        res = plugin.tools.send_email(to=target_address, subject=mail_subject, body=mail_body, is_html=is_html, account_id=acc_id or None)
                        logger.info(f"[NOTIFICATIONS] Sent '{event_type_str}' via MAIL to {target_address} from account '{acc_id or 'default'}': {res}")
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


def notify(event, subject: str, message: str, template_id: str = None, variables: dict = None, destinations: list = None, sender_accounts: list = None):
    """
    Public entry point for emitting a notification.

    :param event: Event type (SystemEvent enum or string).
    :param subject: Short notification title.
    :param message: Notification body.
    :param template_id: Optional UUID of a template to use, overriding the event's default.
    :param variables: Optional dict of variables to interpolate into the template.
    :param destinations: Optional list of destination URIs (e.g., ["MAIL:admin@example.com"]) to override event rules.
    :param sender_accounts: Optional list of mail account IDs to send from (multi-account support).
    """
    event_type_str = event.value if isinstance(event, SystemEvent) else str(event)
    logger.info(f"[NOTIFICATIONS] notify() called: event='{event_type_str}', subject='{subject}', dests={destinations}")

    t = threading.Thread(
        target=_dispatch_async,
        args=(event_type_str, subject, message, template_id, variables, destinations),
        kwargs={"sender_accounts": sender_accounts},
        daemon=True,
        name=f"NotifyThread_{event_type_str}"
    )
    t.start()
    logger.info(f"[NOTIFICATIONS] notify() thread started: {t.name}")
