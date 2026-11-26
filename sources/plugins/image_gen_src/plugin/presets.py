"""
Plugin: Image Generation — Preset Manager
Manages built-in (read-only) and user-defined (CRUD) configuration presets.
User presets now capture the FULL configuration snapshot (provider, model,
VAE, LoRAs, sampler, scheduler, API keys, etc.) — same scope as Profiles.
"""

from __future__ import annotations
from typing import Any

try:
    from hecos.core.logging import logger
except ImportError:
    class _L:
        def info(self, *a): print("[PRESETS]", *a)
        def error(self, *a): print("[PRESETS ERR]", *a)
    logger = _L()


BUILTIN_PRESETS: dict[str, dict[str, Any]] = {
    "⚡ Flux Free (Pollinations)": {
        "provider": "pollinations",
        "model": "flux",
        "aspect_ratio": "1:1",
        "guidance_scale": 0.0,
        "num_inference_steps": 4,
        "seed": -1,
        "sampler": "euler",
        "scheduler": "simple",
        "negative_prompt": "",
        "enable_negative_prompt": False,
        "auto_enrich": False,
        "optimize_for_flux": True,
        "style": "none",
        "_builtin": True,
        "_description": "Free, no API key required. Uses Pollinations with Flux model.",
    },
    "🌐 SDXL (HuggingFace)": {
        "provider": "huggingface",
        "model": "stabilityai/stable-diffusion-xl-base-1.0",
        "aspect_ratio": "1:1",
        "guidance_scale": 7.5,
        "num_inference_steps": 40,
        "seed": -1,
        "sampler": "dpm++_2m",
        "scheduler": "dpm++",
        "negative_prompt": "distorted, extra fingers, malformed limbs, missing limbs, ugly, blurry, low quality",
        "enable_negative_prompt": True,
        "auto_enrich": True,
        "optimize_for_flux": False,
        "style": "none",
        "_builtin": True,
        "_description": "Stable Diffusion XL via HuggingFace Inference API. Requires HF API key.",
    },
    "🖼 SD 1.5 1B (HuggingFace)": {
        "provider": "huggingface",
        "model": "runwayml/stable-diffusion-v1-5",
        "aspect_ratio": "1:1",
        "guidance_scale": 7.5,
        "num_inference_steps": 30,
        "seed": -1,
        "sampler": "euler_a",
        "scheduler": "pndm",
        "negative_prompt": "distorted, extra fingers, malformed limbs, ugly, blurry, low quality",
        "enable_negative_prompt": True,
        "auto_enrich": True,
        "optimize_for_flux": False,
        "style": "none",
        "_builtin": True,
        "_description": "Stable Diffusion 1.5 (~1B params). Fast, lighter on HF quota.",
    },
    "⚡ Flux Schnell (HuggingFace)": {
        "provider": "huggingface",
        "model": "black-forest-labs/FLUX.1-schnell",
        "aspect_ratio": "1:1",
        "guidance_scale": 0.0,
        "num_inference_steps": 4,
        "seed": -1,
        "sampler": "euler",
        "scheduler": "simple",
        "negative_prompt": "",
        "enable_negative_prompt": False,
        "auto_enrich": False,
        "optimize_for_flux": True,
        "style": "none",
        "_builtin": True,
        "_description": "Flux Schnell via HuggingFace. Very fast (4 steps). Requires HF API key.",
    },
    "🎲 Stable Diffusion (AI Horde)": {
        "provider": "horde",
        "model": "stable_diffusion",
        "aspect_ratio": "custom",
        "width": 768,
        "height": 768,
        "guidance_scale": 7.5,
        "num_inference_steps": 30,
        "seed": -1,
        "sampler": "euler_a",
        "scheduler": "simple",
        "negative_prompt": "distorted, malformed, ugly, bad anatomy, bad proportions, bad perspective, blurry, low quality",
        "enable_negative_prompt": True,
        "auto_enrich": False,
        "optimize_for_flux": False,
        "style": "none",
        "_builtin": True,
        "_description": "Free crowdsourced cluster. No censorship. Anonymous or use Kudos via API key.",
    },
}

# -- Import local presets ----------------------------------------------------
try:
    from .local.presets import LOCAL_BUILTIN_PRESETS
except ImportError:
    LOCAL_BUILTIN_PRESETS = {}

