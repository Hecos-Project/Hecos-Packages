"""
image_gen package — Config Manager (Pydantic + TOML)
Reads/writes the package's own image_gen.toml.
Fully autonomous: no hecos.core dependency.
"""
import os
from pathlib import Path
from typing import Any, Dict
from pydantic import BaseModel, Field

try:
    import tomllib                         # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib            # pip install tomli
    except ImportError:
        tomllib = None                     # type: ignore

try:
    import tomli_w                         # pip install tomli-w
    _HAS_TOMLI_W = True
except ImportError:
    _HAS_TOMLI_W = False

try:
    from hecos.core.logging import logger
except ImportError:
    class _L:
        def info(self, *a):  print("[IMAGE_GEN_CONFIG]", *a)
        def debug(self, *a): pass
        def error(self, *a): print("[IMAGE_GEN_CONFIG ERR]", *a)
    logger = _L()


# -- Local config sub-model --------------------------------------------------

class LocalConfig(BaseModel):
    enabled: bool = False
    host: str = "http://localhost:7801"
    backend: str = "swarmui"


class ImageGenConfig(BaseModel):
    # -- Core ----------------------------------------------------------------
    enabled: bool = True
    provider: str = "pollinations"
    model: str = "flux"
    nologo: bool = True
    api_key: str = ""
    api_key_comment: str = ""
    hf_provider: str = "hf-inference"

    # -- Dimensions ----------------------------------------------------------
    aspect_ratio: str = "1:1"
    width: int = 1024
    height: int = 1024

    # -- Sampling ------------------------------------------------------------
    seed: int = -1
    last_seed: int = -1
    sampler: str = "euler"
    scheduler: str = "simple"
    guidance_scale: float = 0.0
    num_inference_steps: int = 4

    # -- Negative Prompt -----------------------------------------------------
    enable_negative_prompt: bool = False
    negative_prompt: str = ""

    # -- Prompt Enhancement --------------------------------------------------
    auto_enrich: bool = False
    enrich_keywords: str = ""
    style: str = "none"
    optimize_for_flux: bool = True
    vae: str = ""                           # Selected VAE
    loras: list = Field(default_factory=list) # Selected LoRAs (names)
    flux_refiner_instructions: str = (
        "Convert keywords into a descriptive natural language paragraph for Flux. "
        "Output ONLY the optimised prompt, no preamble."
    )

    # -- Debug / Chat Options ------------------------------------------------
    show_metadata_in_chat: bool = True

    # -- Preset System -------------------------------------------------------
    presets: Dict[str, Any] = Field(default_factory=dict)
    active_preset: str = ""
    # Which user preset should be auto-loaded at startup (empty = none)
    default_preset: str = ""

    # -- Legacy Profiles (kept for migration, superseded by default_preset) --
    profiles: Dict[str, Any] = Field(default_factory=dict)
    default_profile: str = ""

    # -- Custom Models -------------------------------------------------------
    custom_hf_models: list = Field(default_factory=list)

    # -- Horde ---------------------------------------------------------------
    horde_api_key: str = ""
    horde_nsfw: bool = True
    horde_worker_blacklist: str = ""     # Comma-separated worker names to exclude

    # -- Cloud ---------------------------------------------------------------
    cloud_enabled: bool = False
    routing_override: str = ""

    # -- Local Generation ----------------------------------------------------
    local: Dict[str, Any] = Field(default_factory=lambda: LocalConfig().model_dump(mode='json'))


_THIS_DIR = Path(__file__).parent.resolve()

# Dynamically locate Hecos data directory to ensure config survives reinstalls
try:
    import hecos
    _HECOS_ROOT = Path(hecos.__file__).parent
    _DATA_DIR = _HECOS_ROOT / "data"
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE = _DATA_DIR / "image_gen.toml"
except Exception:
    # Fallback for standalone/dev environments
    _CONFIG_FILE = _THIS_DIR / "image_gen.toml"

_ROOT_KEY = "image_gen"


