"""
weather_pro package — Config Manager (Pydantic + TOML)
Reads/writes the package's own weather_pro.toml using Hecos HPMBaseConfigManager.
"""
import os
from pathlib import Path
from pydantic import BaseModel

try:
    from hecos.core.logging import logger
    from hecos.core.package_manager.config import HPMBaseConfigManager
except ImportError:
    class _L:
        def info(self, *a): print("[WEATHER_PRO CONFIG]", *a)
        def error(self, *a): print("[WEATHER_PRO CONFIG ERR]", *a)
        def warning(self, *a): print("[WEATHER_PRO CONFIG WARN]", *a)
    logger = _L()
    class HPMBaseConfigManager:
        pass


class WeatherProConfig(BaseModel):
    enabled: bool = True
    default_city: str = ""
    units: str = "celsius"


_THIS_DIR      = Path(__file__).parent.resolve()
_CONFIG_FILE   = _THIS_DIR / "weather_pro.toml"

_manager = None
if hasattr(HPMBaseConfigManager, "get"):
    _manager = HPMBaseConfigManager(WeatherProConfig, _CONFIG_FILE, "weather_pro")


def get_config() -> dict:
    """Returns the full weather_pro config dict for backwards compatibility."""
    if _manager:
        obj = _manager.get()
        return {"weather_pro": obj.model_dump(mode='json')}
    return {"weather_pro": WeatherProConfig().model_dump(mode='json')}


def get_weather_pro_config() -> dict:
    """Returns just the [weather_pro] section."""
    return get_config().get("weather_pro", {})


def save_config(data: dict) -> bool:
    """Saves the full config dict to weather_pro.toml."""
    if _manager and "weather_pro" in data:
        try:
            obj = WeatherProConfig.model_validate(data["weather_pro"])
            return _manager.save(obj)
        except Exception as e:
            logger.error(f"[WEATHER_PRO] Validation error on save: {e}")
            return False
    return False


def save_weather_pro_section(section: dict) -> bool:
    """Saves just the [weather_pro] section, merging with existing config."""
    if not _manager: return False
    current = _manager.get().model_dump(mode='json')
    current.update(section)
    try:
        obj = WeatherProConfig.model_validate(current)
        return _manager.save(obj)
    except Exception as e:
        logger.error(f"[WEATHER_PRO] Validation error on merge: {e}")
        return False
