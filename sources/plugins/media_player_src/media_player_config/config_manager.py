import os
from pathlib import Path
try:
    import tomllib
except ImportError:
    import tomli as tomllib
import tomli_w

_THIS_DIR    = Path(__file__).parent.resolve()
_DEFAULTS    = _THIS_DIR / "defaults.toml"
_CONFIG_FILE = _THIS_DIR / "media_player.toml"

def get_config() -> dict:
    if not _CONFIG_FILE.exists():
        _CONFIG_FILE.write_bytes(_DEFAULTS.read_bytes())
    return tomllib.loads(_CONFIG_FILE.read_bytes().decode("utf-8"))

def save_config(data: dict) -> bool:
    _CONFIG_FILE.write_bytes(tomli_w.dumps(data).encode("utf-8"))
    return True
