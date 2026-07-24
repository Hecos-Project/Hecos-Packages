"""
MODULE: Messenger — WhatsApp Adapter  [BETA]
DESCRIPTION: Sends messages via WhatsApp Web using the existing Playwright/CDP browser
             already connected in Hecos browser engine.

STATUS: BETA — relies on WhatsApp Web UI selectors which can break on WA updates.
NOTE:   The pyautogui blind-send fallback has been intentionally removed.
        It never worked reliably and could not verify delivery. If CDP is
        unavailable, the adapter now returns a clear error so the user knows
        what to fix instead of silently failing.
"""

from __future__ import annotations
from urllib.parse import quote
from hecos.core.logging import logger


# ── WhatsApp Web selectors (update here if WA changes UI) ──────────────────
_WA_MSG_BOX_SELECTOR  = 'div[contenteditable="true"][data-testid="conversation-compose-box-input"]'
_WA_MSG_BOX_FALLBACK  = 'div[contenteditable="true"][tabindex="10"]'
_WA_MSG_SENT_SELECTOR = 'span[data-icon="msg-check"], span[data-icon="msg-dblcheck"]'
_WA_LOADING_SELECTOR  = 'div[data-testid="intro-md-beta-logo-dark"], div[data-testid="qrcode"]'


def _send_via_playwright(phone: str, text: str, send_as_single_block: bool = True, cdp_timeout: int = 30, worker_timeout: int = 60) -> str:
    """
    Launches the whatsapp_cdp_worker.py subprocess to send the message via Playwright/CDP.
    This avoids the "Cannot switch to a different thread" (greenlet error)
    that occurs if sync_playwright is used from a different AI thread.
    Returns the worker's output string, or an error message on failure.
    """
    import subprocess
    import sys
    import json
    import os

    worker_script = os.path.join(os.path.dirname(__file__), "whatsapp_cdp_worker.py")
    if not os.path.exists(worker_script):
        return "❌ WhatsApp: worker script not found. Package may be corrupted, try reinstalling."

    input_data = json.dumps({"phone": phone, "text": text, "single_block": send_as_single_block, "cdp_timeout": cdp_timeout})

    try:
        result = subprocess.run(
            [sys.executable, worker_script],
            input=input_data,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=worker_timeout
        )

        output = result.stdout.strip()

        if result.returncode != 0:
            err = result.stderr.strip() or "unknown error"
            logger.warning("MESSENGER/WhatsApp", f"CDP worker exited with error: {err}")
            return f"❌ WhatsApp send failed (worker error): {err}"

        if not output:
            return "❌ WhatsApp: worker returned no output. CDP may not be reachable."

        # Return the text output from the worker (e.g. "✅ Message sent...")
        return output

    except subprocess.TimeoutExpired:
        logger.warning("MESSENGER/WhatsApp", f"CDP worker timed out after {worker_timeout}s.")
        return (
            f"❌ WhatsApp: send operation timed out after {worker_timeout}s. "
            "Chrome may be busy or WhatsApp Web is slow to respond. "
            "Try increasing the Worker Execution Timeout in Messenger settings."
        )
    except Exception as e:
        logger.warning("MESSENGER/WhatsApp", f"CDP worker execution error: {e}")
        return f"❌ WhatsApp: unexpected error during send: {e}"


def send(cfg, recipient: str, text: str, is_app_open: bool = False) -> str:
    """Send a WhatsApp message via Playwright/CDP. Returns a clear error if CDP is unavailable."""
    if not cfg.enabled:
        return "⚠️ WhatsApp adapter is disabled. Enable it in Messenger settings."

    # Normalize phone number ONLY if it looks like a number (no letters)
    phone = recipient.strip()
    has_letters = any(c.isalpha() for c in phone)

    if not has_letters:
        if not phone.startswith("+"):
            cc = getattr(cfg, "phone_country_code", "+39") or "+39"
            phone = cc + phone.lstrip("0")
        phone = phone.replace(" ", "").replace("-", "")

    # Check CDP availability first and give a clear error if not connected
    import socket
    def _port_open(p: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex(('127.0.0.1', p)) == 0

    cdp_port = int(getattr(cfg, "cdp_port", 9222) or 9222)
    if not _port_open(cdp_port):
        return (
            f"❌ WhatsApp: Chrome CDP port {cdp_port} is not reachable. "
            "Make sure Chrome is open and launched with: "
            f"chrome.exe --remote-debugging-port={cdp_port}. "
            "Check the Tray Dashboard for more information."
        )

    logger.info("MESSENGER/WhatsApp", f"Sending via Playwright/CDP to {phone}...")
    single_block = getattr(cfg, "send_as_single_block", True)
    cdp_timeout = int(getattr(cfg, "cdp_timeout", 30))
    worker_timeout = int(getattr(cfg, "worker_timeout", 60))
    result = _send_via_playwright(phone, text, single_block, cdp_timeout, worker_timeout)
    logger.info("MESSENGER/WhatsApp", f"Send result: {result}")
    return result


def check(cfg) -> str:
    if not cfg.enabled:
        return "DISABLED"

    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return "NOT INSTALLED (run: pip install playwright && python -m playwright install chromium)"

    import socket
    def is_port_open(p):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            return s.connect_ex(('127.0.0.1', p)) == 0

    if is_port_open(9222):
        return "BETA (Playwright ready — CDP active on port 9222)"
    else:
        return "BETA (Playwright ready — CDP not connected. Launch Chrome with --remote-debugging-port=9222)"

