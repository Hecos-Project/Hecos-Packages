"""
weather_pro package — Config Manager (Autonomous TOML)
Reads/writes the package's own weather_pro.toml without touching Hecos core config.
"""
import os
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

try:
    import tomli_w
    _HAS_TOMLI_W = True
except ImportError:
    _HAS_TOMLI_W = False

try:
    from hecos.core.logging import logger
except ImportError:
    class _L:
        def info(self, *a): print("[WEATHER_PRO CONFIG]", *a)
        def error(self, *a): print("[WEATHER_PRO CONFIG ERR]", *a)
        def warning(self, *a): print("[WEATHER_PRO CONFIG WARN]", *a)
    logger = _L()

# ── Path resolution ────────────────────────────────────────────────────────────
# When installed by HPM, the package lives in:
#   hecos/plugins/weather_pro/
# This file is at: weather_pro/weather_pro_config/config_manager.py

_THIS_DIR      = Path(__file__).parent.resolve()
_DEFAULTS_FILE = _THIS_DIR / "defaults.toml"
_CONFIG_FILE   = _THIS_DIR / "weather_pro.toml"


def _load_defaults() -> dict:
    """Load the shipped defaults.toml."""
    try:
        return tomllib.loads(_DEFAULTS_FILE.read_bytes().decode("utf-8"))
    except Exception as e:
        logger.error(f"[WEATHER_PRO] Could not load defaults: {e}")
        return {"weather_pro": {}}


def get_config() -> dict:
    """
    Returns the full weather_pro config dict.
    If weather_pro.toml doesn't exist yet, creates it from defaults.
    """
    if not _CONFIG_FILE.exists():
        _create_from_defaults()

    try:
        raw = tomllib.loads(_CONFIG_FILE.read_bytes().decode("utf-8"))
        return raw
    except Exception as e:
        logger.error(f"[WEATHER_PRO] Failed to read config: {e}")
        return _load_defaults()


def get_weather_pro_config() -> dict:
    """Returns just the [weather_pro] section."""
    return get_config().get("weather_pro", {})


def save_config(data: dict) -> bool:
    """
    Saves the full config dict to weather_pro.toml.
    data should be the full dict (including top-level [weather_pro] key).
    """
    if not _HAS_TOMLI_W:
        logger.error("[WEATHER_PRO] tomli_w not installed. Cannot save config. Run: pip install tomli_w")
        return False
    try:
        toml_bytes = tomli_w.dumps(data).encode("utf-8")
        _CONFIG_FILE.write_bytes(toml_bytes)
        logger.info("[WEATHER_PRO] Config saved.")
        return True
    except Exception as e:
        logger.error(f"[WEATHER_PRO] Failed to save config: {e}")
        return False


def save_weather_pro_section(section: dict) -> bool:
    """
    Saves just the [weather_pro] section, merging with existing config.
    """
    cfg = get_config()
    existing = cfg.get("weather_pro", {})
    existing.update(section)
    cfg["weather_pro"] = existing
    return save_config(cfg)


def _create_from_defaults():
    """Copy defaults.toml content to weather_pro.toml."""
    try:
        defaults = _load_defaults()
        save_config(defaults)
        logger.info("[WEATHER_PRO] Created weather_pro.toml from defaults.")
    except Exception as e:
        logger.error(f"[WEATHER_PRO] Could not create config from defaults: {e}")
