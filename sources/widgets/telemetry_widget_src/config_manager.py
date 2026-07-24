"""
telemetry_widget package — Config Manager (Pydantic + TOML)
Reads/writes the package's own telemetry_widget.toml using Hecos HPMBaseConfigManager.
Completely autonomous: zero dependency on core plugins.yaml or plugins_schema.py.
"""
from pathlib import Path
from pydantic import BaseModel

try:
    from hecos.core.logging import logger
    from hecos.core.package_manager.config import HPMBaseConfigManager
except ImportError:
    class _L:
        def info(self, *a): print("[TELEMETRY_WIDGET CONFIG]", *a)
        def error(self, *a): print("[TELEMETRY_WIDGET CONFIG ERR]", *a)
        def warning(self, *a): print("[TELEMETRY_WIDGET CONFIG WARN]", *a)
        def debug(self, *a): pass
    logger = _L()
    class HPMBaseConfigManager:
        pass


class TelemetryWidgetConfig(BaseModel):
    """Config schema for the System Telemetry WebUI widget."""
    track_cpu:  bool = False
    track_ram:  bool = False
    track_vram: bool = False


_THIS_DIR = Path(__file__).parent.resolve() / "telemetry_widget_config"
if not _THIS_DIR.exists():
    _THIS_DIR = Path(__file__).parent.resolve()

_CONFIG_FILE = _THIS_DIR / "telemetry_widget.toml"

_manager = None
if hasattr(HPMBaseConfigManager, "get"):
    _manager = HPMBaseConfigManager(TelemetryWidgetConfig, _CONFIG_FILE, "telemetry_widget")


def get_config() -> TelemetryWidgetConfig:
    """Returns the validated TelemetryWidgetConfig model."""
    if _manager:
        return _manager.get()
    return TelemetryWidgetConfig()


def save_config(data: dict) -> bool:
    """Saves the config dict to telemetry_widget.toml."""
    if _manager:
        try:
            obj = TelemetryWidgetConfig.model_validate(data)
            return _manager.save(obj)
        except Exception as e:
            logger.error(f"[TELEMETRY_WIDGET] Validation error on save: {e}")
            return False
    return False
