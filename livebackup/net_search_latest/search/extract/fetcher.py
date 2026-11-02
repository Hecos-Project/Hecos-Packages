"""
search/extract/fetcher.py
Fetches and reads page content across Clearnet and Tor (.onion) domains.
Supports HTTP fast path and optional Playwright headless DOM fallback.
"""
from __future__ import annotations

import logging
from typing import Dict, Any

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("browser.search.fetcher")

from .. import http_client
from .cleaner import clean_html


def fetch_and_clean_page(
    url: str,
    max_chars: int = 5000,
    network: str = "auto",
    use_playwright_fallback: bool = True
) -> Dict[str, Any]:
    """
    Downloads and extracts readable text from a URL.
    Works for both Clearnet and Dark Web (.onion) sites.
    """
    if not url.startswith("http"):
        url = "https://" + url if not ".onion" in url else "http://" + url

    is_onion = ".onion" in url.lower()
    net = "tor" if is_onion else ("clearnet" if network == "clearnet" else "auto")

    hecos_logger.info(f"[FETCHER] Fetching page: {url} (network={net})")

    html_content = ""
    status_code = 0
    final_url = url
    fetch_engine = "requests"

    # Step 1: Fast HTTP path
    try:
        resp = http_client.get(url, network=net, timeout=18.0)
        status_code = resp.status_code
        final_url = resp.url
        if resp.status_code == 200:
            html_content = resp.text
            hecos_logger.info(f"[FETCHER] Direct HTTP 200 OK from {url} ({len(html_content)} bytes)")
        else:
            hecos_logger.warning(f"[FETCHER] HTTP {resp.status_code} from {url}")
    except Exception as http_err:
        hecos_logger.warning(f"[FETCHER] Direct HTTP request failed for {url}: {http_err}")

    # Step 2: Playwright fallback for clearnet sites blocked by anti-bot / cloudflare / JS
    if not html_content and use_playwright_fallback and not is_onion:
        try:
            try:
                from hecos.modules.browser_automation.plugin import engine
            except (ImportError, ValueError):
                from ...plugin import engine
            if engine.is_available():
                hecos_logger.info(f"[FETCHER:PLAYWRIGHT] Attempting headless browser DOM fallback for {url}...")
                def _pw_fetch():
                    if not (engine._state["browser"] and engine._state["browser"].is_connected()):
                        engine.launch(headless=True)
                    page = engine._state.get("page")
                    if page and not page.is_closed():
                        page.goto(url, timeout=20000, wait_until="domcontentloaded")
                        return page.content(), page.url, 200
                    return "", url, 500

                content, final_url, status_code = engine._run_on_browser_thread(_pw_fetch, timeout=25.0)
                if content:
                    html_content = content
                    fetch_engine = "playwright"
                    hecos_logger.info(f"[FETCHER:PLAYWRIGHT] Fallback succeeded for {url} ({len(html_content)} bytes)")
        except Exception as pw_err:
            hecos_logger.debug(f"[FETCHER:PLAYWRIGHT] Playwright fallback error: {pw_err}")

    if not html_content:
        hecos_logger.warning(f"[FETCHER] Failed to load webpage {url} (HTTP {status_code})")
        return {
            "ok": False,
            "url": url,
            "status_code": status_code,
            "title": "",
            "description": "",
            "text": "",
            "error": f"Could not load webpage (HTTP {status_code}). Site may be offline or blocking scrapers."
        }

    # Step 3: Clean and structure
    cleaned = clean_html(html_content, max_chars=max_chars)
    hecos_logger.info(f"[FETCHER] Page cleaned via {cleaned['method']}: title='{cleaned['title'][:40]}', text={len(cleaned['text'])} chars")
    return {
        "ok": True,
        "url": final_url,
        "status_code": status_code,
        "title": cleaned["title"],
        "description": cleaned["description"],
        "text": cleaned["text"],
        "clean_method": cleaned["method"],
        "fetch_engine": fetch_engine,
        "error": None
    }
