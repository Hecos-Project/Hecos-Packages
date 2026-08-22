"""
Notifications Center — Config Manager (Pydantic + TOML)
Reads/writes notifications.toml stored alongside the package files.
Uses HPMBaseConfigManager — same pattern as Calendar, Global Backup, etc.
No YAML, no JSON, no central hecos/config/data files touched.
"""
from pathlib import Path
from typing import Dict, List, Any
from pydantic import BaseModel, Field, field_validator

try:
    from hecos.core.logging import logger
    from hecos.core.package_manager.config import HPMBaseConfigManager
except ImportError:
    class _L:
        def info(self, *a):    print("[NOTIFICATIONS CONFIG]", *a)
        def error(self, *a):   print("[NOTIFICATIONS CONFIG ERR]", *a)
        def warning(self, *a): print("[NOTIFICATIONS CONFIG WARN]", *a)
        def debug(self, *a):   pass
    logger = _L()
    HPMBaseConfigManager = None


# ── Pydantic schema ────────────────────────────────────────────────────────────

class NotificationsConfig(BaseModel):
    destinations: Dict[str, str] = Field(default_factory=dict)
    rules: Dict[str, List[str]] = Field(default_factory=lambda: {
        "system_boot":           [],
        "system_shutdown":       [],
        "system_error":          [],
        "flow_started":          [],
        "flow_completed":        [],
        "flow_failed":           [],
        "package_installed":     [],
        "package_updated":       [],
        "package_removed":       [],
        "security_login_failed": [],
        "security_new_device":   [],
        "backup_started":        [],
        "backup_completed":      [],
        "backup_failed":         [],
        "custom":                [],
    })
    event_templates: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('event_templates', mode='before')
    def migrate_event_templates(cls, v):
        if not isinstance(v, dict):
            return {}
        migrated = {}
        for k, val in v.items():
            if isinstance(val, str):
                migrated[k] = {"template_id": val, "variables": {}}
            elif isinstance(val, dict):
                migrated[k] = val
        return migrated


# ── Config file path (same dir as this file) ──────────────────────────────────

_THIS_DIR    = Path(__file__).parent.resolve()
_CONFIG_FILE = _THIS_DIR / "notifications.toml"

_manager = None
if HPMBaseConfigManager is not None:
    _manager = HPMBaseConfigManager(NotificationsConfig, _CONFIG_FILE, "notifications")


# ── Public API ────────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Returns the full notifications config as a plain dict."""
    if _manager:
        return _manager.get().model_dump(mode='json')
    return NotificationsConfig().model_dump(mode='json')


def save_config(new_config: dict) -> bool:
    """Validates and saves a new config dict to notifications.toml."""
    if not _manager:
        logger.error("[NOTIFICATIONS] HPMBaseConfigManager not available — cannot save.")
        return False
    try:
        obj = NotificationsConfig.model_validate(new_config)
        return _manager.save(obj)
    except Exception as e:
        logger.error(f"[NOTIFICATIONS] Validation error on save: {e}")
        return False
