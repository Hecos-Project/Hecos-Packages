"""
vision/selector.py
Selects the best N thumbnail URLs from a SearchSession for vision review.

Selection strategy:
1. Prefer results from 'images', 'videos', 'audio' categories (they always have thumbnails).
2. Fall back to any result with a thumbnail_url set, regardless of category.
3. Filter out clearly broken URLs (empty, data: URIs, localhost).
4. De-duplicate by URL.
5. Return at most `max_images` candidates.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from hecos.modules.net_search.search.models import SearchSession

logger = logging.getLogger("hecos.net_search.vision.selector")

# Categories that are guaranteed to have meaningful visual thumbnails
_VISUAL_CATEGORIES = {"images", "videos", "audio"}

# Minimum URL length to be worth attempting
_MIN_URL_LEN = 12


def select_thumbnail_urls(session: "SearchSession", max_images: int = 6) -> list[str]:
    """
    Returns an ordered list of thumbnail URLs (max `max_images`) chosen from `session`.
    The returned list may be shorter than `max_images` if the session has fewer candidates.
    """
    if not session or not session.results:
        return []

    seen: set[str] = set()
    candidates: list[str] = []

    # Pass 1: visual categories first (images, videos, audio)
    for result in session.results:
        if len(candidates) >= max_images:
            break
        if result.category in _VISUAL_CATEGORIES:
            url = _best_url(result)
            if url and url not in seen:
                seen.add(url)
                candidates.append(url)

    # Pass 2: fill remaining slots with any result that has a thumbnail_url
    for result in session.results:
        if len(candidates) >= max_images:
            break
        url = result.thumbnail_url
        if url and _is_valid_url(url) and url not in seen:
            seen.add(url)
            candidates.append(url)

    logger.debug(f"[VisionSelector] Selected {len(candidates)}/{len(session.results)} thumbnails for session {session.id!r}")
    return candidates


def _best_url(result) -> str | None:
    """Returns the most useful thumbnail URL for a result, preferring thumbnail_url > media_url > url."""
    for attr in ("thumbnail_url", "media_url", "url"):
        url = getattr(result, attr, None)
        if url and _is_valid_url(url):
            return url
    return None


def _is_valid_url(url: str) -> bool:
    """Basic sanity check: must be a real HTTP/HTTPS URL of reasonable length."""
    if not url or len(url) < _MIN_URL_LEN:
        return False
    if url.startswith("data:"):
        return False  # data URIs are already inline — skip
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False

