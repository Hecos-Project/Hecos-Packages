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
    from hecos_sdk import logger
except ImportError:
    class _L:
        def info(self, *a): print("[IMAGE_GEN CONFIG]", *a)
        def error(self, *a): print("[IMAGE_GEN CONFIG ERR]", *a)
        def warning(self, *a): print("[IMAGE_GEN CONFIG WARN]", *a)
        def debug(self, *a): print("[IMAGE_GEN CONFIG DBG]", *a)
    logger = _L()

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

try:
    import tomli_w
    _HAS_TOMLI_W = True
except ImportError:
    _HAS_TOMLI_W = False


class ImageGenConfig(BaseModel):
    # ── Core ──────────────────────────────────────────────────────────────────
    enabled: bool = True
    provider: str = "pollinations"
    model: str = "flux"
    nologo: bool = True
    api_key: str = ""
    api_key_comment: str = ""
    hf_provider: str = "hf-inference"

    # ── Dimensions ────────────────────────────────────────────────────────────
    aspect_ratio: str = "1:1"
    width: int = 1024
    height: int = 1024

    # ── Sampling ─────────────────────────────────────────────────────────────
    seed: int = -1
    last_seed: int = -1
    sampler: str = "euler"
    scheduler: str = "simple"
    guidance_scale: float = 0.0
    num_inference_steps: int = 4

    # ── Negative Prompt ───────────────────────────────────────────────────────
    enable_negative_prompt: bool = False
    negative_prompt: str = ""

    # ── Prompt Enhancement ────────────────────────────────────────────────────
    auto_enrich: bool = False
    enrich_keywords: str = ""
    style: str = "none"
    optimize_for_flux: bool = True
    flux_refiner_instructions: str = (
        "Convert keywords into a descriptive natural language paragraph for Flux. "
        "Output ONLY the optimised prompt, no preamble."
    )

    # ── Debug / Chat Options ──────────────────────────────────────────────────
    show_metadata_in_chat: bool = False

    # ── Preset System ─────────────────────────────────────────────────────────
    presets: Dict[str, Any] = Field(default_factory=dict)
    active_preset: str = ""

    # ── Custom Models ─────────────────────────────────────────────────────────
    custom_hf_models: list = Field(default_factory=list)


_THIS_DIR = Path(__file__).parent.resolve()
_CONFIG_FILE = _THIS_DIR / "image_gen.toml"
_ROOT_KEY = "image_gen"


def _read_toml() -> dict:
    """Read the TOML config file directly, return the root dict."""
    if not _CONFIG_FILE.exists():
        # First run after install: bootstrap defaults
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
        # Preserve any other top-level keys
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
        obj = ImageGenConfig.model_validate(data[_ROOT_KEY])
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

