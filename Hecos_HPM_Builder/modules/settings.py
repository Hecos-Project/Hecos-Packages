import os
import json
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # pip install tomli
    except ImportError:
        tomllib = None

CONFIG_TOML = Path(__file__).parent.parent / "config.toml"

DEFAULT_CONFIG = {
    "hecos_path": "C:/Hecos/hecos",
    "packages_path": "C:/Hecos-Packages/packages",
    "src_path": "C:/Hecos-Packages",
    "private_key_path": "C:/hpm_private.pem",
    "defaults": {
        "author": "Hecos Developer",
        "license": "MIT",
        "description": "Package description",
        "version": "1.0.0",
        "hecos_min_version": "0.35.0"
    }
}

_config_cache = None

def _parse_toml(path: Path) -> dict:
    if tomllib is not None:
        with open(path, "rb") as f:
            return tomllib.load(f)
    result = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line and not line.startswith("["):
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"')
                result[key] = val
    return result

def load_config() -> dict:
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    if CONFIG_TOML.exists():
        try:
            _config_cache = _parse_toml(CONFIG_TOML)
            # Merge defaults
            for k, v in DEFAULT_CONFIG.items():
                if k not in _config_cache:
                    _config_cache[k] = v
            # Merge defaults section
            if "defaults" not in _config_cache:
                _config_cache["defaults"] = DEFAULT_CONFIG["defaults"]
            else:
                for dk, dv in DEFAULT_CONFIG["defaults"].items():
                    if dk not in _config_cache["defaults"]:
                        _config_cache["defaults"][dk] = dv
            return _config_cache
        except Exception as e:
            print(f"[ERROR] Cannot read config.toml: {e}")
    
    _config_cache = DEFAULT_CONFIG.copy()
    return _config_cache


def get_hecos_root() -> Path:
    return Path(load_config().get("hecos_path", DEFAULT_CONFIG["hecos_path"])).resolve()

def get_trusted_keys_dir() -> Path:
    return get_hecos_root() / "data" / "trusted_keys"

def get_private_key_path() -> Path:
    """Returns the path to the private signing key from config, or the default location."""
    configured = load_config().get("private_key_path")
    if configured:
        return Path(configured).resolve()
    # Fallback: look inside trusted_keys (legacy behavior)
    return get_trusted_keys_dir() / "hpm_private.pem"

def get_packages_dir() -> Path:
    return Path(load_config().get("packages_path", DEFAULT_CONFIG["packages_path"])).resolve()

def get_src_dir() -> Path:
    """Returns the directory where *_src source folders live."""
    return Path(load_config().get("src_path", DEFAULT_CONFIG["src_path"])).resolve()
