"""
webcam package — Config Manager (Pydantic + TOML)
Reads/writes the package's own webcam.toml using Hecos HPMBaseConfigManager.
"""
from pathlib import Path
from pydantic import BaseModel

try:
    from hecos.core.logging import logger
    from hecos.core.package_manager.config import HPMBaseConfigManager
except ImportError:
    class _L:
        def info(self, *a): print("[WEBCAM CONFIG]", *a)
        def error(self, *a): print("[WEBCAM CONFIG ERR]", *a)
        def warning(self, *a): print("[WEBCAM CONFIG WARN]", *a)
    logger = _L()
    class HPMBaseConfigManager:
        pass


class WebcamConfig(BaseModel):
    camera_index: int = 0
    image_format: str = "jpg"
    save_directory: str = "snapshots"
    stabilization_delay: float = 0.5


_THIS_DIR = Path(__file__).parent.resolve() / "webcam_config"
if not _THIS_DIR.exists():
    _THIS_DIR = Path(__file__).parent.resolve()

_CONFIG_FILE = _THIS_DIR / "webcam.toml"

_manager = None
if hasattr(HPMBaseConfigManager, "get"):
    _manager = HPMBaseConfigManager(WebcamConfig, _CONFIG_FILE, "webcam")


def get_config() -> dict:
    """Returns the full webcam config dict for backwards compatibility."""
    if _manager:
        obj = _manager.get()
        return {"webcam": obj.model_dump(mode='json')}
    return {"webcam": WebcamConfig().model_dump(mode='json')}


def get_webcam_config() -> dict:
    """Returns just the [webcam] section."""
    return get_config().get("webcam", {})


def save_config(data: dict) -> bool:
    """Saves the full config dict to webcam.toml."""
    if _manager and "webcam" in data:
        try:
            obj = WebcamConfig.model_validate(data["webcam"])
            return _manager.save(obj)
        except Exception as e:
            logger.error(f"[WEBCAM] Validation error on save: {e}")
            return False
    return False


class ConfigManager:
    """Wrapper to match old API usage in main.py"""
    def __init__(self):
        self.config = get_webcam_config()
        
    def get_plugin_config(self, tag, key, default):
        return self.config.get(key, default)

