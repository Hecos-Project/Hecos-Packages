"""
vision/encoder.py
Base64-encodes raw image bytes into the vision dict format expected by
hecos.core.llm.client (and any OpenAI-compatible vision API).

Format produced:
    {
        "data_b64": "<base64 string>",
        "mime_type": "image/jpeg",
        "name": "search_preview_1.jpg"
    }
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Optional

logger = logging.getLogger("hecos.net_search.vision.encoder")

# Target max dimension for resizing before encoding (saves tokens / bandwidth)
DEFAULT_MAX_PX = 512

# Attempt to use Pillow for resizing; degrade gracefully if not installed
try:
    from PIL import Image as _PilImage
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    logger.debug("[VisionEncoder] Pillow not available — images sent at original size.")


def encode_image_bytes(
    raw_bytes: bytes,
    mime_hint: str = "image/jpeg",
    name: str = "search_preview.jpg",
    max_px: int = DEFAULT_MAX_PX,
) -> Optional[dict]:
    """
    Takes raw image bytes, optionally resizes via Pillow, and returns a vision dict.
    Returns None if encoding fails.
    """
    if not raw_bytes:
        return None

    try:
        actual_bytes, actual_mime = _maybe_resize(raw_bytes, mime_hint, max_px)
        b64 = base64.b64encode(actual_bytes).decode("utf-8")
        return {
            "data_b64": b64,
            "mime_type": actual_mime,
            "name": name,
        }
    except Exception as e:
        logger.debug(f"[VisionEncoder] Encoding failed for '{name}': {e}")
        return None


def _maybe_resize(raw_bytes: bytes, mime_hint: str, max_px: int) -> tuple[bytes, str]:
    """
    If Pillow is available and image exceeds max_px on its longest side, resize it.
    Returns (bytes, mime_type) — always JPEG after resize to keep size small.
    """
    if not _PIL_AVAILABLE or max_px <= 0:
        return raw_bytes, mime_hint

    try:
        img = _PilImage.open(io.BytesIO(raw_bytes))
        w, h = img.size

        if max(w, h) <= max_px:
            # Already small enough — return original bytes unchanged
            return raw_bytes, mime_hint

        # Resize proportionally
        ratio = max_px / max(w, h)
        new_w, new_h = max(1, int(w * ratio)), max(1, int(h * ratio))
        img = img.resize((new_w, new_h), _PilImage.LANCZOS)

        # Convert RGBA/P modes to RGB before saving as JPEG
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80, optimize=True)
        logger.debug(f"[VisionEncoder] Resized {w}x{h} → {new_w}x{new_h} JPEG")
        return buf.getvalue(), "image/jpeg"

    except Exception as e:
        logger.debug(f"[VisionEncoder] Pillow resize failed, using original: {e}")
        return raw_bytes, mime_hint