# Merge local presets into the built-in set
BUILTIN_PRESETS.update(LOCAL_BUILTIN_PRESETS)

# All keys captured in a full user preset snapshot (excludes API keys and active_preset)
_PRESET_SNAPSHOT_KEYS = [
    "provider", "model", "hf_provider", "aspect_ratio", "width", "height",
    "seed", "sampler", "scheduler", "guidance_scale", "num_inference_steps",
    "flux_guidance_scale", "sigma_shift",
    "enable_negative_prompt", "negative_prompt", "auto_enrich",
    "enrich_keywords", "style", "nologo", "optimize_for_flux",
    "flux_refiner_instructions",
    "show_metadata_in_chat", "vae", "loras",
    "cloud_enabled", "horde_nsfw", "horde_worker_blacklist",
    "routing_override",
]

_INT_KEYS = {"width", "height", "seed", "num_inference_steps"}
_FLOAT_KEYS = {"guidance_scale", "flux_guidance_scale", "sigma_shift"}
_BOOL_KEYS = {
    "enable_negative_prompt", "auto_enrich", "nologo",
    "optimize_for_flux", "show_metadata_in_chat", "cloud_enabled", "horde_nsfw",
}
_LIST_KEYS = {"loras"}


def _get_cfg_io():
    try:
        from igen_config.config_manager import get_config, save_config
    except ImportError:
        from ..igen_config.config_manager import get_config, save_config
    return get_config, save_config


def is_builtin_preset(name: str) -> bool:
    """Case-insensitive check whether a preset name is reserved / built-in."""
    if not name or not isinstance(name, str):
        return False
    norm = name.strip().lower()
    if not norm or norm == "default":
        return True
    return any(k.strip().lower() == norm for k in BUILTIN_PRESETS.keys())


def _find_case_insensitive(mapping: dict, name: str) -> str | None:
    norm = name.strip().lower()
    for k in mapping.keys():
        if k.strip().lower() == norm:
            return k
    return None


def sanitize_preset_snapshot(config_snapshot: dict, description: str = "") -> dict[str, Any]:
    """Filter and type-coerce a preset snapshot so TOML serialization never fails on None/NaN."""
    snapshot: dict[str, Any] = {}
    if not isinstance(config_snapshot, dict):
        return snapshot

    for k in _PRESET_SNAPSHOT_KEYS:
        if k not in config_snapshot:
            continue
        v = config_snapshot[k]
        if v is None:
            continue
        if k in _INT_KEYS:
            try:
                snapshot[k] = int(v)
            except (TypeError, ValueError):
                continue
        elif k in _FLOAT_KEYS:
            try:
                f = float(v)
                if f == f:  # reject NaN
                    snapshot[k] = f
            except (TypeError, ValueError):
                continue
        elif k in _BOOL_KEYS:
            snapshot[k] = bool(v)
        elif k in _LIST_KEYS:
            if isinstance(v, list):
                snapshot[k] = [str(item) for item in v if item is not None and str(item).strip()]
            else:
                snapshot[k] = []
        else:
            snapshot[k] = str(v)

    # Preserve or set user-facing metadata
    desc = (description or config_snapshot.get("_description") or "").strip()
    if desc:
        snapshot["_description"] = desc
    if snapshot.get("provider") == "swarmui":
        snapshot["_local"] = True
    return snapshot


def get_all_presets(user_presets: dict) -> dict[str, dict]:
    combined = dict(BUILTIN_PRESETS)
    if isinstance(user_presets, dict):
        combined.update(user_presets)
    return combined


def get_preset(name: str, user_presets: dict) -> dict | None:
    return get_all_presets(user_presets).get(name)


