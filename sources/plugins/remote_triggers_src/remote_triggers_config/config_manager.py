"""
MODULE: Remote Triggers Config Manager
PACKAGE: remote_triggers
"""
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

_THIS_DIR = Path(__file__).parent.resolve()
_DEFAULTS_FILE = _THIS_DIR / "defaults.toml"
_CONFIG_FILE   = _THIS_DIR / "remote_triggers.toml"


def get_config() -> dict:
    if not _CONFIG_FILE.exists():
        _create_from_defaults()
    try:
        return tomllib.loads(_CONFIG_FILE.read_bytes().decode("utf-8"))
    except Exception:
        return tomllib.loads(_DEFAULTS_FILE.read_bytes().decode("utf-8"))


def save_config(data: dict) -> bool:
    if not _HAS_TOMLI_W:
        return False
    try:
        _CONFIG_FILE.write_bytes(tomli_w.dumps(data).encode("utf-8"))
        return True
    except Exception:
        return False


def _create_from_defaults():
    save_config(tomllib.loads(_DEFAULTS_FILE.read_bytes().decode("utf-8")))
