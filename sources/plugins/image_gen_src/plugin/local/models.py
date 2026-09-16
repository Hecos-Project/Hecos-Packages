"""
image_gen — Local Model Discovery & Management
Handles querying SwarmUI for available models, categorizing them
by architecture, and providing smart defaults.

Responsibilities:
  - discover_models()    → fetch model list from SwarmUI
  - categorize_models()  → group by architecture (Flux, SDXL, SD, etc.)
  - get_default_model()  → smart default for a given category
  - Cached with TTL to avoid hammering the API
"""

import time
from typing import Optional

try:
    from hecos_sdk import logger
except ImportError:
    class _L:
        def info(self, *a): print("[LOCAL_MODELS]", *a)
        def warning(self, *a): print("[LOCAL_MODELS WARN]", *a)
        def error(self, *a): print("[LOCAL_MODELS ERR]", *a)
        def debug(self, *a): pass
    logger = _L()


# ── Architecture detection patterns ──────────────────────────────────────
# Maps keyword patterns in model names/filenames to architecture categories.

_ARCH_PATTERNS = {
    "flux": [
        "flux", "FLUX",
    ],
    "sdxl": [
        "sdxl", "SDXL", "sd_xl", "stable-diffusion-xl",
        "stable_diffusion_xl", "StableDiffusionXL",
    ],
    "sd3": [
        "sd3", "SD3", "sd_3", "stable-diffusion-3",
        "stable_diffusion_3", "StableDiffusion3",
    ],
    "sd15": [
        "sd15", "sd_1_5", "sd-1-5", "v1-5", "v1_5",
        "stable-diffusion-v1", "stable_diffusion_v1",
        "sd1.", "SD1.",
    ],
    "sdxl_turbo": [
        "turbo", "Turbo", "lightning", "Lightning", "lcm", "LCM",
    ],
    "pony": [
        "pony", "Pony", "pdxl",
    ],
}

# Priority order for default model selection
_ARCH_PRIORITY = ["flux", "sdxl", "sd3", "sdxl_turbo", "pony", "sd15"]


# ── Cache ─────────────────────────────────────────────────────────────────

_model_cache: Optional[list[dict]] = None
_cache_timestamp: float = 0.0
_CACHE_TTL: float = 300.0  # 5 minutes


def _is_cache_valid() -> bool:
    """Check if the model cache is still fresh."""
    return (_model_cache is not None
            and (time.time() - _cache_timestamp) < _CACHE_TTL)


def invalidate_cache():
    """Force refresh on next discover_models() call."""
    global _model_cache, _cache_timestamp
    _model_cache = None
    _cache_timestamp = 0.0


# ── Public API ────────────────────────────────────────────────────────────

def discover_models(client, force_refresh: bool = False) -> list[dict]:
    """
    Fetch the list of available models from SwarmUI.

    Args:
        client: A SwarmUIClient instance.
        force_refresh: If True, ignore cache and re-query.

    Returns:
        List of model dicts with 'name' and 'title' keys.
    """
    global _model_cache, _cache_timestamp

    if not force_refresh and _is_cache_valid():
        return _model_cache  # type: ignore

    try:
        models = client.list_models()
        _model_cache = models
        _cache_timestamp = time.time()
        logger.info(f"[LOCAL_MODELS] Discovered {len(models)} model(s) from SwarmUI")
        return models
    except Exception as e:
        logger.error(f"[LOCAL_MODELS] Model discovery failed: {e}")
        return _model_cache or []


def detect_architecture(model_name: str) -> str:
    """
    Detect the model architecture from its name/filename.

    Args:
        model_name: The model identifier string.

    Returns:
        Architecture category string (e.g., "flux", "sdxl", "sd15")
        or "unknown" if unrecognized.
    """
    name_lower = model_name.lower()

    # Check turbo/lightning first (they're usually SDXL-based but distinct)
    for pattern in _ARCH_PATTERNS.get("sdxl_turbo", []):
        if pattern.lower() in name_lower:
            return "sdxl_turbo"

    for arch, patterns in _ARCH_PATTERNS.items():
        if arch == "sdxl_turbo":
            continue  # Already checked
        for pattern in patterns:
            if pattern.lower() in name_lower:
                return arch

    return "unknown"


def categorize_models(models: list[dict]) -> dict[str, list[dict]]:
    """
    Group models by detected architecture.

    Args:
        models: List of model dicts from discover_models().

    Returns:
        Dict mapping architecture names to lists of model dicts.
        Each model dict gets an extra 'architecture' key.
    """
    categories: dict[str, list[dict]] = {}

    for model in models:
        name = model.get("name", model.get("title", ""))
        arch = detect_architecture(name)
        model_with_arch = {**model, "architecture": arch}

        if arch not in categories:
            categories[arch] = []
        categories[arch].append(model_with_arch)

    return categories


def get_default_model(models: list[dict], preferred_arch: str = "") -> str:
    """
    Pick the best default model from the available list.

    Args:
        models: List of model dicts.
        preferred_arch: Preferred architecture (e.g., "flux", "sdxl").
                        If empty, uses the priority order.

    Returns:
        Model name string, or empty string if no models available.
    """
    if not models:
        return ""

    categorized = categorize_models(models)

    # If user has a preference, try that first
    if preferred_arch:
        arch_models = categorized.get(preferred_arch, [])
        if arch_models:
            return arch_models[0].get("name", "")

    # Otherwise, use priority order
    for arch in _ARCH_PRIORITY:
        arch_models = categorized.get(arch, [])
        if arch_models:
            return arch_models[0].get("name", "")

    # Fallback: first available model
    return models[0].get("name", "")


def get_model_summary(models: list[dict]) -> str:
    """
    Generate a human-readable summary of available models.

    Args:
        models: List of model dicts.

    Returns:
        Formatted markdown string.
    """
    if not models:
        return "No models found."

    categorized = categorize_models(models)
    lines = []

    arch_labels = {
        "flux": "⚡ Flux",
        "sdxl": "🎨 SDXL",
        "sd3": "🌟 SD3",
        "sdxl_turbo": "🚀 SDXL Turbo/Lightning",
        "sd15": "📷 SD 1.5",
        "pony": "🐴 Pony",
        "unknown": "❓ Other",
    }

    for arch in [*_ARCH_PRIORITY, "unknown"]:
        arch_models = categorized.get(arch, [])
        if arch_models:
            label = arch_labels.get(arch, arch)
            lines.append(f"**{label}** ({len(arch_models)})")
            for m in arch_models[:5]:  # Show max 5 per category
                lines.append(f"  - `{m.get('name', '?')}`")
            if len(arch_models) > 5:
                lines.append(f"  - ... +{len(arch_models) - 5} more")

    return "\n".join(lines)
