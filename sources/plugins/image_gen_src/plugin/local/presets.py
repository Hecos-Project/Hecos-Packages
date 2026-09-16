"""
image_gen — Local Generation Presets
Built-in presets optimized for local image generation via SwarmUI.
These presets use model names as expected by a typical SwarmUI installation.

Users can override model names in the config if their local filenames differ.
"""

from __future__ import annotations
from typing import Any


LOCAL_BUILTIN_PRESETS: dict[str, dict[str, Any]] = {

    # ── Flux Schnell: Ultra-fast, 4 steps ─────────────────────────────────
    "⚡ Flux Local (SwarmUI)": {
        "provider": "swarmui",
        "model": "FLUX.1-schnell",
        "aspect_ratio": "1:1",
        "width": 1024,
        "height": 1024,
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
        "_local": True,
        "_description": (
            "Flux Schnell locale via SwarmUI. Velocissimo (4 step). "
            "Richiede modello Flux.1 Schnell installato in SwarmUI."
        ),
    },

    # ── SDXL: High quality, 30 steps ──────────────────────────────────────
    "🎨 SDXL Local (SwarmUI)": {
        "provider": "swarmui",
        "model": "sd_xl_base_1.0",
        "aspect_ratio": "1:1",
        "width": 1024,
        "height": 1024,
        "guidance_scale": 7.5,
        "num_inference_steps": 30,
        "seed": -1,
        "sampler": "dpm++2m",
        "scheduler": "karras",
        "negative_prompt": (
            "distorted, extra fingers, malformed limbs, missing limbs, "
            "ugly, blurry, low quality, bad anatomy, bad proportions, "
            "watermark, text, signature"
        ),
        "enable_negative_prompt": True,
        "auto_enrich": True,
        "optimize_for_flux": False,
        "style": "none",
        "_builtin": True,
        "_local": True,
        "_description": (
            "Stable Diffusion XL locale via SwarmUI. Ottima qualità, 30 step. "
            "Richiede modello SDXL installato in SwarmUI."
        ),
    },

    # ── Custom SwarmUI Presets ────────────────────────────────────────────
    "💎 ZImage Turbo FP8": {
        "provider": "swarmui",
        "model": "SwarmUI_Z-Image-Turbo-FP8Mix",
        "aspect_ratio": "1:1",
        "width": 1024,
        "height": 1024,
        "guidance_scale": 2.5,
        "num_inference_steps": 12,
        "seed": -1,
        "sampler": "euler",
        "scheduler": "simple",
        "negative_prompt": "",
        "enable_negative_prompt": False,
        "auto_enrich": True,
        "optimize_for_flux": True,
        "style": "none",
        "_builtin": True,
        "_local": True,
        "_description": "Z-Image Turbo FP8Mix model.",
    },
    
    "🌀 Flux.1 Dev FP8": {
        "provider": "swarmui",
        "model": "flux1-dev-fp8",
        "aspect_ratio": "1:1",
        "width": 1024,
        "height": 1024,
        "guidance_scale": 3.5,
        "num_inference_steps": 20,
        "seed": -1,
        "sampler": "euler",
        "scheduler": "simple",
        "negative_prompt": "",
        "enable_negative_prompt": False,
        "auto_enrich": True,
        "optimize_for_flux": True,
        "style": "none",
        "_builtin": True,
        "_local": True,
        "_description": "Standard Flux.1 Dev (FP8). Ottimo per fotorealismo e testi.",
    },

    "🔥 PornMaster Flux2 Klein": {
        "provider": "swarmui",
        "model": "pornmasterFlux2Klein_v4TurboFp8",
        "aspect_ratio": "3:4",
        "width": 896,
        "height": 1152,
        "guidance_scale": 2.5,
        "num_inference_steps": 12,
        "seed": -1,
        "sampler": "euler",
        "scheduler": "simple",
        "negative_prompt": "",
        "enable_negative_prompt": False,
        "auto_enrich": True,
        "optimize_for_flux": True,
        "style": "none",
        "_builtin": True,
        "_local": True,
        "_description": "PornMaster Flux2 Klein Turbo (NSFW).",
    },

    "🍑 PornMaster ZImage Turbo": {
        "provider": "swarmui",
        "model": "pornmasterZImage_turboV35Bf16",
        "aspect_ratio": "3:4",
        "width": 896,
        "height": 1152,
        "guidance_scale": 2.5,
        "num_inference_steps": 12,
        "seed": -1,
        "sampler": "euler",
        "scheduler": "simple",
        "negative_prompt": "",
        "enable_negative_prompt": False,
        "auto_enrich": True,
        "optimize_for_flux": True,
        "style": "none",
        "_builtin": True,
        "_local": True,
        "_description": "PornMaster ZImage Turbo v3.5 (Bf16).",
    },
}


def get_local_presets() -> dict[str, dict[str, Any]]:
    """Returns a copy of the local built-in presets."""
    return dict(LOCAL_BUILTIN_PRESETS)


def is_local_preset(preset: dict) -> bool:
    """Check if a preset dict is marked as a local preset."""
    return preset.get("_local", False)
