"""
MODULE: Messenger Plugin — Dispatcher
DESCRIPTION: Routes a send_message or check_connection call to the correct
             provider adapter based on the 'to' address or the 'platform' arg.
             Address format: 'platform:recipient'  (e.g. 'telegram:@hecos')
"""

from __future__ import annotations
from hecos.core.logging import logger

PLATFORM_PREFIXES = ("telegram", "whatsapp", "discord")


def parse_target(to: str, platform: str = None) -> tuple[str, str]:
    """
    Parse the target string and return (platform, recipient).

    Accepts:
        - 'contact:Antonio Meloni' → resolves through contacts store
        - 'telegram:@username'     → ('telegram', '@username')
        - 'discord:#general'       → ('discord', '#general')
        - '+393331234567'          → if platform='whatsapp' → ('whatsapp', '+393331234567')
    """
    to_lower = to.strip().lower()
    if to_lower.startswith("contact:"):
        contact_name = to.split(":", 1)[1].strip()
        if not platform:
            raise ValueError("Platform must be specified when using 'contact:' prefix.")
        
        try:
            from hecos.hpm.contacts import store
            resolution = store.resolve_for_platform(contact_name, platform)
            if not resolution:
                raise ValueError(f"No valid {platform} address found for contact '{contact_name}'.")
            return platform.lower(), resolution["address"]
        except ImportError:
            raise ValueError("Contacts plugin is not available. Cannot resolve 'contact:' prefix.")
            
    if ":" in to:
        prefix, _, recipient = to.partition(":")
        prefix = prefix.strip().lower()
        if prefix in PLATFORM_PREFIXES:
            return prefix, recipient.strip()

    # No prefix — use explicit platform or raise
    if platform and platform.lower() in PLATFORM_PREFIXES:
        return platform.lower(), to.strip()

    raise ValueError(
        f"Cannot determine platform from '{to}'. "
        f"Use a prefix like 'telegram:@username', 'contact:Name', or pass platform= argument."
    )


def dispatch_send(platform: str, recipient: str, text: str, config,
                  is_app_open: bool = False,
                  template_id: str = "",
                  template_vars: dict = None,
                  attachments: list = None) -> str:
    """
    Send a message via the appropriate adapter.

    If *template_id* is provided, the template is rendered first and its
    body_text is used as the message content.

    :returns: Result string from the adapter.
    """
    # ── Template rendering (optional) ─────────────────────────────────────────
    if template_id:
        try:
            from hecos.hpm.templates import store as tpl_store
            rendered = tpl_store.render_template(template_id, template_vars or {})
            # Messenger channels use plain text; fall back to body_html stripped if needed
            text = rendered.get("body_text") or rendered.get("body_html") or text
        except KeyError:
            return f"❌ Template '{template_id}' not found."
        except Exception as e:
            logger.warning("MESSENGER", f"Template render error: {e}")

    logger.info("MESSENGER", f"Dispatching send → [{platform}] {recipient} (Attachments: {len(attachments or [])})")

    if platform == "telegram":
        from .adapters import telegram as tg
        bot_name = None
        if ":" in recipient:
            # Parse 'bot_name:chat_id' format
            parts = recipient.split(":", 1)
            bot_name = parts[0].strip()
            recipient = parts[1].strip()
            
        return tg.send(config.telegram, recipient, text, bot_name=bot_name)

    if platform == "whatsapp":
        from .adapters import whatsapp as wa
        return wa.send(config.whatsapp, recipient, text, is_app_open)

    if platform == "discord":
        from .adapters import discord as dc
        return dc.send(config.discord, recipient, text)

    return f"❌ Platform '{platform}' is not supported."



def dispatch_check(platform: str | None, config) -> dict[str, str]:
    """
    Check one or all providers.
    Returns a dict: { platform_name: status_string }
    """
    results = {}

    targets = [platform.lower()] if platform else list(PLATFORM_PREFIXES)

    for p in targets:
        try:
            if p == "telegram":
                from .adapters import telegram as tg
                results["telegram"] = tg.check(config.telegram)

            elif p == "whatsapp":
                from .adapters import whatsapp as wa
                results["whatsapp"] = wa.check(config.whatsapp)

            elif p == "discord":
                from .adapters import discord as dc
                results["discord"] = dc.check(config.discord)

        except Exception as exc:
            results[p] = f"ERROR: {exc}"

    return results