def save_user_preset_ex(
    name: str,
    config_snapshot: dict,
    description: str = "",
    overwrite: bool = True,
    set_active: bool = True,
) -> tuple[bool, str]:
    """Save or update a full configuration snapshot as a named user preset.
    Returns (ok, message_or_name).
    """
    get_config, save_config = _get_cfg_io()

    if not name or not isinstance(name, str) or not name.strip():
        msg = "Preset name is required."
        logger.error(f"[PRESETS] {msg}")
        return False, msg

    clean_name = name.strip()
    if is_builtin_preset(clean_name):
        msg = f"'{clean_name}' is a built-in preset and cannot be overwritten. Choose a custom name."
        logger.error(f"[PRESETS] {msg}")
        return False, msg

    try:
        cfg = get_config()
        igen = cfg.get("image_gen", {})
        presets = dict(igen.get("presets", {}) or {})

        existing_key = _find_case_insensitive(presets, clean_name)
        if existing_key is not None and not overwrite:
            return False, f"A preset named '{existing_key}' already exists."

        target_key = existing_key if (existing_key is not None and overwrite) else clean_name
        existing_desc = ""
        if existing_key and isinstance(presets.get(existing_key), dict):
            existing_desc = presets[existing_key].get("_description", "")

        snapshot = sanitize_preset_snapshot(
            config_snapshot,
            description=description if description else existing_desc,
        )
        # Guard: never save an empty model for SwarmUI presets (e.g. if SwarmUI was offline)
        if snapshot.get("provider") == "swarmui" and not str(snapshot.get("model") or "").strip():
            fallback_model = str(igen.get("model") or "").strip()
            if fallback_model and fallback_model.lower() != "flux":
                snapshot["model"] = fallback_model
            else:
                return False, "No SwarmUI model selected. Select a model (or start SwarmUI & click Refresh) before saving."
        presets[target_key] = snapshot
        igen["presets"] = presets
        if set_active:
            igen["active_preset"] = target_key
        cfg["image_gen"] = igen

        ok = save_config(cfg)
        if ok:
            logger.info(f"[PRESETS] Saved user preset '{target_key}' (full snapshot).")
            return True, target_key
        return False, "Failed writing configuration to disk."
    except Exception as e:
        logger.error(f"[PRESETS] Failed saving preset '{clean_name}': {e}")
        return False, str(e)


def save_user_preset(name: str, config_snapshot: dict, description: str = "") -> bool:
    """Backward-compatible wrapper returning bool."""
    ok, _ = save_user_preset_ex(name, config_snapshot, description=description, overwrite=True, set_active=True)
    return ok


def rename_user_preset(old_name: str, new_name: str) -> tuple[bool, str]:
    """Rename an existing custom user preset and update active_preset/default_preset references."""
    get_config, save_config = _get_cfg_io()

    old_clean = (old_name or "").strip()
    new_clean = (new_name or "").strip()

    if not old_clean:
        return False, "No preset selected to rename."
    if not new_clean:
        return False, "New preset name is required."
    if is_builtin_preset(old_clean):
        return False, f"Built-in preset '{old_clean}' cannot be renamed. Duplicate or save as a custom preset first."
    if is_builtin_preset(new_clean):
        return False, f"'{new_clean}' is a reserved built-in preset name."
    if old_clean == new_clean:
        return True, new_clean

    try:
        cfg = get_config()
        igen = cfg.get("image_gen", {})
        presets = dict(igen.get("presets", {}) or {})

        if old_clean not in presets:
            return False, f"Custom preset '{old_clean}' not found."

        collision = _find_case_insensitive(presets, new_clean)
        if collision is not None and collision != old_clean:
            return False, f"A preset named '{collision}' already exists."

        # Rebuild dict preserving key order
        new_presets: dict[str, Any] = {}
        for k, v in presets.items():
            if k == old_clean:
                new_presets[new_clean] = v
            else:
                new_presets[k] = v

        igen["presets"] = new_presets
        if igen.get("active_preset") == old_clean:
            igen["active_preset"] = new_clean
        if igen.get("default_preset") == old_clean:
            igen["default_preset"] = new_clean
        cfg["image_gen"] = igen

        ok = save_config(cfg)
        if ok:
            logger.info(f"[PRESETS] Renamed user preset '{old_clean}' -> '{new_clean}'.")
            return True, new_clean
        return False, "Failed writing configuration to disk."
    except Exception as e:
        logger.error(f"[PRESETS] Failed renaming preset '{old_clean}': {e}")
        return False, str(e)


