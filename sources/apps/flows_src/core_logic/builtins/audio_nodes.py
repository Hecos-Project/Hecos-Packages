from hecos.modules.flows.core_logic.registry import _REGISTRY, log
import time

def _setup_audio_wrappers():
    def _audio_speak(text: str = "", **kwargs):
        try:
            from hecos.core.audio import voice
            voice.speak(text, _run_id=kwargs.get("_run_id"), _timeout=kwargs.get("_timeout_seconds"), _start=kwargs.get("_start_time"))
        except Exception as e:
            log.error(f"Cannot speak: {e}")
        return text

    def _audio_play_alarm(sound: str = "default", **kwargs):
        import os
        import time
        from hecos.modules.flows.core_logic.engine import is_run_aborted

        run_id = kwargs.get("_run_id")
        timeout = kwargs.get("_timeout_seconds", 0)
        start_time = kwargs.get("_start_time", time.time())

        def _should_stop():
            if run_id and is_run_aborted(run_id): return True
            if timeout and timeout > 0 and (time.time() - start_time) > timeout: return True
            return False

        base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

        try:
            if not sound or sound == "default":
                from hecos.core.audio import beep_generator
                beep_generator._play_beep_on_device(None)
                return True

            path = os.path.join(base_dir, "assets", "sounds", sound)

            if not os.path.exists(path):
                log.error(f"Cannot play alarm, file not found: {path}")
                from hecos.core.audio import beep_generator
                beep_generator._play_beep_on_device(None)
                return False

            played = False

            # Strategy 1: sounddevice + wave (headless-safe, no display required)
            if path.lower().endswith(".wav"):
                try:
                    import wave
                    import numpy as np
                    import sounddevice as sd
                    with wave.open(path, 'rb') as wf:
                        raw = wf.readframes(wf.getnframes())
                        data = np.frombuffer(raw, dtype=np.int16)
                        sd.play(data.astype("float32") / 32768.0, samplerate=wf.getframerate())
                        duration = len(data) / wf.getframerate() / wf.getnchannels()
                        end_time = time.time() + duration
                        while time.time() < end_time:
                            if _should_stop():
                                sd.stop()
                                break
                            time.sleep(0.05)
                    played = True
                except Exception as e_sd:
                    log.debug(f"[Flows.Alarm] sounddevice failed ({e_sd}), trying pygame...")

            # Strategy 2: pygame.mixer (works for mp3/wav/ogg, no display needed)
            if not played:
                try:
                    import pygame.mixer as mixer
                    if not mixer.get_init():
                        mixer.init()
                    mixer.music.load(path)
                    mixer.music.play()
                    while mixer.music.get_busy():
                        if _should_stop():
                            mixer.music.stop()
                            break
                        time.sleep(0.1)
                    played = True
                except Exception as e_pg:
                    log.warning(f"[Flows.Alarm] pygame.mixer failed ({e_pg}), trying winsound...")

            # Strategy 3: winsound (Windows-only, WAV only, last resort)
            if not played:
                if not _should_stop():
                    try:
                        import winsound
                        if path.lower().endswith(".wav"):
                            winsound.PlaySound(path, winsound.SND_FILENAME)
                            played = True
                    except Exception as e_ws:
                        log.error(f"[Flows.Alarm] All playback strategies failed. Last error: {e_ws}")

        except Exception as e:
            log.error(f"Cannot play alarm: {e}")
        return True

    _REGISTRY["AUDIO__speak"] = {
        "name": "AUDIO__speak",
        "description": "Make Hecos speak a message aloud via TTS.",
        "params": {"text": "string"},
        "category": "AUDIO",
        "icon": "🔊",
        "fn": _audio_speak,
    }
    _REGISTRY["AUDIO__play_alarm"] = {
        "name": "AUDIO__play_alarm",
        "description": "Play an alarm sound.",
        "params": {"sound": "string (default)"},
        "category": "AUDIO",
        "icon": "🔔",
        "fn": _audio_play_alarm,
    }

