"""
MODULE: Messenger — Telegram Adapter
DESCRIPTION: Sends messages via the Telegram Bot API using python-telegram-bot v20+.
             Supports multiple bots dynamically via a central thread/loop registry.
"""

from __future__ import annotations
import asyncio
import threading
from hecos.core.logging import logger

_MISSING = "❌ Telegram: 'python-telegram-bot' is not installed. Run: pip install python-telegram-bot"

# ── Dynamic Bot Registry ──────────────────────────────────────────────────────
# Format: { "bot_name": {"thread": Thread, "loop": asyncio.AbstractEventLoop, "bot": telegram.Bot, "app": Application, "config": TelegramBotConfig} }
import sys
if not hasattr(sys, "_hecos_telegram_active_bots"):
    sys._hecos_telegram_active_bots = {}
_active_bots = sys._hecos_telegram_active_bots
_registry_lock = threading.Lock()

def _get_bot_config(cfg, bot_name: str | None = None):
    """
    Returns the specific TelegramBotConfig.
    If bot_name is None, returns the first enabled bot.
    """
    if not cfg.enabled or not cfg.bots:
        raise ValueError("Telegram is globally disabled or has no bots configured.")
    
    if bot_name:
        for b in cfg.bots:
            if b.name == bot_name:
                if not b.enabled:
                    raise ValueError(f"Telegram bot '{bot_name}' is disabled.")
                return b
        raise ValueError(f"Telegram bot '{bot_name}' not found.")
    
    # Fallback to first enabled bot
    for b in cfg.bots:
        if b.enabled:
            return b
    raise ValueError("No enabled Telegram bots found.")

def _resolve_chat(bcfg, recipient: str) -> str:
    r = recipient.strip()
    if r:
        return r
    if bcfg.default_chat_id:
        return bcfg.default_chat_id
    raise ValueError(f"Telegram bot '{bcfg.name}': no recipient and no default_chat_id configured.")

def _get_bot_instance(bcfg):
    try:
        from telegram import Bot
        return Bot(token=bcfg.bot_token)
    except ImportError:
        raise RuntimeError(_MISSING)

# ── Outbound Sync Interfaces ──────────────────────────────────────────────────

def send(cfg, recipient: str, text: str, bot_name: str | None = None) -> str:
    """Synchronous entry point called by the dispatcher."""
    try:
        bcfg = _get_bot_config(cfg, bot_name)
        chat_id = _resolve_chat(bcfg, recipient)
        bot = _get_bot_instance(bcfg)

        async def _send():
            async with bot:
                await bot.send_message(chat_id=chat_id, text=text)

        asyncio.run(_send())
        logger.info("MESSENGER/Telegram", f"[{bcfg.name}] Message sent to {chat_id}")
        return f"✅ Messaggio Telegram inviato a `{chat_id}` via `{bcfg.name}`."
    except Exception as e:
        logger.warning("MESSENGER/Telegram", f"Send failed: {e}")
        return f"❌ Telegram send error: {e}"

def send_photo(cfg, recipient: str, image_path: str, caption: str = "", bot_name: str | None = None) -> str:
    """Invia una foto (file locale) via Telegram."""
    try:
        import os
        bcfg = _get_bot_config(cfg, bot_name)
        chat_id = _resolve_chat(bcfg, recipient)
        bot = _get_bot_instance(bcfg)

        async def _send_photo():
            async with bot:
                with open(image_path, "rb") as f:
                    await bot.send_photo(chat_id=chat_id, photo=f, caption=caption)

        asyncio.run(_send_photo())
        logger.info("MESSENGER/Telegram", f"[{bcfg.name}] Photo sent to {chat_id}")
        return f"✅ Foto inviata a `{chat_id}` via `{bcfg.name}`."
    except Exception as e:
        logger.warning("MESSENGER/Telegram", f"send_photo failed: {e}")
        return f"❌ Telegram send_photo error: {e}"

def check(cfg) -> str:
    """Test the Telegram connection by calling getMe on all enabled bots."""
    if not cfg.enabled or not cfg.bots:
        return "DISABLED"
    
    results = []
    try:
        for bcfg in cfg.bots:
            if not bcfg.enabled:
                continue
            if not bcfg.bot_token:
                results.append(f"{bcfg.name}: NOT CONFIGURED")
                continue
            
            bot = _get_bot_instance(bcfg)
            async def _check(b=bot):
                async with b:
                    me = await b.get_me()
                    return me.username
            
            try:
                username = asyncio.run(_check())
                results.append(f"{bcfg.name}: ONLINE (@{username})")
            except Exception as e:
                results.append(f"{bcfg.name}: ERROR ({e})")
                
        if not results:
            return "DISABLED (no enabled bots)"
        return "\n".join(results)
    except Exception as e:
        return f"ERROR: {e}"

