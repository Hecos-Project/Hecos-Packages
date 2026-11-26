"""
Multi-Bot Background Polling Listener, Active Event-Loop Registry, and Live Group/Channel
Auto-Discovery for Telegram (v2.3).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from hecos.core.logging import logger
from ...core.base_provider import InboundCallback
from .config import TelegramBotConfig, TelegramConfig
from .voice_stt import transcribe_ogg_voice_bytes

# Suppress noisy 10s long-polling DEBUG logs from python-telegram-bot / httpx
for _noisy_logger in ("telegram", "telegram.ext", "httpx", "httpcore", "apscheduler"):
    logging.getLogger(_noisy_logger).setLevel(logging.WARNING)


if not hasattr(sys, "_hecos_telegram_active_bots"):
    sys._hecos_telegram_active_bots = {}  # type: ignore[attr-defined]
_active_bots: dict[str, dict[str, Any]] = sys._hecos_telegram_active_bots  # type: ignore[attr-defined]

if not hasattr(sys, "_hecos_telegram_discovered_chats"):
    sys._hecos_telegram_discovered_chats = {}  # type: ignore[attr-defined]
_discovered_chats: dict[str, dict[str, Any]] = sys._hecos_telegram_discovered_chats  # type: ignore[attr-defined]

_registry_lock = threading.Lock()


def _discovered_cache_file() -> Path:
    try:
        from hecos.core.constants import HECOS_DIR
        data_dir = Path(HECOS_DIR) / "data"
    except Exception:
        data_dir = Path(__file__).resolve().parents[4] / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "telegram_discovered_chats.json"


def _load_discovered_cache() -> None:
    cfile = _discovered_cache_file()
    if not cfile.is_file():
        return
    try:
        raw = json.loads(cfile.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            with _registry_lock:
                for cid, entry in raw.items():
                    if isinstance(entry, dict) and cid not in _discovered_chats:
                        _discovered_chats[str(cid)] = entry
    except Exception:
        pass


def record_discovered_chat(
    chat_id: str | int,
    title: str = "",
    username: str = "",
    chat_type: str = "",
    seen_by_bot: str = "",
) -> None:
    """Records a group, supergroup, or channel observed by a Telegram bot for 1-click UI setup."""
    ctype = (chat_type or "").strip().lower()
    if ctype not in ("group", "supergroup", "channel"):
        return
    cid_str = str(chat_id).strip()
    if not cid_str:
        return

    entry = {
        "chat_id": cid_str,
        "title": (title or "").strip() or cid_str,
        "username": (username or "").strip().lstrip("@"),
        "type": ctype,
        "seen_by_bot": seen_by_bot,
        "last_seen": int(time.time()),
    }
    with _registry_lock:
        _discovered_chats[cid_str] = entry
        snapshot = dict(_discovered_chats)

    try:
        _discovered_cache_file().write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def get_discovered_chats() -> list[dict[str, Any]]:
    _load_discovered_cache()
    with _registry_lock:
        items = list(_discovered_chats.values())
    items.sort(key=lambda x: int(x.get("last_seen") or 0), reverse=True)
    return items[:25]


def is_ptb_installed() -> bool:
    try:
        import telegram  # noqa: F401
        from telegram.ext import Application  # noqa: F401
        return True
    except ImportError:
        return False


def get_active_bot_states() -> dict[str, dict[str, Any]]:
    with _registry_lock:
        return {k: dict(v) for k, v in _active_bots.items()}


def run_on_active_bot_loop(
    bot_name: str,
    coro_builder: Callable[[Any], Any],
    timeout: float = 25.0,
) -> tuple[bool, Any]:
    """
    If `bot_name` has a live polling loop, schedules `coro_builder(bot)` on that loop.
    Returns (handled: bool, result_or_error: Any).
    """
    with _registry_lock:
        state = _active_bots.get(bot_name)

    if not state:
        return False, None

    loop = state.get("loop")
    bot = state.get("bot")
    thread = state.get("thread")
    if not (loop and bot and thread and thread.is_alive() and not loop.is_closed()):
        return False, None

    future = asyncio.run_coroutine_threadsafe(coro_builder(bot), loop)
    return True, future.result(timeout=timeout)


def _run_bot_worker(bcfg: TelegramBotConfig, inbound_callback: Optional[InboundCallback]) -> None:
    bot_name = bcfg.name
    from telegram.ext import Application, ChatMemberHandler, MessageHandler, filters

    try:
        app = Application.builder().token(bcfg.bot_token).build()
        bot_username_holder: list[Optional[str]] = [None]

        async def _fetch_identity() -> None:
            me = await app.bot.get_me()
            uname = (me.username or "").lower()
            bot_username_holder[0] = uname
            with _registry_lock:
                if bot_name in _active_bots:
                    _active_bots[bot_name]["username"] = me.username or ""
                    _active_bots[bot_name]["state"] = "ONLINE"
                    _active_bots[bot_name]["error"] = ""

        async def _handle_member_update(update: Any, context: Any) -> None:
            chat = getattr(update, "effective_chat", None)
            if chat:
                record_discovered_chat(
                    chat_id=chat.id,
                    title=getattr(chat, "title", "") or "",
                    username=getattr(chat, "username", "") or "",
                    chat_type=str(getattr(chat, "type", "") or ""),
                    seen_by_bot=bot_name,
                )

        async def _handle_msg(update: Any, context: Any) -> None:
            chat = update.effective_chat
            if chat:
                record_discovered_chat(
                    chat_id=chat.id,
                    title=getattr(chat, "title", "") or "",
                    username=getattr(chat, "username", "") or "",
                    chat_type=str(getattr(chat, "type", "") or ""),
                    seen_by_bot=bot_name,
                )

            msg = update.effective_message
            if not msg:
                return
            if update.effective_user and update.effective_user.is_bot:
                return

            chat_id = str(chat.id) if chat else ""
            if not chat_id:
                return
            chat_type = str(getattr(chat, "type", "") or "").lower()
            is_group_chat = chat_type in ("group", "supergroup", "channel")
            chat_uname = (getattr(chat, "username", "") or "").strip().lower()
            sender = update.effective_user.first_name if update.effective_user else "?"
            text = msg.text or msg.caption

            # Admin lock: ignore unauthorized private chats while allowing matching @username groups
            if bcfg.is_admin:
                admin_id = str(bcfg.default_chat_id).strip() if bcfg.default_chat_id else ""
                if admin_id:
                    norm_admin_uname = admin_id.lstrip("@").lower().replace("-", "_")
                    norm_chat_uname = chat_uname.replace("-", "_")
                    matches_admin = (
                        chat_id == admin_id
                        or (admin_id.startswith("@") and norm_chat_uname and norm_chat_uname == norm_admin_uname)
                    )
                    if not matches_admin:
                        logger.warning(
                            "MESSENGER/Telegram",
                            f"[{bot_name}] Ignored message from unauthorized chat_id '{chat_id}'.",
                        )
                        return

            if not text and msg.video_note:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ Video notes are not supported yet. Please send a standard voice message or text.",
                )
                return

            if not text and msg.voice:
                try:
                    voice_file = await msg.voice.get_file()
                    ogg_bytes = await voice_file.download_as_bytearray()
                    text = transcribe_ogg_voice_bytes(ogg_bytes)
                    logger.info("MESSENGER/Telegram", f"[{bot_name}] Transcribed voice note: {text}")
                except Exception as stt_exc:
                    logger.error("MESSENGER/Telegram", f"[{bot_name}] Voice transcription error: {stt_exc}")
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="⚠️ Could not transcribe this voice message.",
                    )
                    return

            if not text:
                return

            my_username = (bot_username_holder[0] or bot_name).lower()
            text_lower = text.lower()
            mentioned = bool(my_username and f"@{my_username}" in text_lower)

            # Inspect reply_to_message so replying directly to a bot triggers response & carries context
            reply_msg = getattr(msg, "reply_to_message", None)
            replied_to_me = False
            replied_to_other_bot = False
            reply_context_line = ""
            if reply_msg is not None:
                r_user = getattr(reply_msg, "from_user", None)
                r_uname = (getattr(r_user, "username", "") or "").strip().lower() if r_user else ""
                r_is_bot = bool(getattr(r_user, "is_bot", False)) if r_user else False
                if my_username and r_uname == my_username:
                    replied_to_me = True
                elif r_is_bot and r_uname and r_uname != my_username:
                    replied_to_other_bot = True

                r_body = (getattr(reply_msg, "text", None) or getattr(reply_msg, "caption", None) or "").strip()
                r_media = ""
                if getattr(reply_msg, "photo", None):
                    r_media = " [Photo]"
                elif getattr(reply_msg, "document", None):
                    r_media = " [Document]"
                elif getattr(reply_msg, "voice", None) or getattr(reply_msg, "audio", None):
                    r_media = " [Voice]"

                if r_body or r_media:
                    short_body = (r_body[:240] + "...") if len(r_body) > 240 else r_body
                    if short_body:
                        reply_context_line = f'> [Quoted{r_media}: "{short_body}"]'
                    else:
                        reply_context_line = f"> [Quoted{r_media.strip()}]"

            if is_group_chat or not bcfg.is_admin:
                # Never hijack a direct reply aimed at a sibling bot unless explicitly @mentioned
                if replied_to_other_bot and not mentioned:
                    return

                kws = [k.strip().lower() for k in (bcfg.group_keywords or "").split(",") if k.strip()]
                is_slash_cmd = text.strip().startswith("/")
                should_respond = (
                    (bcfg.is_admin and is_slash_cmd)
                    or bcfg.group_mode == "all"
                    or (bcfg.group_mode == "mention" and (mentioned or replied_to_me))
                    or (bcfg.group_mode == "keyword" and (replied_to_me or any(kw in text_lower for kw in kws)))
                )
                if not should_respond:
                    return

            if mentioned and my_username:
                text = re.sub(rf"@{re.escape(my_username)}\b", "", text, count=1, flags=re.IGNORECASE).strip()

            if not text:
                return

            logger.info("MESSENGER/Telegram", f"[{bot_name}] From {chat_id} ({sender}): {text}")

            # Enrich group speaker name & quoted reply envelope without triggering outbound keywords
            formatted_inbound = f"[{sender}]: {text}" if (is_group_chat and not text.startswith("/")) else text
            if reply_context_line and not text.startswith("/"):
                formatted_inbound = f"{reply_context_line}\n{formatted_inbound}"

            if inbound_callback:
                threading.Thread(
                    target=inbound_callback,
                    args=("telegram", chat_id, formatted_inbound, bot_name, bool(bcfg.is_admin)),
                    daemon=True,
                ).start()

        async def _on_error(update: object, context: Any) -> None:
            err = getattr(context, "error", None)
            logger.warning("MESSENGER/Telegram", f"[{bot_name}] Polling warning: {err}")

        app.add_error_handler(_on_error)
        app.add_handler(ChatMemberHandler(_handle_member_update, ChatMemberHandler.MY_CHAT_MEMBER))
        app.add_handler(
            MessageHandler(
                filters.TEXT | filters.VOICE | filters.VIDEO_NOTE | filters.UpdateType.CHANNEL_POSTS,
                _handle_msg,
            )
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        with _registry_lock:
            if bot_name in _active_bots:
                _active_bots[bot_name]["loop"] = loop
                _active_bots[bot_name]["bot"] = app.bot
                _active_bots[bot_name]["app"] = app

        async def _runner() -> None:
            async with app:
                await _fetch_identity()
                await app.start()
                await app.updater.start_polling(drop_pending_updates=True)
                logger.info(
                    "MESSENGER/Telegram",
                    f"[{bot_name}] Polling active (@{bot_username_holder[0] or '?'}).",
                )
                stop_ev = _active_bots.get(bot_name, {}).get("stop_event")
                while stop_ev and not stop_ev.is_set():
                    await asyncio.sleep(1.0)
                await app.updater.stop()
                await app.stop()

        loop.run_until_complete(_runner())
    except Exception as exc:
        logger.error("MESSENGER/Telegram", f"[{bot_name}] Listener crashed: {exc}")
        with _registry_lock:
            if bot_name in _active_bots:
                _active_bots[bot_name]["state"] = "ERROR"
                _active_bots[bot_name]["error"] = str(exc)
    finally:
        with _registry_lock:
            current = _active_bots.get(bot_name)
            if current and current.get("thread") is threading.current_thread():
                _active_bots.pop(bot_name, None)


def stop_bot(bot_name: str) -> None:
    with _registry_lock:
        entry = _active_bots.get(bot_name)
        if not entry:
            return
        stop_ev = entry.get("stop_event")
        if stop_ev:
            stop_ev.set()
        thread = entry.get("thread")

    if thread and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=4.0)

    with _registry_lock:
        _active_bots.pop(bot_name, None)


def stop_all_bots() -> None:
    with _registry_lock:
        names = list(_active_bots.keys())
    for name in names:
        stop_bot(name)


def sync_listeners(cfg: TelegramConfig, inbound_callback: Optional[InboundCallback]) -> None:
    """Starts, updates, or stops Telegram polling threads to match `cfg`."""
    _load_discovered_cache()
    if not cfg or not cfg.enabled or not is_ptb_installed():
        stop_all_bots()
        return

    desired: dict[str, TelegramBotConfig] = {
        b.name: b for b in (cfg.bots or []) if b.enabled and b.bot_token and b.name
    }

    with _registry_lock:
        running_names = set(_active_bots.keys())

    for old_name in running_names - set(desired.keys()):
        logger.info("MESSENGER/Telegram", f"[{old_name}] Stopping disabled/removed bot listener.")
        stop_bot(old_name)

    for bname, bcfg in desired.items():
        fingerprint = (
            bcfg.bot_token,
            bcfg.default_chat_id,
            bcfg.is_admin,
            bcfg.group_mode,
            bcfg.group_keywords,
        )
        with _registry_lock:
            existing = _active_bots.get(bname)
            if (
                existing
                and existing.get("fingerprint") == fingerprint
                and existing.get("state") in ("ONLINE", "STARTING")
                and existing.get("thread")
                and existing["thread"].is_alive()
            ):
                continue

        if existing:
            stop_bot(bname)

        stop_ev = threading.Event()
        t = threading.Thread(
            target=_run_bot_worker,
            args=(bcfg, inbound_callback),
            name=f"HecosTG-{bname}",
            daemon=True,
        )
        with _registry_lock:
            _active_bots[bname] = {
                "name": bname,
                "state": "STARTING",
                "username": "",
                "error": "",
                "fingerprint": fingerprint,
                "stop_event": stop_ev,
                "thread": t,
                "loop": None,
                "bot": None,
                "app": None,
            }
        t.start()
        logger.info("MESSENGER/Telegram", f"[{bname}] Listener thread launched.")