def duplicate_preset(source_name: str, new_name: str) -> tuple[bool, str]:
    """Duplicate any preset (built-in or custom) into a new editable custom preset."""
    get_config, save_config = _get_cfg_io()

    src_clean = (source_name or "").strip()
    new_clean = (new_name or "").strip()

    if not src_clean:
        return False, "Select a preset to duplicate first."
    if not new_clean:
        return False, "New preset name is required."
    if is_builtin_preset(new_clean):
        return False, f"'{new_clean}' is a reserved built-in preset name."

    try:
        cfg = get_config()
        igen = cfg.get("image_gen", {})
        user_presets = dict(igen.get("presets", {}) or {})

        source = get_preset(src_clean, user_presets)
        if source is None:
            return False, f"Source preset '{src_clean}' not found."

        collision = _find_case_insensitive(user_presets, new_clean)
        if collision is not None:
            return False, f"A preset named '{collision}' already exists."

        src_desc = source.get("_description", "") if isinstance(source, dict) else ""
        snapshot = sanitize_preset_snapshot(source, description=src_desc)
        user_presets[new_clean] = snapshot
        igen["presets"] = user_presets
        igen["active_preset"] = new_clean
        cfg["image_gen"] = igen

        ok = save_config(cfg)
        if ok:
            logger.info(f"[PRESETS] Duplicated preset '{src_clean}' -> '{new_clean}'.")
            return True, new_clean
        return False, "Failed writing configuration to disk."
    except Exception as e:
        logger.error(f"[PRESETS] Failed duplicating preset '{src_clean}': {e}")
        return False, str(e)


def delete_user_preset_ex(name: str) -> tuple[bool, str, bool]:
    """Delete a custom user preset, also clearing active_preset/default_preset if pointing to it.
    Returns (ok, message, cleared_default).
    """
    get_config, save_config = _get_cfg_io()

    clean_name = (name or "").strip()
    if not clean_name:
        return False, "No preset selected.", False
    if is_builtin_preset(clean_name):
        msg = f"Built-in preset '{clean_name}' cannot be deleted."
        logger.error(f"[PRESETS] {msg}")
        return False, msg, False

    try:
        cfg = get_config()
        igen = cfg.get("image_gen", {})
        presets = dict(igen.get("presets", {}) or {})
        if clean_name not in presets:
            msg = f"Preset '{clean_name}' not found."
            logger.error(f"[PRESETS] {msg}")
            return False, msg, False

        del presets[clean_name]
        igen["presets"] = presets

        cleared_default = False
        if igen.get("active_preset") == clean_name:
            igen["active_preset"] = ""
        if igen.get("default_preset") == clean_name:
            igen["default_preset"] = ""
            cleared_default = True

        cfg["image_gen"] = igen
        ok = save_config(cfg)
        if ok:
            logger.info(f"[PRESETS] Deleted user preset '{clean_name}'.")
            return True, clean_name, cleared_default
        return False, "Failed writing configuration to disk.", False
    except Exception as e:
        logger.error(f"[PRESETS] Failed deleting preset '{clean_name}': {e}")
        return False, str(e), False


def delete_user_preset(name: str) -> bool:
    """Backward-compatible wrapper returning bool."""
    ok, _, _ = delete_user_preset_ex(name)
    return ok


def export_preset(name: str) -> dict[str, Any] | None:
    """Build a portable JSON export dictionary for any preset (custom or built-in)."""
    get_config, _ = _get_cfg_io()
    igen = get_config().get("image_gen", {})
    user_presets = igen.get("presets", {}) or {}
    preset = get_preset(name, user_presets)
    if preset is None:
        return None
    clean = {k: v for k, v in preset.items() if not k.startswith("_") and k in _PRESET_SNAPSHOT_KEYS}
    return {
        "format": "hecos_image_gen_preset",
        "version": 1,
        "name": name,
        "description": preset.get("_description", ""),
        "config": clean,
    }


def import_user_preset(
    name: str,
    config_snapshot: dict,
    description: str = "",
    auto_rename: bool = True,
) -> tuple[bool, str]:
    """Import a preset JSON payload as a custom user preset (auto-suffixing if name collides)."""
    get_config, _ = _get_cfg_io()
    base_name = (name or "").strip() or "Imported Preset"

    cfg = get_config()
    presets = cfg.get("image_gen", {}).get("presets", {}) or {}

    final_name = base_name
    if auto_rename and (is_builtin_preset(final_name) or _find_case_insensitive(presets, final_name) is not None):
        idx = 2
        while True:
            cand = f"{base_name} ({idx})"
            if not is_builtin_preset(cand) and _find_case_insensitive(presets, cand) is None:
                final_name = cand
                break
            idx += 1

    return save_user_preset_ex(final_name, config_snapshot, description=description, overwrite=False, set_active=True)
