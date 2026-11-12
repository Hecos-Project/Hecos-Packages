"""
Voice Forge - Fish Speech Audio Config Registry
Registers baked custom timbres directly into Hecos config/data/audio.yaml under fish_speech_presets.
Allows newly sculpted voices to appear immediately in Hecos TTS dropdowns.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional
import yaml

try:
    from hecos.core.audio.audio_config import CONFIG_AUDIO_PATH as _CORE_AUDIO_PATH
    AUDIO_CONFIG_PATH = Path(_CORE_AUDIO_PATH)
except Exception:
    AUDIO_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "data" / "audio.yaml"


def _log(level: str, msg: str) -> None:
    try:
        from hecos.core.logging import logger as hecos_logger
        getattr(hecos_logger, level, hecos_logger.info)("VOICE_FORGE", msg)
    except Exception:
        print(f"[FishRegistry] [{level.upper()}] {msg}")

def register_fish_preset(
    preset_name: str,
    reference_audio_filename: str,
    reference_text: str,
    inference_preset: str = "Standard & Balanced",
    temperature: float = 0.7,
    top_p: float = 0.7,
    repetition_penalty: float = 1.2,
    max_new_tokens: int = 512,
    chunk_sentences: bool = True
) -> bool:
    """
    Adds or updates a voice preset under fish_speech_presets in audio.yaml.
    """
    if not AUDIO_CONFIG_PATH.is_file():
        _log("warning", f"Cannot register Fish preset '{preset_name}': {AUDIO_CONFIG_PATH} does not exist")
        return False

    try:
        with open(AUDIO_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        if "fish_speech_presets" not in cfg or not isinstance(cfg["fish_speech_presets"], dict):
            cfg["fish_speech_presets"] = {}

        cfg["fish_speech_presets"][preset_name] = {
            "reference_audio": reference_audio_filename,
            "reference_text": reference_text.strip(),
            "inference_preset": inference_preset,
            "temperature": float(temperature),
            "top_p": float(top_p),
            "repetition_penalty": float(repetition_penalty),
            "max_new_tokens": int(max_new_tokens),
            "chunk_sentences": bool(chunk_sentences)
        }

        with open(AUDIO_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)

        _log("info", f"Registered Fish Speech preset '{preset_name}' (ref={reference_audio_filename}) in {AUDIO_CONFIG_PATH}")
        return True
    except Exception as e:
        _log("error", f"Failed to register preset '{preset_name}' in {AUDIO_CONFIG_PATH}: {e}")
        return False

def unregister_fish_preset(preset_name: str) -> bool:
    """Removes a preset from fish_speech_presets in audio.yaml."""
    if not AUDIO_CONFIG_PATH.is_file():
        _log("warning", f"Cannot unregister Fish preset '{preset_name}': {AUDIO_CONFIG_PATH} does not exist")
        return False

    try:
        with open(AUDIO_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        presets = cfg.get("fish_speech_presets", {})
        if preset_name in presets:
            del presets[preset_name]
            with open(AUDIO_CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)
            _log("info", f"Unregistered Fish Speech preset '{preset_name}' from {AUDIO_CONFIG_PATH}")
            return True
        _log("debug", f"Preset '{preset_name}' not present in {AUDIO_CONFIG_PATH}; nothing to unregister")
        return False
    except Exception as e:
        _log("error", f"Failed to unregister preset '{preset_name}' from {AUDIO_CONFIG_PATH}: {e}")
        return False


def rename_fish_preset(old_name: str, new_name: str) -> bool:
    """Renames a preset key under fish_speech_presets in audio.yaml if present."""
    if not old_name or not new_name or old_name == new_name:
        return False
    if not AUDIO_CONFIG_PATH.is_file():
        return False

    try:
        with open(AUDIO_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        presets = cfg.get("fish_speech_presets", {})
        if old_name in presets and new_name not in presets:
            presets[new_name] = presets.pop(old_name)
            with open(AUDIO_CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)
            _log("info", f"Renamed Fish Speech preset '{old_name}' -> '{new_name}' in {AUDIO_CONFIG_PATH}")
            return True
        return False
    except Exception as e:
        _log("error", f"Failed to rename preset '{old_name}' -> '{new_name}': {e}")
        return False
