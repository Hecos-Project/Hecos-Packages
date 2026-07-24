"""
MODULE: Reminder Notifier
DESCRIPTION: Fires a reminder alert.
             On trigger:
             1. TTS via core/audio/voice.py speak() — runs in a daemon thread
             2. StateManager.add_event("reminder_fire") → WebUI SSE banner
"""

import os
import threading
import time
from hecos.core.logging import logger

try:
    from hecos.core.i18n import translator
except ImportError:
    class _DummyTranslator:
        def t(self, key, **kwargs): return key
    translator = _DummyTranslator()


# Resolve sounds directory — look in this package's own sounds/ subfolder first,
# then fall back to the global hecos/assets/sounds/.
_PKG_DIR    = os.path.dirname(os.path.abspath(__file__))
_SOUNDS_DIR = os.path.join(_PKG_DIR, "sounds")
_GLOBAL_SOUNDS_DIR = os.path.abspath(os.path.join(_PKG_DIR, "..", "..", "assets", "sounds"))


def _resolve_ringtone(ringtone_path: str) -> str:
    """Returns the absolute path to the ringtone file, or empty string if not found."""
    candidates = []

    if ringtone_path:
        # Absolute path supplied — use directly if it exists
        if os.path.isabs(ringtone_path) and os.path.exists(ringtone_path):
            return ringtone_path
        # Relative name — look in package sounds/ first, then global assets/sounds/
        candidates.append(os.path.join(_SOUNDS_DIR, ringtone_path))
        candidates.append(os.path.join(_GLOBAL_SOUNDS_DIR, ringtone_path))

    # Fallback to built-in default in both locations
    candidates.append(os.path.join(_SOUNDS_DIR, "Default_System_Alert.mp3"))
    candidates.append(os.path.join(_GLOBAL_SOUNDS_DIR, "Default_System_Alert.mp3"))

    for c in candidates:
        if os.path.exists(c):
            return c

    logger.debug("REMINDER", f"Ringtone not found. Searched: {candidates}")
    return ""


def _play_ringtone_once(path: str, stop_check=None) -> None:
    """
    Plays a ringtone file synchronously (blocks until playback ends or stop_check returns True).
    Uses pygame for robust cross-platform MP3/WAV/OGG playback.
    """
    if not path or not os.path.exists(path):
        logger.debug("REMINDER", f"Ringtone file not found ('{path}'), using system beep fallback.")
        try:
            import sys
            if sys.platform == "win32":
                import winsound
                for _ in range(3):
                    winsound.Beep(880, 400)
                    time.sleep(0.1)
        except Exception:
            pass
        return

    try:
        import pygame
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if stop_check and stop_check():
                pygame.mixer.music.stop()
                break
            time.sleep(0.2)
        pygame.mixer.quit()
        return
    except Exception as e:
        logger.debug("REMINDER", f"Pygame audio failed: {e}. Trying system fallbacks.")

    try:
        import sys, subprocess, shutil
        proc = None
        if sys.platform == "win32":
            if path.lower().endswith(".wav"):
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME)
            else:
                import winsound
                for _ in range(3):
                    winsound.Beep(880, 400)
                    time.sleep(0.1)
            return
        elif sys.platform == "darwin":
            proc = subprocess.Popen(["afplay", path])
        else:
            if shutil.which("ffplay"):
                proc = subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path])
            elif shutil.which("mpg123") and path.lower().endswith(".mp3"):
                proc = subprocess.Popen(["mpg123", "-q", path])
            elif shutil.which("mpv"):
                proc = subprocess.Popen(["mpv", "--no-video", "--really-quiet", path])
        
        if proc is not None:
            while proc.poll() is None:
                if stop_check and stop_check():
                    proc.terminate()
                    break
                time.sleep(0.2)
                pass

    except Exception as e:
        logger.debug("REMINDER", f"Ringtone playback error: {e}")



