"""
image_gen — Parameter Mapper (Hecos → SwarmUI)
Translates the unified Hecos image generation parameters into
the specific format required by the SwarmUI REST API.

SwarmUI uses flat JSON keys in POST /API/GenerateText2Image.
This module ensures clean separation between Hecos config semantics
and the wire protocol.
"""

from typing import Any, Optional


# ── Sampler name mapping ──────────────────────────────────────────────────
# Hecos uses lowercase internal names; SwarmUI may use different casing
# or naming conventions. This map normalizes them.

SAMPLER_MAP = {
    "euler":       "euler",
    "euler_a":     "euler_ancestral",
    "dpm++2m":     "dpmpp_2m",
    "dpm++2s":     "dpmpp_2s_ancestral",
    "dpm++sde":    "dpmpp_sde",
    "dpm++2m_sde": "dpmpp_2m_sde",
    "ddim":        "ddim",
    "ddpm":        "ddpm",
    "lms":         "lms",
    "heun":        "heun",
    "uni_pc":      "uni_pc",
    "lcm":         "lcm",
}

SCHEDULER_MAP = {
    "simple":   "simple",
    "normal":   "normal",
    "karras":   "karras",
    "sgm":      "sgm_uniform",
    "exponential": "exponential",
    "beta":     "beta",
    "linear":   "linear_quadratic",
}


def _map_sampler(sampler: str) -> str:
    """Map Hecos sampler name to SwarmUI sampler name."""
    key = sampler.strip().lower().replace(" ", "_")
    return SAMPLER_MAP.get(key, sampler)


def _map_scheduler(scheduler: str) -> str:
    """Map Hecos scheduler name to SwarmUI scheduler name."""
    key = scheduler.strip().lower().replace(" ", "_")
    return SCHEDULER_MAP.get(key, scheduler)


def build_swarmui_params(
    prompt: str,
    model: str,
    width: int = 1024,
    height: int = 1024,
    steps: int = 30,
    cfg: float = 7.5,
    seed: int = -1,
    sampler: str = "euler",
    scheduler: str = "normal",
    negative_prompt: str = "",
    images: int = 1,
    # Advanced / future params
    loras: Optional[list[dict]] = None,
    vae: Optional[str] = None,
    clip_skip: Optional[int] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict:
    """
    Build the parameter dict for SwarmUI's GenerateText2Image API.

    Args:
        prompt: The text prompt for image generation.
        model: Model name as known to SwarmUI (e.g., "sd_xl_base_1.0").
        width: Image width in pixels.
        height: Image height in pixels.
        steps: Number of inference steps.
        cfg: Classifier-free guidance scale.
        seed: Random seed (-1 for random).
        sampler: Sampler algorithm name.
        scheduler: Scheduler algorithm name.
        negative_prompt: Negative prompt text.
        images: Number of images to generate.
        loras: Optional list of LoRA dicts [{"name": ..., "weight": ...}].
        vae: Optional VAE model name.
        clip_skip: Optional CLIP skip layers count.
        extra: Optional dict of additional raw SwarmUI parameters.

    Returns:
        Dict ready to be sent as JSON to SwarmUI API.
    """
    params: dict[str, Any] = {
        "prompt": prompt,
        "model": model,
        "width": int(width),
        "height": int(height),
        "steps": int(steps),
        "cfgscale": float(cfg),
        "images": int(images),
        "sampler": _map_sampler(sampler),
        "scheduler": _map_scheduler(scheduler),
    }

    # Seed: SwarmUI uses -1 for random, same as Hecos
    if seed is not None and seed != 0:
        params["seed"] = int(seed)

    # Negative prompt
    if negative_prompt and negative_prompt.strip():
        params["negativeprompt"] = negative_prompt.strip()

    # ── Advanced parameters ───────────────────────────────────────────

    # LoRA support
    if loras:
        for idx, lora in enumerate(loras):
            if isinstance(lora, str):
                lora_name = lora
                lora_weight = 1.0
            else:
                lora_name = lora.get("name", "")
                lora_weight = lora.get("weight", 1.0)
            
            if lora_name:
                params[f"loramodel{idx}"] = lora_name
                params[f"loraweight{idx}"] = float(lora_weight)

    # VAE override
    if vae:
        params["vae"] = vae

    # CLIP skip
    if clip_skip is not None and clip_skip > 0:
        params["clipstop"] = int(clip_skip)

    # Pass-through for any extra SwarmUI-specific params
    if extra:
        params.update(extra)

    return params


def extract_generation_metadata(params: dict, backend: str = "swarmui") -> dict:
    """
    Extract a clean metadata dict from generation params for sidecar files.

    Args:
        params: The SwarmUI params dict (as built by build_swarmui_params).
        backend: Backend identifier string.

    Returns:
        Dict suitable for saving alongside the generated image.
    """
    return {
        "provider": backend,
        "model": params.get("model", ""),
        "prompt": params.get("prompt", ""),
        "negative_prompt": params.get("negativeprompt", ""),
        "width": params.get("width", 0),
        "height": params.get("height", 0),
        "steps": params.get("steps", 0),
        "cfg_scale": params.get("cfgscale", 0.0),
        "seed": params.get("seed", -1),
        "sampler": params.get("sampler", ""),
        "scheduler": params.get("scheduler", ""),
        "backend": backend,
        "source": "local",
    }
