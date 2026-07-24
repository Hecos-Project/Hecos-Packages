"""
MODULE: Messenger Plugin — Main Entry Point
DESCRIPTION: Exposes MessengerTools to the Hecos agent loop.
             Tools: send_message, list_accounts, check_connection, force_send.
             Providers (Telegram, WhatsApp, Discord) are loaded lazily
             from the dispatcher on first use.
"""

from __future__ import annotations
from hecos.core.logging import logger

try:
    from hecos.core.i18n import translator
except ImportError:
    class _DummyTranslator:
        def t(self, key, **kwargs): return key
    translator = _DummyTranslator()

from .messenger_config.config_manager import get_config_obj
from . import dispatcher


class MessengerTools:
    """
    Hecos Messenger Plugin — send messages via Telegram, WhatsApp, and Discord.
    """

    def __init__(self):
        self.tag    = "MESSENGER"
        self.desc   = "Send messages via Telegram, WhatsApp, and Discord."
        self.status = "ONLINE"
        self._cfg   = None
        # Pre-callbacks registrati da altri plugin (es. Remote Access Pro).
        # {name: callable(text) -> str | None}
        # Se il callable restituisce una stringa, questa viene inviata come risposta
        # e il messaggio NON viene passato all'AI.
        self._pre_callbacks: dict = {}

    def register_pre_callback(self, name: str, fn) -> None:
        """Registra un pre-callback che intercetta i messaggi in ingresso.
        Se fn(text) restituisce una stringa non-None, quella viene usata come risposta."""
        self._pre_callbacks[name] = fn
        logger.info("MESSENGER", f"Pre-callback '{name}' registrato.")

    def _require_config(self):
        if self._cfg is None:
            self._cfg = get_config_obj()
        return self._cfg

    def send_message(self, to: str, text: str, platform: str = None, skip_default_template: bool = False, is_app_open: bool = False) -> str:
        """
        Send a message to a contact or channel.
        """
        cfg = self._require_config()
        try:
            plat, recipient = dispatcher.parse_target(to, platform)
        except ValueError as e:
            return f"❌ {e}"

        # Check explicit template via config
        explicit_template_id = ""
        if plat == "whatsapp":
            if getattr(cfg.whatsapp, "use_template", False):
                explicit_template_id = getattr(cfg.whatsapp, "template_id", "")
            else:
                skip_default_template = True

        # Try to apply template wrapper if not skipped
        if not skip_default_template:
            try:
                from hecos.hpm.templates.store import list_templates, get_template
                
                template_to_apply = None
                if explicit_template_id:
                    template_to_apply = get_template(explicit_template_id)
                else:
                    for t in list_templates(channel=plat):
                        if t.get("is_default"):
                            template_to_apply = t
                            break

                if template_to_apply:
                    h = template_to_apply.get("header", "").strip()
                    f = template_to_apply.get("footer", "").strip()
                    parts = []
                    if h: parts.append(h)
                    parts.append(text)
                    if f: parts.append(f)
                    text = "\n\n".join(parts)
            except Exception as e:
                logger.warning("MESSENGER", f"Error applying template: {e}")

        return dispatcher.dispatch_send(plat, recipient, text, cfg, is_app_open)

    def send_photo(self, to: str, image_path: str, caption: str = "") -> str:
        """
        Send a photo to a contact or channel (Telegram only for now).
        """
        cfg = self._require_config()
        try:
            plat, recipient = dispatcher.parse_target(to, "telegram")
        except ValueError as e:
            return f"❌ {e}"
        
        if plat != "telegram":
            return "❌ send_photo is currently only supported on telegram."

        bot_name = None
        if ":" in recipient:
            parts = recipient.split(":", 1)
            bot_name = parts[0].strip()
            recipient = parts[1].strip()

        try:
            import os
            from .adapters import telegram as tg
            if not os.path.isfile(image_path):
                return f"❌ Errore: file immagine non trovato ({image_path})"
            return tg.send_photo(cfg.telegram, recipient, image_path, caption, bot_name=bot_name)
        except Exception as e:
            return f"❌ Errore durante l'invio della foto: {e}"

    def msg_command(self, args: str) -> str:
        """
        Direct command invoked via /msg <target> <text>
        """
        if not args or " " not in args:
            return "❌ Errore: Sintassi '/msg <piattaforma:destinatario> <testo>'. Esempio: '/msg telegram:@utente ciao'"
        
        target, text = args.split(" ", 1)
        return self.send_message(to=target, text=text)

    def list_accounts(self) -> str:
        cfg = self._require_config()
        lines = [translator.t("ext_messenger_accounts_title") + "\n"]

        # Telegram
        tg_status = "✅ Abilitato" if getattr(cfg.telegram, 'enabled', False) else "⛔ Disabilitato"
        tg_tk = getattr(cfg.telegram, 'bot_token', "")
        tg_id = f"(Token: {'***' + tg_tk[-6:] if tg_tk else 'non impostato'})"
        lines.append(f"📨 **Telegram**: {tg_status} {tg_id}")

        # WhatsApp
        wa_status = "✅ Abilitato [BETA]" if getattr(cfg.whatsapp, 'enabled', False) else "⛔ Disabilitato"
        lines.append(f"💬 **WhatsApp**: {wa_status}")

        # Discord
        dc_status = "✅ Abilitato" if getattr(cfg.discord, 'enabled', False) else "⛔ Disabilitato"
        dc_w = getattr(cfg.discord, 'webhook_url', "")
        dc_wh = "(webhook configurato)" if dc_w else "(nessun webhook)"
        lines.append(f"🔵 **Discord**: {dc_status} {dc_wh}")

        return "\n".join(lines)

    def check_connection(self, platform: str = None) -> str:
        cfg = self._require_config()
        results = dispatcher.dispatch_check(platform, cfg)

        if platform:
            status = results.get(platform.lower(), "UNKNOWN")
            icon = "✅" if "ONLINE" in status or "BETA" in status else "❌"
            return f"{icon} **{platform.capitalize()}**: {status}"

        lines = [translator.t("ext_messenger_check_title") + "\n"]
        icons = {"ONLINE": "✅", "BETA": "🟡", "DISABLED": "⛔", "NOT": "⚠️", "ERROR": "❌"}
        for pname, st in results.items():
            icon = next((v for k, v in icons.items() if k in st.upper()), "❓")
            lines.append(f"{icon} **{pname.capitalize()}**: {st}")

        return "\n".join(lines)

    def force_send(self) -> str:
        try:
            import pyautogui  # type: ignore
            pyautogui.press('enter')
            return "✅ Ho simulato la pressione del tasto Invio (Forzatura invio)."
        except ImportError:
            return "❌ Impossibile forzare l'invio: pyautogui non è installato."
        except Exception as e:
            return f"❌ Errore durante force_send: {e}"