def fire_reminder(reminder: dict) -> None:
    """
    Dispatches a reminder alert. Called by the APScheduler worker thread.
    :param reminder: dict from store (id, title, when_iso, cron_expr, repeat, status)
    """
    title = reminder.get("title", "Reminder")
    reminder_id = reminder.get("id", "")
    is_repeat = bool(reminder.get("repeat", 0))

    logger.info("REMINDER", f"🔔 FIRE: [{reminder_id}] '{title}'")

    def _alert_async():
        from hecos.hpm.reminder.reminder_config import get_reminder_config
        plugin_config = get_reminder_config()

        mode = reminder.get("mode") # Per-reminder override
        if not mode:
            mode = plugin_config.get("reminder_mode", "voice").lower()
        else:
            mode = mode.lower()
            
        ringtone_path = plugin_config.get("ringtone_path", "").strip()

        # Per-reminder interactive setting overrides system default
        r_interactive = reminder.get("interactive")  # 1, 0, or None
        if r_interactive is None:
            snooze_enabled = plugin_config.get("reminder_snooze_ui", False)
        else:
            snooze_enabled = bool(r_interactive)

        from hecos.hpm.reminder.main import tools
        tools.stop_flag = False

        resolved = _resolve_ringtone(ringtone_path)
        logger.info("REMINDER", f"🎵 Ringtone: '{resolved}' | mode={mode} | snooze={snooze_enabled}")

        # ── TTS: always plays exactly once ────────────────────────────────────
        if mode in ("voice", "both"):
            try:
                from hecos.core.audio.voice import speak
                label = translator.t("ext_reminder_title")
                speak(f"{label}: {title}")
            except Exception as e:
                logger.debug("REMINDER", f"TTS error: {e}")

        # ── Ringtone ──────────────────────────────────────────────────────────
        if mode not in ("ringtone", "both"):
            return  # Voice-only: done

        if not snooze_enabled:
            # Normal mode: play ringtone once
            _play_ringtone_once(resolved, stop_check=lambda: tools.stop_flag)
        else:
            # Snooze mode: loop until user stops
            while not tools.stop_flag:
                _play_ringtone_once(resolved, stop_check=lambda: tools.stop_flag)
                if tools.stop_flag:
                    break
                # Small gap between plays
                for _ in range(10):
                    if tools.stop_flag:
                        break
                    time.sleep(0.1)

        if tools.stop_flag:
            logger.info("REMINDER", "Audio loop interrupted by user.")

    # ── SSE event includes interactive flag so banner renders correctly ─────────
    # Resolve effective interactive value from reminder or system config
    r_interactive = reminder.get("interactive")
    if r_interactive is None:
        try:
            from hecos.hpm.reminder.reminder_config import get_reminder_config
            _snooze = get_reminder_config().get("reminder_snooze_ui", False)
        except Exception:
            _snooze = False
    else:
        _snooze = bool(r_interactive)

    try:
        from hecos.modules.web_ui.server import get_state_manager
        sm = get_state_manager()
        if sm is not None:
            sm.add_event("reminder_fire", {
                "id":          reminder_id,
                "title":       title,
                "interactive": _snooze,
            })
            logger.info("REMINDER", f"📢 SSE event pushed for [{reminder_id}] interactive={_snooze}")
        else:
            logger.info("REMINDER", "StateManager not available — WebUI push skipped.")
    except Exception as e:
        logger.info("REMINDER", f"WebUI SSE push error: {e}")

    tts_thread = threading.Thread(target=_alert_async, daemon=True, name=f"reminder-alert-{reminder_id}")
    tts_thread.start()

    # ── Mark as fired (one-shot only) ─────────────────────────────────────────
    if not is_repeat:
        try:
            from hecos.hpm.reminder import store
            store.update_status(reminder_id, "fired")
        except Exception as e:
            logger.debug("REMINDER", f"Store update error: {e}")
