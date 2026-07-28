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
    # In the isolated SDK environment, we cannot use the core LLM directly yet.
    # The Web UI handles refinement via routes.py. For CLI commands, we bypass.
    logger.info("[PROMPT_ENGINE] Skipping Flux refinement (running in isolated mode).")
    return original_prompt


def build_prompt(
    raw_prompt: str, style: str, auto_enrich: bool, enrich_keywords: str,
    model: str, optimize_for_flux: bool, flux_instructions: str,
) -> str:
    if optimize_for_flux and "flux" in model.lower():
        logger.info("[PROMPT_ENGINE] Flux optimisation enabled — calling Brain refiner.")
        prompt = refine_flux_prompt(raw_prompt, flux_instructions)
        return apply_style(prompt, style)

    prompt = apply_style(raw_prompt, style)
    prompt = apply_enrichment(prompt, auto_enrich, enrich_keywords)
    return prompt
