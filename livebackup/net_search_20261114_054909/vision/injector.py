"""
vision/injector.py
Orchestrator for the Net Search Vision pipeline.

Entry point: ``inject_search_vision(session_id, config, vision_cfg) -> list[dict]``

Returns a list of vision dicts (each with data_b64, mime_type, name) ready to be
appended to the LLM's images list for the next inference call.

Returns an empty list if:
- The active model doesn't support vision
- The session has no thumbnail candidates
- All thumbnail downloads fail
- Vision is disabled in config
"""
from __future__ import annotations

import logging
from typing import Optional

from .capability_checker import model_supports_vision
from .selector import select_thumbnail_urls
from .fetcher import fetch_image_bytes, fetch_image_bytes_via_proxy
from .encoder import encode_image_bytes

logger = logging.getLogger("hecos.net_search.vision.injector")


def inject_search_vision(
    session_id: str,
    config: Optional[dict] = None,
    vision_cfg: Optional[dict] = None,
) -> list[dict]:
    """
    Full pipeline: session_id → list of vision dicts for LLM.

    Args:
        session_id: The ``hs_XXXX`` search session ID.
        config:     Hecos config dict (used for vision capability check).
        vision_cfg: Override dict for vision settings. Keys:
                        enabled  (bool,  default True)
                        max_images (int, default 6)
                        max_px   (int,  default 512)
                        timeout  (int,  default 5)
                        use_proxy (bool, default True)

    Returns:
        List of vision dicts ``[{"data_b64": ..., "mime_type": ..., "name": ...}, ...]``
    """
    cfg = _merge_vision_cfg(vision_cfg or {})

    # --- Guard: feature enabled? ---
    if not cfg["enabled"]:
        logger.debug("[VisionInjector] Vision review disabled in config — skipping.")
        return []

    # --- Guard: model capable? ---
    if not model_supports_vision(config):
        logger.debug("[VisionInjector] Active model does not support vision — skipping.")
        return []

    # --- Load session from store ---
    session = _load_session(session_id)
    if session is None:
        logger.warning(f"[VisionInjector] Session '{session_id}' not found in store.")
        return []

    # --- Select candidate URLs ---
    urls = select_thumbnail_urls(session, max_images=cfg["max_images"])
    if not urls:
        logger.debug(f"[VisionInjector] No thumbnail candidates found for session '{session_id}'.")
        return []

    logger.info(f"[VisionInjector] Fetching {len(urls)} thumbnails for session '{session_id}' (vision review)...")

    # --- Fetch + Encode ---
    vision_images: list[dict] = []
    for idx, url in enumerate(urls, start=1):
        raw = _fetch_with_fallback(url, cfg)
        if raw is None:
            logger.debug(f"[VisionInjector] [{idx}/{len(urls)}] Failed to fetch: {url[:80]}")
            continue

        name = f"search_preview_{idx}.jpg"
        encoded = encode_image_bytes(
            raw_bytes=raw,
            mime_hint="image/jpeg",
            name=name,
            max_px=cfg["max_px"],
        )
        if encoded:
            vision_images.append(encoded)
            logger.debug(f"[VisionInjector] [{idx}/{len(urls)}] Encoded '{name}' ({len(raw)} bytes raw)")

    logger.info(
        f"[VisionInjector] Vision pipeline complete: {len(vision_images)}/{len(urls)} images "
        f"ready for session '{session_id}'."
    )
    return vision_images


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_session(session_id: str):
    """Loads a SearchSession from the SQLite store. Returns None on failure."""
    try:
        from hecos.modules.net_search.search.sessions import get_session_store
        store = get_session_store()
        return store.get_session(session_id)
    except Exception as e:
        logger.error(f"[VisionInjector] Could not load session '{session_id}': {e}")
        return None


def _fetch_with_fallback(url: str, cfg: dict) -> Optional[bytes]:
    """
    Tries proxy first (if enabled), then falls back to direct fetch.
    Returns raw bytes or None.
    """
    timeout = cfg["timeout"]

    if cfg["use_proxy"]:
        raw = fetch_image_bytes_via_proxy(url, timeout=timeout)
        if raw:
            return raw

    # Direct fetch as fallback
    return fetch_image_bytes(url, timeout=timeout)


def _merge_vision_cfg(override: dict) -> dict:
    """Merges override with sensible defaults."""
    defaults = {
        "enabled": True,
        "max_images": 6,
        "max_px": 512,
        "timeout": 5,
        "use_proxy": True,
    }
    return {**defaults, **override}

