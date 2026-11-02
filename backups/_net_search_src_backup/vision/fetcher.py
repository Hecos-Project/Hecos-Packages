"""
vision/fetcher.py
Downloads thumbnail images from a SearchSession's results.
Uses the same HTTP client as the rest of the net_search module for consistency.
All fetches go through the server-side proxy to bypass client-side ad-blockers.
"""
from __future__ import annotations

import logging
import urllib.request
import urllib.error
from typing import Optional

logger = logging.getLogger("hecos.net_search.vision.fetcher")

# Default per-image download timeout (seconds)
DEFAULT_TIMEOUT = 5


def fetch_image_bytes(url: str, timeout: int = DEFAULT_TIMEOUT) -> Optional[bytes]:
    """
    Downloads a single image URL and returns its raw bytes.
    Returns None on any error (network, HTTP, timeout).
    Tries with a browser-like User-Agent to avoid 403s.
    """
    if not url or not isinstance(url, str):
        return None

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            # Accept only actual image content
            if content_type and not content_type.startswith("image/"):
                # Some CDNs serve HTML on redirect — skip silently
                logger.debug(f"[VisionFetcher] Skipping non-image content-type '{content_type}' for {url[:80]}")
                return None
            data = resp.read()
            if len(data) < 512:
                # Tiny files are likely 1x1 tracking pixels — skip
                logger.debug(f"[VisionFetcher] Skipping suspiciously small image ({len(data)} bytes) for {url[:80]}")
                return None
            return data
    except urllib.error.HTTPError as e:
        logger.debug(f"[VisionFetcher] HTTP {e.code} for {url[:80]}")
        return None
    except urllib.error.URLError as e:
        logger.debug(f"[VisionFetcher] URL error for {url[:80]}: {e.reason}")
        return None
    except Exception as e:
        logger.debug(f"[VisionFetcher] Unexpected error for {url[:80]}: {e}")
        return None


def fetch_image_bytes_via_proxy(url: str, base_url: str = "http://127.0.0.1:5000", timeout: int = DEFAULT_TIMEOUT) -> Optional[bytes]:
    """
    Downloads an image through the Hecos server-side proxy (/api/hsearch/media_proxy).
    This bypasses client-side ad-blockers and domain blacklists, using the same
    mechanism already proven to work for the chat cards.
    """
    import urllib.parse
    proxy_url = f"{base_url}/api/hsearch/media_proxy?url={urllib.parse.quote(url, safe='')}"
    return fetch_image_bytes(proxy_url, timeout=timeout)