def _read_toml() -> dict:
    """Read the TOML config file directly, return the root dict."""
    if not _CONFIG_FILE.exists():
        defaults = ImageGenConfig().model_dump(mode='json')
        try:
            if _HAS_TOMLI_W:
                _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
                _CONFIG_FILE.write_bytes(tomli_w.dumps({_ROOT_KEY: defaults}).encode("utf-8"))
                logger.info("[IMAGE_GEN_CONFIG] Default config created.")
        except Exception:
            pass
        return defaults
    try:
        raw = tomllib.loads(_CONFIG_FILE.read_bytes().decode("utf-8"))
        return raw.get(_ROOT_KEY, {})
    except Exception as e:
        logger.error(f"[IMAGE_GEN_CONFIG] Failed to read config: {e}")
        return {}


def _write_toml(section: dict) -> bool:
    """Write just the image_gen section to the TOML file."""
    if not _HAS_TOMLI_W:
        logger.error("[IMAGE_GEN_CONFIG] tomli_w not available, cannot save.")
        return False
    try:
        existing = {}
        if _CONFIG_FILE.exists():
            try:
                existing = tomllib.loads(_CONFIG_FILE.read_bytes().decode("utf-8"))
            except Exception:
                existing = {}
        existing[_ROOT_KEY] = section
        _CONFIG_FILE.write_bytes(tomli_w.dumps(existing).encode("utf-8"))
        logger.debug("[IMAGE_GEN_CONFIG] Config saved.")
        return True
    except Exception as e:
        logger.error(f"[IMAGE_GEN_CONFIG] Failed to save config: {e}")
        return False


def get_config() -> dict:
    """Returns the full image_gen config dict."""
    raw = _read_toml()
    try:
        obj = ImageGenConfig.model_validate(raw)
    except Exception:
        obj = ImageGenConfig()
    return {_ROOT_KEY: obj.model_dump(mode='json')}


def get_image_gen_config() -> dict:
    """Returns just the [image_gen] section."""
    return get_config().get(_ROOT_KEY, {})


def save_config(data: dict) -> bool:
    """Saves the full config dict to image_gen.toml."""
    if _ROOT_KEY not in data:
        return False
    try:
        incoming = data[_ROOT_KEY]
        if "local" not in incoming:
            existing_local = get_image_gen_config().get("local", {})
            if existing_local:
                incoming["local"] = existing_local
        obj = ImageGenConfig.model_validate(incoming)
        return _write_toml(obj.model_dump(mode='json'))
    except Exception as e:
        logger.error(f"[IMAGE_GEN_CONFIG] Validation error on save: {e}")
        return False


def save_image_gen_section(section: dict) -> bool:
    """Saves just the [image_gen] section, merging with existing config."""
    current = get_image_gen_config()
    current.update(section)
    try:
        obj = ImageGenConfig.model_validate(current)
        return _write_toml(obj.model_dump(mode='json'))
    except Exception as e:
        logger.error(f"[IMAGE_GEN_CONFIG] Validation error on merge: {e}")
        return False


# -- Keys captured in a full snapshot ----------------------------------------

_SNAPSHOT_KEYS = [
    "provider", "model", "hf_provider", "aspect_ratio", "width", "height",
    "seed", "sampler", "scheduler", "guidance_scale", "num_inference_steps",
    "enable_negative_prompt", "negative_prompt", "auto_enrich",
    "enrich_keywords", "style", "nologo", "optimize_for_flux",
    "show_metadata_in_chat", "active_preset", "vae", "loras",
    "cloud_enabled", "api_key", "horde_api_key", "horde_nsfw",
    "horde_worker_blacklist", "routing_override",
]

_PROFILE_KEYS = _SNAPSHOT_KEYS  # backward-compat alias


# -- Default Preset ----------------------------------------------------------

def get_default_preset() -> str:
    """Returns the name of the preset auto-loaded at startup."""
    return get_image_gen_config().get("default_preset", "")


