"""
MODULE: Messenger Plugin — Main Entry Point (v2.2 Modular Architecture)
DESCRIPTION: Thin facade exposing MessengerTools to the Hecos agent loop:
             - Smart contact & 15-minute follow-up resolution
             - Persona-aware Telegram multi-bot selection
             - Smart media & document resolution ([[IMG:...]], 'latest', magic-byte check)
             - Per-turn & 3-minute anti-duplicate / anti-burst protection
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from hecos.core.logging import logger

try:
    from hecos.core.i18n import translator
except ImportError:
    class _DummyTranslator:
        def t(self, key: str, **kwargs: Any) -> str:
            return kwargs.get("default", key)

    translator = _DummyTranslator()

from .core.inbound_router import InboundRouter
from .core.media_resolver import resolve_attachment_path, resolve_photo_path
from .core.registry import registry
from .core.resolver import resolve_target
from .core.session_memory import (
    check_burst_guard,
    record_outbound_attempt,
    record_verified_send,
)
from .core.templates_bridge import apply_message_template
from .messenger_config.config_manager import (
    MessengerConfig,
    get_config_obj,
    sync_routing_override_yaml,
)
from .providers import register_default_providers

register_default_providers(registry)
_inbound_router = InboundRouter(registry)


def _is_pre_dispatch_validation_error(msg: str) -> bool:
    """Returns True when a failure occurred before any network/browser dispatch took place."""
    low = (msg or "").lower()
    return any(
        tok in low
        for tok in (
            "not found in configuration",
            "not found. available enabled bots",
            "is disabled",
            "no recipient specified",
            "attachment file(s) not found",
            "invalid whatsapp phone number",
        )
    )


class MessengerTools:
    """Hecos Messenger LLM Tools — send messages, photos, and documents via WhatsApp and Telegram."""

    def __init__(self) -> None:
        self.tag = "MESSENGER"
        self.desc = "Send and receive messages, photos, and documents via WhatsApp and Telegram."
        self.status = "ONLINE"
        self._cfg: Optional[MessengerConfig] = None

    def _require_config(self) -> MessengerConfig:
        self._cfg = get_config_obj()
        return self._cfg

    def register_pre_callback(self, name: str, fn: Any) -> None:
        """Registers an inbound message pre-callback interceptor."""
        _inbound_router.register_pre_callback(name, fn)

    # ── Primary LLM Tools ─────────────────────────────────────────────────────

    def send_message(
        self,
        to: str = "",
        text: str = "",
        platform: Optional[str] = None,
        bot_name: Optional[str] = None,
        attachments: Optional[list[str]] = None,
        skip_default_template: bool = False,
        # Flexible fallback parameter names for local text-mode models
        name: Optional[str] = None,
        contact_id: Optional[str] = None,
        message: Optional[str] = None,
        is_app_open: bool = False,
    ) -> str:
        """
        Sends a text message (and optional file attachments) to a contact name or direct address
        on WhatsApp or Telegram. Automatically resolves contact names from Hecos Contacts.
        """
        cfg = self._require_config()
        effective_to = (to or name or contact_id or "").strip()
        effective_text = text if text else (message or "")

        if not effective_text and not attachments:
            return "❌ Message text cannot be empty."

        resolved_files: list[str] = []
        if attachments:
            for raw_att in attachments:
                apath, aerr = resolve_attachment_path(str(raw_att))
                if aerr or not apath:
                    return f"❌ {aerr}"
                resolved_files.append(apath)

        try:
            resolved = resolve_target(
                to=effective_to,
                platform=platform,
                root_cfg=cfg,
                bot_name=bot_name,
                reg=registry,
            )
        except ValueError as exc:
            return f"❌ {exc}"

        provider = registry.get(resolved.platform)
        if not provider:
            return f"❌ Provider '{resolved.platform}' is not registered."

        kind = "media" if resolved_files else "text"
        sig_key = ("|".join(resolved_files) + "|" + effective_text) if resolved_files else effective_text
        burst_block = check_burst_guard(resolved.platform, resolved.recipient, sig_key, kind=kind)
        if burst_block:
            logger.warning("MESSENGER", f"Blocked duplicate/burst [{resolved.platform}] {resolved.recipient}: {burst_block}")
            return burst_block

        pcfg = provider.get_provider_config(cfg)
        formatted_text = apply_message_template(
            platform=resolved.platform,
            text=effective_text,
            provider_cfg=pcfg,
            skip_default_template=skip_default_template,
        )

        logger.info(
            "MESSENGER",
            f"Dispatching → [{resolved.platform}] {resolved.recipient}"
            + (f" (contact: {resolved.contact_name})" if resolved.contact_name else "")
            + (f" (attachments: {len(resolved_files)})" if resolved_files else ""),
        )

        if resolved_files:
            res = provider.send_media(
                pcfg,
                resolved.recipient,
                file_paths=resolved_files,
                caption=formatted_text,
                bot_name=resolved.bot_name,
                contact_name=resolved.contact_name,
            )
        else:
            res = provider.send_text(
                pcfg,
                resolved.recipient,
                formatted_text,
                bot_name=resolved.bot_name,
                contact_name=resolved.contact_name,
            )

        if res.ok or not _is_pre_dispatch_validation_error(res.message):
            record_outbound_attempt(resolved.platform, res.recipient or resolved.recipient, sig_key, res.ok, kind=kind)

        if res.ok and getattr(cfg, "remember_last_channel", True):
            record_verified_send(
                platform=resolved.platform,
                recipient=res.recipient or resolved.recipient,
                contact_name=resolved.contact_name,
                raw_query=effective_to,
                bot_name=resolved.bot_name,
            )

        return res.format_for_agent()

    def send_photo(
        self,
        to: str = "",
        image_path: str = "",
        caption: str = "",
        platform: Optional[str] = None,
        bot_name: Optional[str] = None,
        file_path: str = "",
        path: str = "",
    ) -> str:
        """
        Sends a photo or image file (`[[IMG:filename]]`, `/api/images/...`, `'latest'`, or full path)
        to a contact or channel on Telegram or WhatsApp. Validates real binary image headers.
        """
        cfg = self._require_config()
        raw_img = (image_path or file_path or path or "latest").strip()

        resolved_img, img_err = resolve_photo_path(raw_img)
        if img_err or not resolved_img:
            return f"❌ {img_err}"

        try:
            resolved = resolve_target(
                to=to,
                platform=platform,
                root_cfg=cfg,
                bot_name=bot_name,
                reg=registry,
            )
        except ValueError as exc:
            return f"❌ {exc}"

        provider = registry.get(resolved.platform)
        if not provider:
            return f"❌ Provider '{resolved.platform}' is not registered."

        burst_block = check_burst_guard(resolved.platform, resolved.recipient, resolved_img, kind="media")
        if burst_block:
            logger.warning("MESSENGER", f"Blocked duplicate photo [{resolved.platform}] {resolved.recipient}: {burst_block}")
            return burst_block

        pcfg = provider.get_provider_config(cfg)
        formatted_caption = (
            apply_message_template(platform=resolved.platform, text=caption, provider_cfg=pcfg)
            if caption and caption.strip()
            else ""
        )

        res = provider.send_media(
            pcfg,
            resolved.recipient,
            file_paths=[resolved_img],
            caption=formatted_caption,
            bot_name=resolved.bot_name,
            contact_name=resolved.contact_name,
        )

        if res.ok or not _is_pre_dispatch_validation_error(res.message):
            record_outbound_attempt(resolved.platform, res.recipient or resolved.recipient, resolved_img, res.ok, kind="media")

        if res.ok and getattr(cfg, "remember_last_channel", True):
            record_verified_send(
                platform=resolved.platform,
                recipient=res.recipient or resolved.recipient,
                contact_name=resolved.contact_name,
                raw_query=to,
                bot_name=resolved.bot_name,
            )

        return res.format_for_agent()

    def send_document(
        self,
        to: str = "",
        file_path: str = "",
        caption: str = "",
        platform: Optional[str] = None,
        bot_name: Optional[str] = None,
        document_path: str = "",
        path: str = "",
    ) -> str:
        """
        Sends a document or file (PDF, HTML, DOCX, TXT, ZIP, audio, video) to a contact or channel
        on Telegram or WhatsApp.
        """
        cfg = self._require_config()
        raw_doc = (file_path or document_path or path or "").strip()

        resolved_doc, doc_err = resolve_attachment_path(raw_doc)
        if doc_err or not resolved_doc:
            return f"❌ {doc_err}"

        try:
            resolved = resolve_target(
                to=to,
                platform=platform,
                root_cfg=cfg,
                bot_name=bot_name,
                reg=registry,
            )
        except ValueError as exc:
            return f"❌ {exc}"

        provider = registry.get(resolved.platform)
        if not provider:
            return f"❌ Provider '{resolved.platform}' is not registered."

        burst_block = check_burst_guard(resolved.platform, resolved.recipient, resolved_doc, kind="media")
        if burst_block:
            return burst_block

        pcfg = provider.get_provider_config(cfg)
        formatted_doc_caption = (
            apply_message_template(platform=resolved.platform, text=caption, provider_cfg=pcfg)
            if caption and caption.strip()
            else ""
        )

        res = provider.send_media(
            pcfg,
            resolved.recipient,
            file_paths=[resolved_doc],
            caption=formatted_doc_caption,
            bot_name=resolved.bot_name,
            contact_name=resolved.contact_name,
            force_document=True,
        )

        if res.ok or not _is_pre_dispatch_validation_error(res.message):
            record_outbound_attempt(resolved.platform, res.recipient or resolved.recipient, resolved_doc, res.ok, kind="media")

        if res.ok and getattr(cfg, "remember_last_channel", True):
            record_verified_send(
                platform=resolved.platform,
                recipient=res.recipient or resolved.recipient,
                contact_name=resolved.contact_name,
                raw_query=to,
                bot_name=resolved.bot_name,
            )

        return res.format_for_agent()

    # Alias for local models guessing send_file
    send_file = send_document

    def list_accounts(self) -> str:
        """Lists all configured messaging providers, accounts, and active delivery methods."""
        cfg = self._require_config()
        title = translator.t("ext_messenger_accounts_title", default="Configured messaging accounts:")
        lines = [title + "\n"]
        for provider in registry.all():
            pcfg = provider.get_provider_config(cfg)
            lines.extend(provider.describe_accounts(pcfg))
        return "\n".join(lines)

    def check_connection(self, platform: Optional[str] = None) -> str:
        """Checks live connectivity and readiness of one or all messaging providers."""
        cfg = self._require_config()
        state_icons = {
            "ONLINE": "✅",
            "READY": "🟢",
            "DEGRADED": "🟡",
            "DISABLED": "⛔",
            "OFFLINE": "❌",
            "MISSING_DEP": "⚠️",
            "ERROR": "❌",
        }

        if platform:
            provider = registry.get(platform)
            if not provider:
                return f"❌ Unknown platform '{platform}'. Supported: {', '.join(registry.names())}."
            health = provider.check_health(provider.get_provider_config(cfg))
            icon = state_icons.get(health.state, "❓")
            method_str = f" [{health.method_used}]" if health.method_used else ""
            return f"{icon} **{provider.display_name}** ({health.state}){method_str}: {health.summary}"

        title = translator.t("ext_messenger_check_title", default="Connection status for messaging services:")
        lines = [title + "\n"]
        for provider in registry.all():
            health = provider.check_health(provider.get_provider_config(cfg))
            icon = state_icons.get(health.state, "❓")
            method_str = f" — _{health.method_used}_" if health.method_used else ""
            lines.append(f"{icon} **{provider.display_name}** (`{health.state}`){method_str}: {health.summary}")
        return "\n".join(lines)

    def resolve_contact_address(self, name: str, platform: Optional[str] = None) -> str:
        """Resolves a contact name from Hecos Contacts without sending a message."""
        cfg = self._require_config()
        try:
            resolved = resolve_target(to=f"contact:{name}", platform=platform, root_cfg=cfg, reg=registry)
            return (
                f"✅ Resolved '{name}' ({resolved.contact_name}) → "
                f"{resolved.platform} address: `{resolved.recipient}`"
            )
        except ValueError as exc:
            return f"⚠️ {exc}"

    def msg_command(self, args: str) -> str:
        """Slash command handler invoked via `/msg <target> <text>` or `/send <target> <text>`."""
        if not args or " " not in args.strip():
            return (
                "❌ Usage: `/msg <platform:recipient_or_contact> <message>`\n"
                "Examples:\n"
                "- `/msg whatsapp:Rowena Hello!`\n"
                "- `/msg whatsapp:+393331234567 Hello!`\n"
                "- `/msg telegram:Urania:1292135505 Hello!`"
            )
        target, body = args.strip().split(" ", 1)
        return self.send_message(to=target.strip(), text=body.strip())

    # ── Compatibility Aliases for Local Text-Mode LLMs ────────────────────────

    def send_whatsapp_to_contact(
        self,
        to: str = "",
        text: str = "",
        name: str = "",
        contact_id: str = "",
        query: str = "",
        id: str = "",
        message: str = "",
    ) -> str:
        target = (to or name or contact_id or query or id or "").strip()
        body = text if text else (message or "")
        return self.send_message(to=target, text=body, platform="whatsapp")

    def send_telegram_to_contact(
        self,
        to: str = "",
        text: str = "",
        name: str = "",
        contact_id: str = "",
        message: str = "",
        bot_name: Optional[str] = None,
    ) -> str:
        target = (to or name or contact_id or "").strip()
        body = text if text else (message or "")
        return self.send_message(to=target, text=body, platform="telegram", bot_name=bot_name)

    def send_to_contact(
        self,
        name: str = "",
        message: str = "",
        platform: Optional[str] = None,
        to: str = "",
        text: str = "",
        bot_name: Optional[str] = None,
        attachments: Optional[list[str]] = None,
    ) -> str:
        target = (name or to or "").strip()
        body = message if message else (text or "")
        return self.send_message(
            to=target,
            text=body,
            platform=platform,
            bot_name=bot_name,
            attachments=attachments,
        )


# ── Singleton & Plugin Lifecycle Hooks ────────────────────────────────────────

tools = MessengerTools()


def info() -> dict[str, str]:
    return {"tag": tools.tag, "desc": tools.desc}


def status() -> str:
    return tools.status


def on_load(config: Optional[dict[str, Any]] = None) -> None:
    """Initializes or hot-reloads the Messenger plugin, routing_override.yaml, and active listeners."""
    try:
        from hecos.core.i18n.translator import register_package_locales
        locales_dir = str(Path(__file__).parent / "locales")
        register_package_locales(locales_dir)
    except Exception:
        pass

    register_default_providers(registry)
    tools._cfg = get_config_obj()
    cfg = tools._cfg
    sync_routing_override_yaml(cfg)

    enabled = registry.enabled_providers(cfg)
    if not enabled:
        for prov in registry.all():
            prov.stop_listener()
        tools.status = "DEGRADED"
        logger.info("MESSENGER", "Plugin loaded — no providers currently enabled.")
        return

    active_names = [p.name for p in enabled]
    logger.info("MESSENGER", f"Plugin loaded — active providers: {', '.join(active_names)}")
    tools.status = "ONLINE"

    def _inbound_cb(
        platform: str,
        chat_id: str,
        text: str,
        account_name: Optional[str] = None,
        is_admin: bool = False,
    ) -> None:
        _inbound_router.handle_incoming(
            platform=platform,
            chat_id=chat_id,
            text=text,
            account_name=account_name,
            is_admin=is_admin,
            root_cfg=tools._require_config(),
        )

    for prov in registry.all():
        if prov.is_enabled(cfg):
            try:
                prov.start_listener(prov.get_provider_config(cfg), inbound_callback=_inbound_cb)
            except Exception as exc:
                logger.error("MESSENGER", f"Failed to start listener for '{prov.name}': {exc}")
        else:
            prov.stop_listener()


def on_unload() -> None:
    """Stops all background listeners cleanly when the plugin is unloaded."""
    logger.info("MESSENGER", "Plugin unloading — stopping all active listeners...")
    for prov in registry.all():
        try:
            prov.stop_listener()
        except Exception as exc:
            logger.error("MESSENGER", f"Error stopping listener '{prov.name}': {exc}")
    tools.status = "OFFLINE"
