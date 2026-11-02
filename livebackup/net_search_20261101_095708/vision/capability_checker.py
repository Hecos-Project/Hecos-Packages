"""
vision/capability_checker.py
Checks whether the currently active LLM backend + model supports vision input.
Fully self-contained: reads hecos config to detect the active model, then matches
it against a curated list of known vision-capable model families.
"""
from __future__ import annotations

import re
import logging
from typing import Optional

logger = logging.getLogger("hecos.net_search.vision.capability_checker")

# ---------------------------------------------------------------------------
# Known vision-capable model name patterns (case-insensitive regex)
# ---------------------------------------------------------------------------
_VISION_PATTERNS: list[str] = [
    # OpenAI
    r"gpt-4o",
    r"gpt-4-turbo",
    r"gpt-4-vision",
    r"o1",
    # Anthropic Claude
    r"claude-3",
    r"claude-3\.5",
    # Google Gemini
    r"gemini",
    # Meta LLaVA family (local / Ollama)
    r"llava",
    r"bakllava",
    r"obsidian",
    r"moondream",
    r"cogvlm",
    r"minicpm-v",
    r"internvl",
    r"qwen.*vl",
    r"pixtral",
    r"llama.*vision",
    # Mistral
    r"mistral.*vision",
    r"pixtral",
    # xAI Grok
    r"grok-2",
    # Generic "vision" or "vl" suffixes
    r"\bvision\b",
    r"\bvl\b",
    r"-v\d+",        # e.g. model-v2
]

_VISION_COMPILED = [re.compile(p, re.IGNORECASE) for p in _VISION_PATTERNS]


def model_supports_vision(config: Optional[dict] = None) -> bool:
    """
    Returns True if the active LLM model is known to support image/vision input.

    Resolution order:
    1. ``config`` dict passed in (from the caller's already-loaded config)
    2. hecos config_manager singleton (loaded from config.yaml)
    3. Fallback → False (safe degradation)
    """
    model_name = _resolve_model_name(config)
    if not model_name:
        logger.debug("[VisionChecker] Could not determine active model — assuming no vision support.")
        return False

    for pattern in _VISION_COMPILED:
        if pattern.search(model_name):
            logger.debug(f"[VisionChecker] Model '{model_name}' matched vision pattern '{pattern.pattern}' → vision=True")
            return True

    logger.debug(f"[VisionChecker] Model '{model_name}' does not match any known vision pattern → vision=False")
    return False


def _resolve_model_name(config: Optional[dict]) -> Optional[str]:
    """Tries multiple sources to find the active model name string."""
    # --- Source 1: explicitly passed config dict ---
    if config and isinstance(config, dict):
        name = _extract_model_from_dict(config)
        if name:
            return name

    # --- Source 2: hecos config_manager singleton ---
    try:
        from hecos.config.manager import get_config_manager
        cfg = get_config_manager().config
        if cfg:
            name = _extract_model_from_dict(cfg if isinstance(cfg, dict) else cfg.__dict__)
            if name:
                return name
    except Exception as e:
        logger.debug(f"[VisionChecker] config_manager not available: {e}")

    return None


def _extract_model_from_dict(cfg: dict) -> Optional[str]:
    """Traverses common config key paths to find a model name."""
    # Flat keys
    for key in ("model", "model_name", "llm_model", "active_model"):
        val = cfg.get(key)
        if val and isinstance(val, str):
            return val

    # Nested: cfg["llm"]["model"]
    llm_section = cfg.get("llm") or cfg.get("brain") or cfg.get("ai")
    if isinstance(llm_section, dict):
        for key in ("model", "model_name", "active_model"):
            val = llm_section.get(key)
            if val and isinstance(val, str):
                return val

    return None