def set_default_preset(name: str) -> bool:
    """Mark a preset as the default auto-loaded at startup. Empty clears."""
    cfg = get_image_gen_config()
    cfg["default_preset"] = name.strip()
    try:
        obj = ImageGenConfig.model_validate(cfg)
        ok = _write_toml(obj.model_dump(mode='json'))
        if ok:
            logger.info(f"[IMAGE_GEN_CONFIG] Default preset set to '{name or '(none)'}'.")
        return ok
    except Exception as e:
        logger.error(f"[IMAGE_GEN_CONFIG] Failed setting default preset: {e}")
        return False


# -- Effective Config (applies default preset at startup) --------------------

def get_effective_config() -> dict:
    """Returns image_gen config with the default preset applied.
    Falls back to legacy default_profile for backward compat."""
    cfg = get_image_gen_config()

    # 1. New: default_preset
    default_preset_name = cfg.get("default_preset", "")
    if default_preset_name:
        preset = cfg.get("presets", {}).get(default_preset_name)
        if preset:
            for key in _SNAPSHOT_KEYS:
                if key in preset:
                    cfg[key] = preset[key]
            logger.debug(f"[IMAGE_GEN_CONFIG] Applied default preset '{default_preset_name}'.")
            return cfg

    # 2. Legacy fallback: default_profile
    default_profile_name = cfg.get("default_profile", "")
    if default_profile_name:
        profile = cfg.get("profiles", {}).get(default_profile_name)
        if profile:
            for key in _SNAPSHOT_KEYS:
                if key in profile:
                    cfg[key] = profile[key]
            logger.debug(f"[IMAGE_GEN_CONFIG] Applied legacy default profile '{default_profile_name}'.")

    return cfg


# -- Legacy Profile API (kept for backward compat) ---------------------------

def list_profiles() -> list:
    cfg = get_image_gen_config()
    profiles = cfg.get("profiles", {})
    default = cfg.get("default_profile", "")
    return [
        {"name": name, "is_default": (name == default)}
        for name in sorted(profiles.keys())
    ]


def save_profile(name: str, snapshot: dict) -> bool:
    if not name or not name.strip():
        return False
    name = name.strip()
    filtered = {k: v for k, v in snapshot.items() if k in _PROFILE_KEYS}
    cfg = get_image_gen_config()
    profiles = cfg.get("profiles", {})
    profiles[name] = filtered
    cfg["profiles"] = profiles
    try:
        obj = ImageGenConfig.model_validate(cfg)
        ok = _write_toml(obj.model_dump(mode='json'))
        if ok:
            logger.info(f"[IMAGE_GEN_CONFIG] Profile '{name}' saved.")
        return ok
    except Exception as e:
        logger.error(f"[IMAGE_GEN_CONFIG] Failed saving profile '{name}': {e}")
        return False


def load_profile(name: str) -> dict | None:
    cfg = get_image_gen_config()
    return cfg.get("profiles", {}).get(name)


def delete_profile(name: str) -> bool:
    cfg = get_image_gen_config()
    profiles = cfg.get("profiles", {})
    if name not in profiles:
        return False
    del profiles[name]
    cfg["profiles"] = profiles
    if cfg.get("default_profile", "") == name:
        cfg["default_profile"] = ""
    try:
        obj = ImageGenConfig.model_validate(cfg)
        ok = _write_toml(obj.model_dump(mode='json'))
        if ok:
            logger.info(f"[IMAGE_GEN_CONFIG] Profile '{name}' deleted.")
        return ok
    except Exception as e:
        logger.error(f"[IMAGE_GEN_CONFIG] Failed deleting profile '{name}': {e}")
        return False


def set_default_profile(name: str) -> bool:
    cfg = get_image_gen_config()
    if name and name not in cfg.get("profiles", {}):
        return False
    cfg["default_profile"] = name
    try:
        obj = ImageGenConfig.model_validate(cfg)
        ok = _write_toml(obj.model_dump(mode='json'))
        if ok:
            logger.info(f"[IMAGE_GEN_CONFIG] Default profile set to '{name or '(none)'}'.")
        return ok
    except Exception as e:
        logger.error(f"[IMAGE_GEN_CONFIG] Failed setting default profile: {e}")
        return False
