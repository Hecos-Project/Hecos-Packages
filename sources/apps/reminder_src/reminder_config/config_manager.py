"""
reminder package — Config Manager (Pydantic + TOML)
Reads/writes the package's own reminder.toml using Hecos HPMBaseConfigManager.
"""
from pathlib import Path
from pydantic import BaseModel

try:
    from hecos.core.logging import logger
    from hecos.core.package_manager.config import HPMBaseConfigManager
except ImportError:
    class _L:
        def info(self, *a):    print("[REMINDER CONFIG]", *a)
        def error(self, *a):   print("[REMINDER CONFIG ERR]", *a)
        def warning(self, *a): print("[REMINDER CONFIG WARN]", *a)
    logger = _L()
    class HPMBaseConfigManager:
        pass


class ReminderConfig(BaseModel):
    reminder_mode: str = "ringtone"
    ringtone_path: str = "Default_System_Alert.mp3"
    time_format: str = "24h"
    max_reminders: int = 50
    snooze_default_minutes: int = 15
    reminder_snooze_ui: bool = False


_THIS_DIR    = Path(__file__).parent.resolve()
_CONFIG_FILE = _THIS_DIR / "reminder.toml"

_manager = None
if hasattr(HPMBaseConfigManager, "get"):
    _manager = HPMBaseConfigManager(ReminderConfig, _CONFIG_FILE, "reminder")
    # Auto-create reminder.toml with defaults on fresh install if it doesn't exist
    if not _CONFIG_FILE.exists():
        try:
            _manager.save(ReminderConfig())
            logger.info("[REMINDER CONFIG] Created default reminder.toml")
        except Exception as _e:
            logger.error(f"[REMINDER CONFIG] Could not create default reminder.toml: {_e}")


def get_config() -> dict:
    """Returns the full reminder config dict for backwards compatibility."""
    if _manager:
        obj = _manager.get()
        return {"reminder": obj.model_dump(mode='json')}
    return {"reminder": ReminderConfig().model_dump(mode='json')}


def get_reminder_config() -> dict:
    """Returns just the [reminder] section."""
    return get_config().get("reminder", {})


def save_config(data: dict) -> bool:
    """Saves the full config dict to reminder.toml."""
    if _manager and "reminder" in data:
        try:
            obj = ReminderConfig.model_validate(data["reminder"])
            return _manager.save(obj)
        except Exception as e:
            logger.error(f"[REMINDER] Validation error on save: {e}")
            return False
    return False


def save_reminder_section(section: dict) -> bool:
    """Saves just the [reminder] section, merging with existing config."""
    if not _manager: return False
    current = _manager.get().model_dump(mode='json')
    current.update(section)
    try:
        obj = ReminderConfig.model_validate(current)
        return _manager.save(obj)
    except Exception as e:
        logger.error(f"[REMINDER] Validation error on merge: {e}")
        return False

