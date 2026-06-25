import os
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent / "config.json"

DEFAULT_CONFIG = {
    "hecos_path": "C:/Hecos/hecos",
    "packages_path": "C:/Hecos-Packages"
}

_config_cache = None

def load_config() -> dict:
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        _config_cache = DEFAULT_CONFIG.copy()
    else:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                _config_cache = json.load(f)
                
            # Merge defaults if missing keys
            save_needed = False
            for k, v in DEFAULT_CONFIG.items():
                if k not in _config_cache:
                    _config_cache[k] = v
                    save_needed = True
            
            if save_needed:
                save_config(_config_cache)
                
        except Exception as e:
            print(f"[ERROR] Impossibile leggere config.json: {e}")
            _config_cache = DEFAULT_CONFIG.copy()
            
    return _config_cache

def save_config(new_config: dict):
    global _config_cache
    _config_cache = new_config
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(new_config, f, indent=4)

def get_hecos_root() -> Path:
    return Path(load_config().get("hecos_path", DEFAULT_CONFIG["hecos_path"])).resolve()

def get_trusted_keys_dir() -> Path:
    return get_hecos_root() / "data" / "trusted_keys"

def get_packages_dir() -> Path:
    return Path(load_config().get("packages_path", DEFAULT_CONFIG["packages_path"])).resolve()