# ── Dynamic Send Reply (Event Loop Injection) ──────────────────────────────────

def send_reply(bot_name: str, chat_id: str, text: str):
    with _registry_lock:
        state = _active_bots.get(bot_name)
    
    if state and state["loop"] and not state["loop"].is_closed():
        async def _do_send():
            await state["bot"].send_message(chat_id=chat_id, text=text)
        future = asyncio.run_coroutine_threadsafe(_do_send(), state["loop"])
        try:
            future.result(timeout=15)
            logger.info("MESSENGER/Telegram", f"[{bot_name}] Reply sent to {chat_id}")
        except Exception as e:
            logger.error("MESSENGER/Telegram", f"[{bot_name}] send_reply failed: {e}")
    else:
        logger.warning("MESSENGER/Telegram", f"[{bot_name}] send_reply: no active listener loop")

def send_reply_photo(bot_name: str, chat_id: str, image_path: str, caption: str = ""):
    with _registry_lock:
        state = _active_bots.get(bot_name)
    
    if state and state["loop"] and not state["loop"].is_closed():
        async def _do_send():
            with open(image_path, "rb") as f:
                await state["bot"].send_photo(chat_id=chat_id, photo=f, caption=caption)
        future = asyncio.run_coroutine_threadsafe(_do_send(), state["loop"])
        try:
            future.result(timeout=20)
            logger.info("MESSENGER/Telegram", f"[{bot_name}] Photo reply sent to {chat_id}")
        except Exception as e:
            logger.error("MESSENGER/Telegram", f"[{bot_name}] send_reply_photo failed: {e}")

# ── Background Listeners ───────────────────────────────────────────────────────

def _run_bot_worker(bcfg, message_callback):
    bot_name = bcfg.name
    try:
        from telegram.ext import Application, MessageHandler, filters
    except ImportError:
        logger.warning("MESSENGER/Telegram", f"[{bot_name}] python-telegram-bot non installato.")
        return

    try:
        app = Application.builder().token(bcfg.bot_token).build()
        bot_username_holder = [None]

        async def _fetch_username():
            me = await app.bot.get_me()
            bot_username_holder[0] = me.username.lower()

        async def handle_msg(update, context):
            # effective_message covers both `message` (groups/DMs) AND `channel_post` (channels)
            msg = update.effective_message
            if not msg:
                return

            # --- ANTI-LOOP: ignore messages from other bots (including ourselves) ---
            if update.effective_user and update.effective_user.is_bot:
                return

            chat_id = str(update.effective_chat.id)
            sender = update.effective_user.first_name if update.effective_user else "?"
            text = msg.text
            
            # --- PROTEZIONE ADMIN ---
            if bcfg.is_admin:
                admin_id = str(bcfg.default_chat_id) if bcfg.default_chat_id else ""
                if admin_id and chat_id != admin_id:
                    # Silently ignore (do NOT reply — a reply in a channel would re-trigger the loop)
                    logger.warning("MESSENGER/Telegram", f"[{bot_name}] Messaggio ignorato: chat_id '{chat_id}' non autorizzato.")
                    return

            # --- GESTIONE MULTIMEDIALE ---
            if not text and msg.video_note:
                await context.bot.send_message(chat_id=chat_id, text="⚠️ Hai inviato un video-messaggio (quello rotondo). Attualmente riesco ad ascoltare solo le **note vocali** classiche.")
                return
            
            if not text and msg.voice:
                try:
                    voice_file = await msg.voice.get_file()
                    import io
                    ogg_data = await voice_file.download_as_bytearray()
                    import soundfile as sf
                    data, samplerate = sf.read(io.BytesIO(ogg_data))
                    wav_io = io.BytesIO()
                    sf.write(wav_io, data, samplerate, format='WAV')
                    wav_io.seek(0)
                    import speech_recognition as sr
                    r = sr.Recognizer()
                    with sr.AudioFile(wav_io) as source:
                        audio_data = r.record(source)
                    lang = "it-IT"
                    try:
                        from hecos.core.audio.device_manager import get_audio_config
                        conf = get_audio_config()
                        if "language" in conf:
                            lang = conf["language"]
                    except Exception:
                        pass
                    text = r.recognize_google(audio_data, language=lang)
                    logger.info("MESSENGER/Telegram", f"[{bot_name}] Trascrizione vocale: {text}")
                except Exception as e:
                    logger.error("MESSENGER/Telegram", f"[{bot_name}] Errore trascrizione: {e}")
                    await context.bot.send_message(chat_id=chat_id, text="⚠️ Ops, non sono riuscita a capire questo vocale.")
                    return

            if not text:
                return

            text_lower = text.lower()
            
            # --- LOGICA GRUPPI (se non è admin) ---
            if not bcfg.is_admin:
                my_username = bot_username_holder[0] or bot_name
                mentioned = f"@{my_username}" in text_lower
                
                should_respond = False
                mode = bcfg.group_mode
                kws = [k.strip().lower() for k in bcfg.group_keywords.split(",") if k.strip()]
                
                if mode == "all":
                    should_respond = True
                elif mode == "mention" and mentioned:
                    should_respond = True
                elif mode == "keyword" and any(kw in text_lower for kw in kws):
                    should_respond = True
                
                if not should_respond:
                    return
                
                # Pulisce il tag
                if mentioned:
                    text = text.replace(f"@{my_username}", "", 1).strip()
            
            if not text:
                return

            logger.info("MESSENGER/Telegram", f"[{bot_name}] da {chat_id} ({sender}): {text}")

            if message_callback:
                # Passa bot_name al callback per instradare la risposta
                def _run_cb():
                    message_callback("telegram", chat_id, text, bot_name=bot_name)
                threading.Thread(target=_run_cb, daemon=True).start()

        app.add_handler(MessageHandler(filters.TEXT | filters.VOICE | filters.VIDEO_NOTE | filters.UpdateType.CHANNEL_POSTS, handle_msg))

        import asyncio as _asyncio
        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)
        
        with _registry_lock:
            _active_bots[bot_name]["loop"] = loop
            _active_bots[bot_name]["bot"] = app.bot
            _active_bots[bot_name]["app"] = app

        loop.run_until_complete(_fetch_username())
        
        logger.info("MESSENGER/Telegram", f"[{bot_name}] Polling avviato.")
        app.run_polling(drop_pending_updates=True, stop_signals=[])

    except Exception as e:
        logger.error("MESSENGER/Telegram", f"[{bot_name}] Errore listener: {e}")


