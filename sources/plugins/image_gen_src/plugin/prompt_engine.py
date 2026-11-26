"""
Plugin: Image Generation — Prompt Engine
Handles style modifier injection, auto-enrichment, and Flux refinement.
"""

try:
    from hecos.core.logging import logger
except ImportError:
    class _L:
        def info(self, *a): print("[PROMPT_ENGINE]", *a)
        def warning(self, *a): print("[PROMPT_ENGINE WARN]", *a)
        def error(self, *a): print("[PROMPT_ENGINE ERR]", *a)
    logger = _L()


STYLE_MAP = {
    "cinematic":   "cinematic photo, highly detailed, dramatic lighting, 8k",
    "photography": "professional photography, DSLR, ultra-realistic, 8k, sharp focus",
    "anime":       "anime style, vibrant colors, expressive features, clean lines",
    "manga":       "manga style, black and white, detailed ink drawing, hatch lines",
    "cartoon":     "cartoon style, playful, simplified shapes, bright colors, 2d",
    "digital_art": "digital art, concept art, artistic, detailed illustration",
    "oil_painting":"oil painting, textured brushstrokes, classical art style, canvas",
    "sketch":      "pencil sketch, hand-drawn, graphite, artist study, white background",
    "3d_render":   "3D rendering, Octane Render, Unreal Engine 5, highly detailed, photorealistic",
    "real_photo":  "realistic photo, ultra-realistic, highly detailed, sharp focus, 8k",

    "cyberpunk":   "cyberpunk style, neon lights, rainy streets, futuristic, high tech",
    "fantasy":     "fantasy art, magical, ethereal, epic scale, mythical",
    "watercolor":  "watercolor painting, soft washes, fluid strokes, pale tones",
    "pixel_art":   "pixel art, retro style, 16-bit, crisp pixels, limited palette",
}


def apply_style(prompt: str, style: str) -> str:
    if not style or style.lower() == "none":
        return prompt
    modifier = STYLE_MAP.get(style.lower())
    if modifier:
        return f"{prompt}, {modifier}"
    return prompt


def apply_enrichment(prompt: str, auto_enrich: bool, enrich_keywords: str) -> str:
    if not auto_enrich:
        return prompt
    terms = enrich_keywords.strip() if enrich_keywords else \
        "masterpiece, 8k wallpaper, highly detailed, realistic, sharp focus, cinematic lighting"
    if "masterpiece" not in prompt.lower() and "8k" not in prompt.lower():
        return f"{prompt}, {terms}"
    return prompt


def refine_flux_prompt(original_prompt: str, instructions: str) -> str:
    """
    Optional Flux Prompt Upsampler powered by the active Hecos LLM backend.
    Uses ONLY the user-configured, editable `flux_refiner_instructions` from image_gen.toml / UI.
    Falls back cleanly to `original_prompt` if instructions are empty, running isolated, or LLM fails.
    """
    clean_instr = (instructions or "").strip()
    if not clean_instr or not (original_prompt or "").strip():
        return original_prompt

    try:
        import re
        import sys
        from hecos.core.llm import client as llm_client

        cfg_mgr = getattr(sys, "hecos_config_manager", None)
        if cfg_mgr is not None and isinstance(getattr(cfg_mgr, "config", None), dict):
            sys_cfg = cfg_mgr.config
        else:
            from hecos.app.config import ConfigManager
            sys_cfg = ConfigManager().config

        try:
            from hecos.app.model_manager import ModelManager
            btype, mname = ModelManager.get_effective_model_info(sys_cfg)
        except Exception:
            btype = (sys_cfg.get("backend") or {}).get("type", "ollama")
            mname = ((sys_cfg.get("backend") or {}).get(btype) or {}).get("model", "")

        if not mname:
            return original_prompt

        backend_cfg = dict(((sys_cfg.get("backend") or {}).get(btype) or {}))
        backend_cfg["backend_type"] = btype
        backend_cfg["model"] = mname
        backend_cfg["payload_control"] = {"send_tools": False}
        backend_cfg["disable_tools"] = True
        backend_cfg["think"] = False

        llm_cfg = dict(sys_cfg.get("llm") or {})
        llm_cfg["max_tokens"] = min(int(llm_cfg.get("max_tokens") or 300), 260)
        llm_cfg["temperature"] = min(float(llm_cfg.get("temperature") or 0.6), 0.7)
        llm_cfg["think"] = False

        raw_out = llm_client.generate(
            clean_instr,
            original_prompt.strip(),
            backend_cfg,
            llm_cfg,
            tools=None,
            images=None,
            extra_messages=None,
        )
        text = raw_out.get("content", "") if isinstance(raw_out, dict) else getattr(raw_out, "content", str(raw_out or ""))
        if not text or str(text).lstrip().startswith(("⚠️", "❌", "⛔")):
            return original_prompt

        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", str(text), flags=re.IGNORECASE).strip()
        cleaned = cleaned.strip().strip('"').strip("'").strip()
        if len(cleaned) >= 20 and len(cleaned) <= 1800:
            logger.info(f"[PROMPT_ENGINE] Flux Prompt Upsampler refined prompt ({len(original_prompt)} -> {len(cleaned)} chars).")
            return cleaned
    except Exception as exc:
        logger.warning(f"[PROMPT_ENGINE] Flux Prompt Upsampler fallback to original prompt: {exc}")

    return original_prompt


def build_prompt(
    raw_prompt: str, style: str, auto_enrich: bool, enrich_keywords: str,
    model: str, optimize_for_flux: bool, flux_instructions: str,
) -> str:
    if optimize_for_flux and "flux" in (model or "").lower():
        logger.info("[PROMPT_ENGINE] Flux Prompt Upsampler enabled — refining prompt with user instructions.")
        prompt = refine_flux_prompt(raw_prompt, flux_instructions)
        return apply_style(prompt, style)

    prompt = apply_style(raw_prompt, style)
    prompt = apply_enrichment(prompt, auto_enrich, enrich_keywords)
    return prompt
