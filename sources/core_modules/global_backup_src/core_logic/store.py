"""
MODULE: Backup Store
DESCRIPTION: Persistent configuration for the Global Backup Orchestrator.
             Reads/writes backup_config.toml inside the package itself
             (hecos/hpm/global_backup/core_logic/backup_config.toml).
             Fully autonomous — no hecos.core path dependency.
"""

import threading
from pathlib import Path

_lock = threading.Lock()

# ── TOML imports ──────────────────────────────────────────────────────────────
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

try:
    import tomli_w
    _HAS_TOMLI_W = True
except ImportError:
    _HAS_TOMLI_W = False

# ── Config file path: lives inside the package, not in hecos/config/data ─────
_THIS_DIR = Path(__file__).parent.resolve()
_CONFIG_FILE = _THIS_DIR / "backup_config.toml"
_ROOT_KEY = "backup"

# ── Defaults ──────────────────────────────────────────────────────────────────
_DEFAULT_CONFIG = {
    "enabled": False,
    "schedule_preset": "daily_2am",
    "schedule_cron": "0 2 * * *",
    "destination": "",
    "keep_last": 7,
    "last_backup": "",
    "last_result": "",
    "last_details": {},
    "modules": [],
}

# Preset schedules — shown as dropdown in the UI
SCHEDULE_PRESETS = {
    "every_6h":    {"label": "backup_preset_6h",    "cron": "0 */6 * * *"},
    "every_12h":   {"label": "backup_preset_12h",   "cron": "0 */12 * * *"},
    "daily_2am":   {"label": "backup_preset_daily",  "cron": "0 2 * * *"},
    "weekly_sun":  {"label": "backup_preset_weekly", "cron": "0 3 * * 0"},
    "custom":      {"label": "backup_preset_custom", "cron": ""},
}


def _read_toml() -> dict:
    """Read the TOML config file, returning the [backup] section dict."""
    if not _CONFIG_FILE.exists():
        # First run: write defaults
        _write_toml(dict(_DEFAULT_CONFIG))
        return dict(_DEFAULT_CONFIG)
    try:
        raw = tomllib.loads(_CONFIG_FILE.read_bytes().decode("utf-8"))
        return raw.get(_ROOT_KEY, dict(_DEFAULT_CONFIG))
    except Exception as e:
        print(f"[BACKUP STORE] Failed to read config: {e}")
        return dict(_DEFAULT_CONFIG)


def _write_toml(section: dict) -> bool:
    """Write the [backup] section to backup_config.toml."""
    if not _HAS_TOMLI_W:
        print("[BACKUP STORE] tomli_w not available, cannot save config.")
        return False
    with _lock:
        try:
            # Preserve any other top-level TOML sections
            existing = {}
            if _CONFIG_FILE.exists():
                try:
                    existing = tomllib.loads(_CONFIG_FILE.read_bytes().decode("utf-8"))
                except Exception:
                    existing = {}
            existing[_ROOT_KEY] = section
            _CONFIG_FILE.write_bytes(tomli_w.dumps(existing).encode("utf-8"))
            return True
        except Exception as e:
            print(f"[BACKUP STORE] Failed to save config: {e}")
            return False


def load() -> dict:
    """Load backup config from disk, merging with defaults. Discovers HPM modules."""
    cfg = dict(_DEFAULT_CONFIG)
    cfg.update(_read_toml())

    # modules must be a list (list of enabled module IDs)
    if not isinstance(cfg.get("modules"), list):
        cfg["modules"] = []

    return cfg


def save(cfg: dict) -> bool:
    """Persist backup config to the package-local TOML file."""
    # Sanitize: ensure modules is always a list
    if not isinstance(cfg.get("modules"), list):
        cfg["modules"] = []
    # Remove None values — TOML doesn't have null, use empty string
    for k in ("last_backup", "last_result"):
        if cfg.get(k) is None:
            cfg[k] = ""
    return _write_toml(cfg)


def update_last_run(result: str, timestamp: str, details: dict = None) -> None:
    """Update last_backup, last_result and last_details fields atomically."""
    cfg = load()
    cfg["last_backup"] = timestamp
    cfg["last_result"] = result
    cfg["last_details"] = details or {}
    save(cfg)


def get_cron_for_preset(preset_key: str, custom_cron: str = "") -> str:
    """Return the cron expression for a given preset key."""
    if preset_key == "custom":
        return custom_cron
    return SCHEDULE_PRESETS.get(preset_key, SCHEDULE_PRESETS["daily_2am"])["cron"]
