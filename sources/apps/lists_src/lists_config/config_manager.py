"""
lists package — Config Manager (Pydantic + TOML)
Reads/writes the package's own lists.toml using Hecos HPMBaseConfigManager.
"""
from pathlib import Path
from pydantic import BaseModel

try:
    from hecos.core.logging import logger
    from hecos.core.package_manager.config import HPMBaseConfigManager
except ImportError:
    class _L:
        def info(self, *a):    print("[LISTS CONFIG]", *a)
        def error(self, *a):   print("[LISTS CONFIG ERR]", *a)
        def warning(self, *a): print("[LISTS CONFIG WARN]", *a)
    logger = _L()
    class HPMBaseConfigManager:
        pass


class ListsConfig(BaseModel):
    enabled: bool = True
    lazy_load: bool = True
    default_icon: str = "📋"
    max_items_per_list: int = 500
    max_lists: int = 50
    show_completed: bool = True


_THIS_DIR    = Path(__file__).parent.resolve()
_CONFIG_FILE = _THIS_DIR / "lists.toml"

_manager = None
if hasattr(HPMBaseConfigManager, "get"):
    _manager = HPMBaseConfigManager(ListsConfig, _CONFIG_FILE, "lists")


def get_config() -> dict:
    """Returns the full lists config dict for backwards compatibility."""
    if _manager:
        obj = _manager.get()
        return {"lists": obj.model_dump(mode='json')}
    return {"lists": ListsConfig().model_dump(mode='json')}


def get_lists_config() -> dict:
    """Returns just the [lists] section."""
    return get_config().get("lists", {})


def save_config(data: dict) -> bool:
    """Saves the full config dict to lists.toml."""
    if _manager and "lists" in data:
        try:
            obj = ListsConfig.model_validate(data["lists"])
            return _manager.save(obj)
        except Exception as e:
            logger.error(f"[LISTS] Validation error on save: {e}")
            return False
    return False


def save_lists_section(section: dict) -> bool:
    """Saves just the [lists] section, merging with existing config."""
    if not _manager: return False
    current = _manager.get().model_dump(mode='json')
    current.update(section)
    try:
        obj = ListsConfig.model_validate(current)
        return _manager.save(obj)
    except Exception as e:
        logger.error(f"[LISTS] Validation error on merge: {e}")
        return False
