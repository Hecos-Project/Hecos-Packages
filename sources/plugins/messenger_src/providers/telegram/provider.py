"""
Telegram Provider implementation for Hecos Messenger (v2.2).
Features:
  - Active polling event-loop reuse for instant outbound sends
  - Persona/Soul-aware bot auto-selection (e.g. talking to Urania -> uses 'Urania' bot;
    talking to Hecos -> uses 'hecos' bot) + fuzzy/username bot matching
  - Automatic photo -> document fallback if Telegram rejects photo dimensions/encoding
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Optional

from hecos.core.logging import logger
from ...core.base_provider import BaseMessengerProvider, InboundCallback, ProviderHealth, SendResult
from .config import TelegramBotConfig, TelegramConfig
from . import listener


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}


def _normalize_ident(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").strip().lower()).strip()


def _detect_active_persona_tokens() -> str:
    """
    Inspects the active Hecos session's Soul / Persona (e.g. 'Urania 9800 GP' vs 'Hecos')
    so outbound Telegram messages automatically use the bot matching the persona speaking.
    """
    parts: list[str] = []
    session_id = None
    try:
        from hecos.core.agent.trace_session import get_active_session
        sess = get_active_session()
        if sess:
            session_id = sess.session_id
    except Exception:
        pass

    try:
        from hecos.core.global_presets import get_active_soul
        soul = get_active_soul(session_id or "global")
        if soul:
            if getattr(soul, "meta", None) and getattr(soul.meta, "name", ""):
                parts.append(str(soul.meta.name))
            if getattr(soul, "persona", None) and getattr(soul.persona, "soul_file", ""):
                parts.append(str(soul.persona.soul_file))
    except Exception:
        pass

    if session_id:
        try:
            from hecos.memory.session_config_db import get_session_config
            ov = get_session_config(session_id) or {}
            ai_ov = (ov.get("ai") or {}).get("active_personality")
            if ai_ov:
                parts.append(str(ai_ov))
        except Exception:
            pass

    return _normalize_ident(" ".join(parts))


class TelegramProvider(BaseMessengerProvider):
    name = "telegram"
    display_name = "Telegram"
    icon = "📨"
    supports_inbound = True
    supports_media = True

    def _match_bot_by_hint(
        self,
        enabled_bots: list[TelegramBotConfig],
        hint: str,
        active_states: dict[str, dict[str, Any]],
    ) -> Optional[TelegramBotConfig]:
        clean_hint = (hint or "").strip().lstrip("@")
        if not clean_hint:
            return None
        low_hint = clean_hint.lower()
        norm_hint = _normalize_ident(clean_hint)
        hint_words = set(norm_hint.split())

        # 1. Exact identifier or @username match
        for bot in enabled_bots:
            bname_low = bot.name.strip().lower()
            uname_low = str((active_states.get(bot.name) or {}).get("username") or "").strip().lower()
            if low_hint == bname_low or (uname_low and low_hint == uname_low):
                return bot

        # 2. Token / prefix match (e.g. 'Urania 9800' / 'Urania_9800' -> bot 'Urania')
        for bot in enabled_bots:
            bnorm = _normalize_ident(bot.name)
            if not bnorm or len(bnorm) < 3:
                continue
            if bnorm in hint_words or norm_hint.startswith(bnorm) or bnorm.startswith(norm_hint):
                return bot
            uname_norm = _normalize_ident(str((active_states.get(bot.name) or {}).get("username") or ""))
            if uname_norm and (norm_hint == uname_norm or norm_hint in uname_norm):
                return bot

        return None

    def _select_bot_config(
        self,
        cfg: TelegramConfig,
        bot_name: Optional[str] = None,
    ) -> TelegramBotConfig:
        if not cfg or not cfg.enabled or not cfg.bots:
            raise ValueError("Telegram provider is disabled or has no bots configured.")

        enabled_bots = [b for b in cfg.bots if b.enabled and b.bot_token]
        if not enabled_bots:
            raise ValueError("No enabled Telegram bots with a valid token were found.")

        active_states = listener.get_active_bot_states()

        # 1. Explicit or fuzzy bot_name passed by caller/LLM
        if bot_name and bot_name.strip():
            matched = self._match_bot_by_hint(enabled_bots, bot_name, active_states)
            if matched:
                return matched

            available_desc = ", ".join(
                f"'{b.name}'" + (f" (@{active_states[b.name]['username']})" if active_states.get(b.name, {}).get("username") else "")
                for b in enabled_bots
            )
            raise ValueError(
                f"Telegram bot '{bot_name}' not found. Available enabled bots: {available_desc}."
            )

        # 2. Automatic Persona/Soul matching when enabled (e.g. speaking with Urania -> 'Urania' bot)
        if getattr(cfg, "auto_match_persona_bot", True) and len(enabled_bots) > 1:
            persona_tokens = _detect_active_persona_tokens()
            if persona_tokens:
                matched_persona = self._match_bot_by_hint(enabled_bots, persona_tokens, active_states)
                if matched_persona:
                    logger.debug(
                        "MESSENGER/Telegram",
                        f"Auto-selected bot '{matched_persona.name}' matching active persona '{persona_tokens}'.",
                    )
                    return matched_persona

        # 3. Fallback to Primary bot, then first enabled bot
        for bot in enabled_bots:
            if bot.is_primary:
                return bot

        return enabled_bots[0]

    def _resolve_chat_id(self, bcfg: TelegramBotConfig, recipient: str) -> str:
        cleaned = (recipient or "").strip()
        if cleaned:
            return cleaned
        if bcfg.default_chat_id:
            return str(bcfg.default_chat_id).strip()
        raise ValueError(
            f"Telegram bot '{bcfg.name}': no recipient specified and no default_chat_id configured."
        )

    def _execute_bot_coro(
        self,
        bcfg: TelegramBotConfig,
        coro_fn: Any,
        timeout: float = 30.0,
    ) -> Any:
        """Executes `coro_fn(bot)` on the active listener loop if running, else via asyncio.run."""
        if not listener.is_ptb_installed():
            raise RuntimeError(
                "'python-telegram-bot' is not installed in Hecos Python environment."
            )

        try:
            handled, res = listener.run_on_active_bot_loop(bcfg.name, coro_fn, timeout=timeout)
            if handled:
                return res
        except Exception as loop_exc:
            err_low = str(loop_exc).lower()
            # Do not retry deterministic Telegram API rejections (bad chat_id, corrupt image, forbidden)
            if any(
                kw in err_low
                for kw in ("image_process_failed", "chat not found", "bot was blocked", "can't parse", "bad request")
            ):
                raise
            logger.warning(
                "MESSENGER/Telegram",
                f"[{bcfg.name}] Active loop send failed ({loop_exc}), retrying with fresh Bot instance...",
            )

        from telegram import Bot

        async def _fresh_runner() -> Any:
            bot = Bot(token=bcfg.bot_token)
            async with bot:
                return await coro_fn(bot)

        return asyncio.run(_fresh_runner())

    def send_text(
        self,
        provider_cfg: TelegramConfig,
        recipient: str,
        text: str,
        **options: Any,
    ) -> SendResult:
        try:
            bcfg = self._select_bot_config(provider_cfg, options.get("bot_name"))
            chat_id = self._resolve_chat_id(bcfg, recipient)
        except ValueError as exc:
            return SendResult(ok=False, platform=self.name, recipient=recipient, message=str(exc))

        contact_name = options.get("contact_name")
        target_label = f"{contact_name} ({chat_id})" if contact_name else chat_id
        method_used = f"Telegram Bot API (@{bcfg.name})"

        try:
            async def _do_send(bot: Any) -> None:
                await bot.send_message(chat_id=chat_id, text=text)

            self._execute_bot_coro(bcfg, _do_send, timeout=20.0)
            logger.info("MESSENGER/Telegram", f"[{bcfg.name}] Message sent to {target_label}")
            return SendResult(
                ok=True,
                platform=self.name,
                recipient=chat_id,
                verified=True,
                method_used=method_used,
                message=f"Telegram message sent to {target_label} via bot '{bcfg.name}'.",
            )
        except Exception as exc:
            logger.warning("MESSENGER/Telegram", f"[{bcfg.name}] Send failed: {exc}")
            return SendResult(
                ok=False,
                platform=self.name,
                recipient=chat_id,
                method_used=method_used,
                message=f"Telegram send error via '{bcfg.name}': {exc}",
            )

    def send_media(
        self,
        provider_cfg: TelegramConfig,
        recipient: str,
        file_paths: list[str],
        caption: str = "",
        **options: Any,
    ) -> SendResult:
        try:
            bcfg = self._select_bot_config(provider_cfg, options.get("bot_name"))
            chat_id = self._resolve_chat_id(bcfg, recipient)
        except ValueError as exc:
            return SendResult(ok=False, platform=self.name, recipient=recipient, message=str(exc))

        missing = [p for p in file_paths if not os.path.isfile(p)]
        if missing:
            return SendResult(
                ok=False,
                platform=self.name,
                recipient=chat_id,
                message=f"Attachment file(s) not found: {', '.join(missing)}",
            )

        force_document = bool(options.get("force_document", False))
        method_used = f"Telegram Bot API (@{bcfg.name})"
        contact_name = options.get("contact_name")
        target_label = f"{contact_name} ({chat_id})" if contact_name else chat_id

        try:
            for idx, fpath in enumerate(file_paths):
                ext = os.path.splitext(fpath)[1].lower()
                item_caption = (caption[:1024] if caption else "") if idx == 0 else ""

                async def _do_upload(
                    bot: Any,
                    fp: str = fpath,
                    ex: str = ext,
                    cap: str = item_caption,
                ) -> None:
                    if not force_document and ex in _IMAGE_EXTS:
                        try:
                            with open(fp, "rb") as handle:
                                await bot.send_photo(chat_id=chat_id, photo=handle, caption=cap or None)
                            return
                        except Exception as photo_exc:
                            if "image_process_failed" in str(photo_exc).lower():
                                # Valid binary image with extreme dimensions/size -> fallback to original document!
                                with open(fp, "rb") as doc_handle:
                                    await bot.send_document(chat_id=chat_id, document=doc_handle, caption=cap or None)
                                return
                            raise
                    with open(fp, "rb") as handle:
                        if not force_document and ex in _VIDEO_EXTS:
                            await bot.send_video(chat_id=chat_id, video=handle, caption=cap or None)
                        elif not force_document and ex in _AUDIO_EXTS:
                            await bot.send_audio(chat_id=chat_id, audio=handle, caption=cap or None)
                        else:
                            await bot.send_document(chat_id=chat_id, document=handle, caption=cap or None)

                self._execute_bot_coro(bcfg, _do_upload, timeout=90.0)

            logger.info("MESSENGER/Telegram", f"[{bcfg.name}] Sent {len(file_paths)} file(s) to {target_label}")
            return SendResult(
                ok=True,
                platform=self.name,
                recipient=chat_id,
                verified=True,
                method_used=method_used,
                message=f"Sent {len(file_paths)} file(s) ({os.path.basename(file_paths[0])}) to {target_label} via Telegram bot '{bcfg.name}'.",
            )
        except Exception as exc:
            logger.warning("MESSENGER/Telegram", f"[{bcfg.name}] Media send failed: {exc}")
            return SendResult(
                ok=False,
                platform=self.name,
                recipient=chat_id,
                method_used=method_used,
                message=(
                    f"Telegram media send error via '{bcfg.name}': {exc} "
                    "(Do NOT retry with EXECUTOR fake files — inform the user directly.)"
                ),
            )

    def check_health(self, provider_cfg: TelegramConfig) -> ProviderHealth:
        if not provider_cfg or not provider_cfg.enabled:
            return ProviderHealth(
                platform=self.name,
                enabled=False,
                state="DISABLED",
                summary="Disabled",
                method_used="Telegram Bot API",
            )

        if not listener.is_ptb_installed():
            return ProviderHealth(
                platform=self.name,
                enabled=True,
                state="MISSING_DEP",
                summary="Library 'python-telegram-bot' is not installed.",
                method_used="Telegram Bot API",
            )

        enabled_bots = [b for b in (provider_cfg.bots or []) if b.enabled]
        if not enabled_bots:
            return ProviderHealth(
                platform=self.name,
                enabled=True,
                state="DEGRADED",
                summary="Enabled, but no active bots are configured.",
                method_used="Telegram Bot API",
            )

        active_states = listener.get_active_bot_states()
        bot_reports: list[dict[str, Any]] = []
        summary_parts: list[str] = []
        any_online = False
        any_error = False

        for bcfg in enabled_bots:
            if not bcfg.bot_token:
                summary_parts.append(f"{bcfg.name}: NOT CONFIGURED")
                bot_reports.append({"name": bcfg.name, "state": "NOT_CONFIGURED"})
                any_error = True
                continue

            st = active_states.get(bcfg.name)
            if st and st.get("state") == "ONLINE" and st.get("username"):
                uname = st["username"]
                summary_parts.append(f"{bcfg.name}: ONLINE (@{uname})")
                bot_reports.append({"name": bcfg.name, "state": "ONLINE", "username": uname, "polling": True})
                any_online = True
                continue

            try:
                async def _probe(bot: Any) -> str:
                    me = await bot.get_me()
                    return me.username or ""

                uname = self._execute_bot_coro(bcfg, _probe, timeout=10.0)
                summary_parts.append(f"{bcfg.name}: ONLINE (@{uname})")
                bot_reports.append({"name": bcfg.name, "state": "ONLINE", "username": uname, "polling": bool(st)})
                any_online = True
            except Exception as exc:
                summary_parts.append(f"{bcfg.name}: ERROR ({exc})")
                bot_reports.append({"name": bcfg.name, "state": "ERROR", "error": str(exc)})
                any_error = True

        overall = "ONLINE" if (any_online and not any_error) else ("DEGRADED" if any_online else "ERROR")
        return ProviderHealth(
            platform=self.name,
            enabled=True,
            state=overall,
            summary="; ".join(summary_parts),
            method_used="Official Telegram Bot API (HTTPS)",
            details={
                "bots": bot_reports,
                "discovered_chats": listener.get_discovered_chats(),
            },
        )

    def probe_chat(self, provider_cfg: TelegramConfig, chat_ref: str) -> dict[str, Any]:
        """Verifies a Telegram group/channel `@username` or `-100...` Chat ID via active bots."""
        clean_ref = (chat_ref or "").strip()
        if not clean_ref:
            return {"ok": False, "error": "Provide a @username or numeric Chat ID (e.g. -100...)."}
        try:
            bcfg = self._select_bot_config(provider_cfg)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

        try:
            async def _inspect(bot: Any) -> dict[str, Any]:
                ch = await bot.get_chat(clean_ref)
                me = await bot.get_me()
                member_status = "unknown"
                try:
                    mem = await bot.get_chat_member(ch.id, me.id)
                    member_status = str(mem.status)
                except Exception:
                    pass
                ctype = str(getattr(ch, "type", "") or "")
                listener.record_discovered_chat(
                    chat_id=ch.id,
                    title=getattr(ch, "title", "") or "",
                    username=getattr(ch, "username", "") or "",
                    chat_type=ctype,
                    seen_by_bot=bcfg.name,
                )
                return {
                    "ok": True,
                    "chat_id": str(ch.id),
                    "title": getattr(ch, "title", "") or clean_ref,
                    "username": getattr(ch, "username", "") or "",
                    "type": ctype,
                    "bot_used": bcfg.name,
                    "bot_status": member_status,
                }

            return self._execute_bot_coro(bcfg, _inspect, timeout=12.0)
        except Exception as exc:
            return {"ok": False, "error": f"Telegram could not resolve '{clean_ref}' via bot '{bcfg.name}': {exc}"}

    def describe_accounts(self, provider_cfg: TelegramConfig) -> list[str]:
        enabled = bool(provider_cfg and provider_cfg.enabled)
        lines = [f"📨 **Telegram**: {'✅ Enabled' if enabled else '⛔ Disabled'}"]
        if not enabled:
            return lines

        if not listener.is_ptb_installed():
            lines.append("  └─ ❌ Missing dependency: python-telegram-bot")
            return lines

        bots = getattr(provider_cfg, "bots", None) or []
        if not bots:
            lines.append("  └─ (No bots configured)")
        else:
            active_states = listener.get_active_bot_states()
            for bot in bots:
                b_icon = "✅" if bot.enabled else "⛔"
                primary_badge = " [PRIMARY]" if bot.is_primary else ""
                admin_badge = " [ADMIN]" if bot.is_admin else ""
                st = active_states.get(bot.name) or {}
                uname_part = f" @{st['username']}" if st.get("username") else ""
                tk_tail = f"***{bot.bot_token[-6:]}" if bot.bot_token else "missing token"
                lines.append(
                    f"  └─ {b_icon} Bot **{bot.name}**{uname_part}{primary_badge}{admin_badge} (Token: {tk_tail})"
                )

        groups = [g for g in (getattr(provider_cfg, "groups", None) or []) if g.name]
        if groups:
            lines.append("  └─ **Configured Groups & Channels**:")
            for grp in groups:
                g_icon = "✅" if grp.enabled else "⛔"
                alias_str = f" (aliases: {grp.aliases})" if grp.aliases else ""
                lines.append(f"      • {g_icon} **{grp.name}** → `{grp.chat_id}`{alias_str}")
        return lines

    def start_listener(
        self,
        provider_cfg: TelegramConfig,
        inbound_callback: Optional[InboundCallback] = None,
    ) -> None:
        listener.sync_listeners(provider_cfg, inbound_callback=inbound_callback)

    def stop_listener(self) -> None:
        listener.stop_all_bots()
