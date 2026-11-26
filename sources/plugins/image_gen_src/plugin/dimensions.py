"""
Plugin: Image Generation — Dimensions Helper
Resolves aspect ratio / preset dimension keys to (width, height) tuples.
Supports ~1 MP standard presets, ~1.5–2 MP HD presets (ideal for Flux.2 / Flux.3),
compact fast presets, literal 'WxH' strings, and custom (W, H) rounded to multiples of 64.
"""

import re

# Aspect ratio / resolution preset lookup table → (width, height)
ASPECT_RATIO_MAP = {
    # Standard (~1 MP — fast, balanced for Flux / SDXL)
    "1:1":       (1024, 1024),
    "3:4":       ( 896, 1152),
    "2:3":       ( 832, 1216),
    "9:16":      ( 768, 1344),
    "4:3":       (1152,  896),
    "3:2":       (1216,  832),
    "16:9":      (1344,  768),
    "21:9":      (1536,  640),
    "5:4":       (1152,  896),
    "4:5":       ( 896, 1120),

    # High-Resolution (~1.5–2 MP — great native detail for Flux.2 / Flux.3 Klein)
    "1:1_hd":    (1280, 1280),
    "2:3_hd":    (1024, 1536),
    "3:4_hd":    (1152, 1536),
    "9:16_hd":   ( 896, 1536),
    "3:2_hd":    (1536, 1024),
    "4:3_hd":    (1536, 1152),
    "16:9_hd":   (1536,  896),

    # Fast / Draft (~0.5 MP)
    "1:1_fast":  ( 768,  768),
    "3:4_fast":  ( 640,  896),
    "16:9_fast": ( 960,  576),
}

_LITERAL_DIM_RE = re.compile(r'^\s*(\d{3,4})\s*[xX×]\s*(\d{3,4})\s*$')


def resolve_dimensions(aspect_ratio: str, width: int, height: int) -> tuple[int, int]:
    """
    Returns (width, height) based on the selected aspect ratio / resolution preset.
    Supports named presets ('3:4', '2:3_hd', ...), literal 'WxH' strings, or 'custom'.
    Custom values are clamped to [256, 2048] and rounded to the nearest multiple of 64.
    """
    if aspect_ratio and aspect_ratio.strip().lower() != "custom":
        key = aspect_ratio.strip()
        resolved = ASPECT_RATIO_MAP.get(key) or ASPECT_RATIO_MAP.get(key.lower())
        if resolved:
            return resolved
        m = _LITERAL_DIM_RE.match(key)
        if m:
            w = max(256, min(2048, round(int(m.group(1)) / 64) * 64))
            h = max(256, min(2048, round(int(m.group(2)) / 64) * 64))
            return w, h

    w = max(256, min(2048, round(int(width) / 64) * 64))
    h = max(256, min(2048, round(int(height) / 64) * 64))
    return w, h