# ── Singleton ──────────────────────────────────────────────────────────────────
tools = MessengerTools()


def info():
    return {"tag": tools.tag, "desc": tools.desc}


def status():
    return tools.status


def on_load(config: dict = None):
    """Called by the plugin loader when Hecos starts."""
    # Register i18n translations from the plugin's own locales/ directory.
    # The module scanner usually does this automatically, but calling it here
    # guarantees translations are available on every on_load() invocation
    # (including hot-reloads triggered by config saves).
    try:
        from pathlib import Path as _Path
        from hecos.core.i18n.translator import register_package_locales
        _locales_dir = str(_Path(__file__).parent / "locales")
        register_package_locales(_locales_dir)
    except Exception:
        pass  # Non-critical: fall back to key strings if i18n is unavailable

    tools._cfg = get_config_obj()
    cfg = tools._cfg
    enabled_providers = [
        p for p in ("telegram", "whatsapp", "discord")
        if getattr(getattr(cfg, p, None), "enabled", False)
    ]

    if enabled_providers:
        logger.info("MESSENGER", f"Plugin loaded — active providers: {', '.join(enabled_providers)}")
        tools.status = "ONLINE"
        
        # Avvia i listener in background per i provider che lo supportano
        if "telegram" in enabled_providers:
            try:
                from .adapters import telegram as tg
                def on_msg(platform, chat_id, text, bot_name=None):
                    try:
                        # ── Remote Access Pro: intercetta comandi /slash ─────
                        if text and text.strip().startswith("/"):
                            try:
                                from hecos.hpm.remote_access_pro.main import handle_remote_command
                                result = handle_remote_command(text)
                                if result is not None:
                                    logger.info("MESSENGER", f"[RAP] Comando '{text.split()[0]}' gestito direttamente.")
                                    if bot_name:
                                        tg.send_reply(bot_name, chat_id, result)
                                    return
                            except ImportError:
                                pass
                            except Exception as rap_err:
                                logger.error("MESSENGER", f"[RAP] Errore: {rap_err}")

                        # ── Fallback: AI ─────────────────────────────────────
                        from hecos.core.processing.processore import process_exchange
                        logger.info("MESSENGER", f"Routing message from {platform}:{chat_id} to Hecos AI...")

                        video_response, clean_voice = process_exchange(text, voice_status="telegram", sm=None)
                        reply = clean_voice or video_response or "..."

                        # ── Rilevamento immagini: se la risposta contiene un path file immagine ──
                        import re, os
                        img_match = re.search(r'([A-Za-z]:[/\\].+?\.(png|jpg|jpeg|webp))', reply, re.IGNORECASE)
                        if img_match:
                            img_path = img_match.group(1).replace("\\", "/")
                            caption = re.sub(r'([A-Za-z]:[/\\].+?\.(png|jpg|jpeg|webp))', '', reply, flags=re.IGNORECASE).strip()
                            if os.path.isfile(img_path):
                                if bot_name:
                                    tg.send_reply_photo(bot_name, chat_id, img_path, caption or "")
                                return

                        if bot_name:
                            tg.send_reply(bot_name, chat_id, reply)

                    except Exception as e:
                        logger.error("MESSENGER", f"Error routing message to AI: {e}")
                        try:
                            if bot_name:
                                tg.send_reply(bot_name, chat_id, f"⚠️ Errore interno di Hecos: {e}")
                        except Exception:
                            pass

                tg.start_listener(cfg.telegram, message_callback=on_msg)

            except Exception as e:
                logger.error("MESSENGER", f"Errore avvio listener Telegram: {e}")
    else:
        logger.info("MESSENGER", "Plugin loaded — no providers configured (disabled mode).")
        tools.status = "DEGRADED"


def on_unload():
    """Called by the plugin loader when the plugin is disabled/unloaded.
    Stops all active Telegram polling threads gracefully.
    """
    logger.info("MESSENGER", "Plugin unloading — stopping all active listeners...")
    try:
        from .adapters import telegram as tg
        active_names = list(tg._active_bots.keys())
        for name in active_names:
            tg.stop_bot(name)
            logger.info("MESSENGER/Telegram", f"[{name}] Polling stopped (plugin unloaded).")
    except Exception as e:
        logger.error("MESSENGER", f"Error stopping Telegram listeners on unload: {e}")
    tools.status = "OFFLINE"