def stop_bot(bot_name: str):
    """Safely stops an active bot polling loop and thread."""
    with _registry_lock:
        state = _active_bots.get(bot_name)
    if not state:
        return
        
    app = state.get("app")
    loop = state.get("loop")
    
    if app and loop and not loop.is_closed():
        logger.info("MESSENGER/Telegram", f"[{bot_name}] Arresto del polling attivo per reload...")
        async def _stop():
            try:
                await app.updater.stop()
                await app.stop()
                await app.shutdown()
            except Exception as e:
                logger.error("MESSENGER/Telegram", f"[{bot_name}] Errore durante l'arresto del bot: {e}")
        
        future = asyncio.run_coroutine_threadsafe(_stop(), loop)
        try:
            future.result(timeout=5)
        except Exception:
            pass
            
    thread = state.get("thread")
    if thread and thread.is_alive():
        # We cannot join easily if the event loop is blocked, but we'll try
        thread.join(timeout=1)
        
    with _registry_lock:
        if bot_name in _active_bots:
            del _active_bots[bot_name]


def start_listener(cfg, message_callback=None):
    """
    Starts threads for all enabled bots in the config.
    If a bot is already running with the same token, it is left untouched.
    Only stops bots that are removed from config or whose token changed.
    """
    if not cfg.enabled or not cfg.bots:
        # Stop all currently running bots
        active_names = list(_active_bots.keys())
        for name in active_names:
            stop_bot(name)
        return

    configured_names = {bcfg.name for bcfg in cfg.bots if bcfg.enabled and bcfg.bot_token}

    # 1. Stop bots that are no longer in the config
    for name in list(_active_bots.keys()):
        if name not in configured_names:
            stop_bot(name)

    # 2. Start or update bots
    for bcfg in cfg.bots:
        if not bcfg.enabled or not bcfg.bot_token:
            continue

        with _registry_lock:
            state = _active_bots.get(bcfg.name)

        # If already running with the same token and thread is alive → skip entirely
        if state:
            thread = state.get("thread")
            old_token = state.get("config", {}).bot_token if state.get("config") else None
            if thread and thread.is_alive() and old_token == bcfg.bot_token:
                logger.info("MESSENGER/Telegram", f"[{bcfg.name}] Already running, skipping restart.")
                continue
            # Token changed or thread died → stop and restart
            stop_bot(bcfg.name)

        with _registry_lock:
            _active_bots[bcfg.name] = {
                "config": bcfg,
                "thread": None,
                "loop": None,
                "bot": None,
                "app": None
            }

        t = threading.Thread(
            target=_run_bot_worker,
            args=(bcfg, message_callback),
            daemon=True,
            name=f"TgListener_{bcfg.name}"
        )
        with _registry_lock:
            _active_bots[bcfg.name]["thread"] = t
        t.start()
        logger.info("MESSENGER/Telegram", f"[{bcfg.name}] Thread avviato.")

