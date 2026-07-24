"""
Calendar Package — Config Manager (Pydantic + TOML)
Reads/writes the package's own calendar.toml using HPMBaseConfigManager.
All state is local to this package. No central hecos yaml files are touched.
"""
from pathlib import Path
from pydantic import BaseModel, Field

try:
    from hecos.core.logging import logger
    from hecos.core.package_manager.config import HPMBaseConfigManager
except ImportError:
    class _L:
        def info(self, *a):    print("[CALENDAR CONFIG]", *a)
        def error(self, *a):   print("[CALENDAR CONFIG ERR]", *a)
        def warning(self, *a): print("[CALENDAR CONFIG WARN]", *a)
    logger = _L()
    class HPMBaseConfigManager:
        pass


class CalendarConfig(BaseModel):
    calendar_locale: str = "it-IT"
    calendar_country: str = "IT"
    bg_color: str = ""
    bg_image: str = ""
    calendar_sync_urls: list[str] = Field(default_factory=list)
    # 7 strings, index 0=Sun, 1=Mon, ..., 6=Sat (FullCalendar convention)
    # Stored as a plain TOML array — no alias tricks needed.
    day_colors: list[str] = Field(default_factory=lambda: [""] * 7)


_THIS_DIR    = Path(__file__).parent.resolve()
_CONFIG_FILE = _THIS_DIR / "calendar.toml"

_manager = None
if hasattr(HPMBaseConfigManager, "get"):
    _manager = HPMBaseConfigManager(CalendarConfig, _CONFIG_FILE, "calendar")


def get_config() -> dict:
    """Returns the full calendar config dict for backwards compatibility."""
    if _manager:
        obj = _manager.get()
        return {"calendar": obj.model_dump(mode='json')}
    return {"calendar": CalendarConfig().model_dump(mode='json')}


def get_calendar_config() -> dict:
    """Returns just the [calendar] section."""
    return get_config().get("calendar", {})


def save_config(data: dict) -> bool:
    """Saves the full config dict to calendar.toml."""
    if _manager and "calendar" in data:
        try:
            obj = CalendarConfig.model_validate(data["calendar"])
            return _manager.save(obj)
        except Exception as e:
            logger.error(f"[CALENDAR] Validation error on save: {e}")
            return False
    return False


def save_calendar_section(section: dict) -> bool:
    """Saves just the [calendar] section, merging with existing config."""
    if not _manager:
        return False
    current = _manager.get().model_dump(mode='json')
    current.update(section)
    try:
        obj = CalendarConfig.model_validate(current)
        return _manager.save(obj)
    except Exception as e:
        logger.error(f"[CALENDAR-CFG] Error saving calendar.toml: {e}")
        return False
