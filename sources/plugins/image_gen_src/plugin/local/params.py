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
    "euler":                    "euler",
    "euler_a":                  "euler_ancestral",
    "euler_ancestral":          "euler_ancestral",
    "heun":                     "heun",
    "heunpp2":                  "heunpp2",
    "dpm_2":                    "dpm_2",
    "dpm_2_a":                  "dpm_2_ancestral",
    "dpm_2_ancestral":          "dpm_2_ancestral",
    "dpm++2m":                  "dpmpp_2m",
    "dpm++_2m":                 "dpmpp_2m",
    "dpmpp_2m":                 "dpmpp_2m",
    "dpm++2s":                  "dpmpp_2s_ancestral",
    "dpm++_2s_a":               "dpmpp_2s_ancestral",
    "dpmpp_2s_ancestral":       "dpmpp_2s_ancestral",
    "dpm++sde":                 "dpmpp_sde",
    "dpm++_sde":                "dpmpp_sde",
    "dpmpp_sde":                "dpmpp_sde",
    "dpmpp_sde_gpu":            "dpmpp_sde_gpu",
    "dpm++2m_sde":              "dpmpp_2m_sde",
    "dpm++_2m_sde":             "dpmpp_2m_sde",
    "dpmpp_2m_sde":             "dpmpp_2m_sde",
    "dpmpp_2m_sde_gpu":         "dpmpp_2m_sde_gpu",
    "dpm++_3m_sde":             "dpmpp_3m_sde",
    "dpmpp_3m_sde":             "dpmpp_3m_sde",
    "dpmpp_3m_sde_gpu":         "dpmpp_3m_sde_gpu",
    "ddim":                     "ddim",
    "ddpm":                     "ddpm",
    "lms":                      "lms",
    "dpm_fast":                 "dpm_fast",
    "dpm_adaptive":             "dpm_adaptive",
    "uni_pc":                   "uni_pc",
    "uni_pc_bh2":               "uni_pc_bh2",
    "lcm":                      "lcm",
    # Modern Flow-Matching / Flux / Rectified Flow samplers in SwarmUI
    "res_multistep":            "res_multistep",
    "res_multistep_ancestral":  "res_multistep_ancestral",
    "deis":                     "deis",
    "er_sde":                   "er_sde",
    "ipndm":                    "ipndm",
    "ipndm_v":                  "ipndm_v",
    "sa_solver":                "sa_solver",
    "sa_solver_pece":           "sa_solver_pece",
    "seeds_2":                  "seeds_2",
    "seeds_3":                  "seeds_3",
    "gradient_estimation":      "gradient_estimation",
    "euler_cfg_pp":             "euler_cfg_pp",
    "dpmpp_2m_cfg_pp":          "dpmpp_2m_cfg_pp",
    "res_multistep_cfg_pp":     "res_multistep_cfg_pp",
}

SCHEDULER_MAP = {
    "simple":           "simple",
    "normal":           "normal",
    "karras":           "karras",
    "sgm":              "sgm_uniform",
    "sgm_uniform":      "sgm_uniform",
    "exponential":      "exponential",
    "beta":             "beta",
    "linear":           "linear_quadratic",
    "linear_quadratic": "linear_quadratic",
    "ddim_uniform":     "ddim_uniform",
    "align_your_steps": "align_your_steps",
    "turbo":            "turbo",
    "flux2":            "flux2",
    "kl_optimal":       "kl_optimal",
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
    # Advanced / Flux / Rectified Flow params
    loras: Optional[list[dict]] = None,
    vae: Optional[str] = None,
    clip_skip: Optional[int] = None,
    flux_guidance_scale: Optional[float] = None,
    sigma_shift: Optional[float] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict:
    """
    Build the parameter dict for SwarmUI's GenerateText2Image API.
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

    # Flux Guidance Scale (optional override; -1 / None lets SwarmUI use model default)
    if flux_guidance_scale is not None:
        try:
            fg = float(flux_guidance_scale)
            if fg >= 0.0:
                params["fluxguidancescale"] = fg
        except (TypeError, ValueError):
            pass

    # Sigma Shift (optional override for Rectified Flow / Flux / SD3; -1 / None = model default)
    if sigma_shift is not None:
        try:
            ss = float(sigma_shift)
            if ss >= 0.0:
                params["sigmashift"] = ss
        except (TypeError, ValueError):
            pass

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
    """
    meta = {
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
    if "fluxguidancescale" in params:
        meta["flux_guidance_scale"] = params["fluxguidancescale"]
    if "sigmashift" in params:
        meta["sigma_shift"] = params["sigmashift"]
    if params.get("vae"):
        meta["vae"] = params["vae"]
    return meta
