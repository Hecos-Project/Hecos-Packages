"""
browser/engine.py
Playwright browser lifecycle manager — persistent singleton for Hecos.

ARCHITECTURE: All Playwright operations are executed on a single dedicated
"BrowserThread" via a job queue. This is mandatory because Playwright's
sync API is thread-affine: page objects MUST be used from the thread that
created them. Using a shared queue ensures all calls (launch, click, navigate,
close_tab, etc.) always run on the same thread regardless of which Flask
worker or AI-brain thread issues the call.
"""

import os
import queue
import threading
import socket
import logging
from typing import Callable, Any

logger = logging.getLogger('browser')

def _get_browser_cfg():
    try:
        from hecos.app.config import ConfigManager
        return ConfigManager().config.get("plugins", {}).get("BROWSER", {})
    except Exception:
        return {}


_INSTALL_MSG = (
    "Playwright or Chromium binaries are missing. "
    "Please run: 'python -m playwright install chromium' in your terminal."
)

# ── Browser Thread (singleton) ────────────────────────────────────────────────

_job_queue: queue.Queue = queue.Queue()
_browser_thread: threading.Thread | None = None
_browser_thread_lock = threading.Lock()


def _browser_worker():
    """The single dedicated thread that owns all Playwright objects."""
    while True:
        try:
            job = _job_queue.get(timeout=0.5)
            if job is None:
                break  # Poison pill — shutdown
            fn, result_holder = job
            try:
                result_holder["result"] = fn()
            except Exception as e:
                result_holder["error"] = e
            finally:
                result_holder["done"].set()
        except queue.Empty:
            continue


def _ensure_browser_thread():
    """Starts the browser worker thread if not already running."""
    global _browser_thread
    with _browser_thread_lock:
        if _browser_thread is None or not _browser_thread.is_alive():
            _browser_thread = threading.Thread(
                target=_browser_worker,
                daemon=True,
                name="HecosPlaywrightThread"
            )
            _browser_thread.start()
            logger.info("[BROWSER] Playwright thread started.")


def _run_on_browser_thread(fn: Callable, timeout: float = 60.0) -> Any:
    """
    Executes `fn` on the dedicated Playwright thread and returns the result.
    Blocks the calling thread until done or timeout.
    Raises any exception that occurred inside fn.
    """
    _ensure_browser_thread()
    holder = {"result": None, "error": None, "done": threading.Event()}
    _job_queue.put((fn, holder))
    if not holder["done"].wait(timeout=timeout):
        raise TimeoutError(f"[BROWSER] Operation timed out after {timeout}s")
    if holder["error"] is not None:
        raise holder["error"]
    return holder["result"]


# ── Global state (owned exclusively by the browser thread) ────────────────────

_state = {
    "pw_instance": None,
    "browser": None,
    "page": None,
    "last_error": "",
}


# ── Internal helpers (MUST be called from browser thread only) ────────────────

def _is_available() -> bool:
    try:
        import playwright  # noqa
        return True
    except ImportError:
        return False


def _ensure_chromium(pw_instance=None):
    try:
        from playwright.sync_api import sync_playwright
        def _check(pw):
            try:
                path = pw.chromium.executable_path
                if not path or not os.path.exists(path):
                    raise FileNotFoundError("Missing binary")
                return path
            except Exception:
                raise FileNotFoundError(
                    "Chromium binaries are missing from the system. "
                    "To fix this, please run: 'python -m playwright install chromium' in your terminal."
                )
        if pw_instance:
            return _check(pw_instance)
        else:
            with sync_playwright() as pw:
                return _check(pw)
    except ImportError:
        raise ImportError(
            "Playwright library is not installed. "
            "Please run: 'pip install playwright' inside Hecos root."
        )


def _is_page_usable(p) -> bool:
    try:
        if p.is_closed():
            return False
        _ = p.url
        return True
    except Exception:
        return False


def _is_hecos_page(url: str) -> bool:
    if not url:
        return True
    return (
        url.startswith("chrome://")
        or url.startswith("about:")
        or "localhost:7070" in url
        or "127.0.0.1:7070" in url
    )


def _is_port_open(p):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)
        return s.connect_ex(('127.0.0.1', p)) == 0


# ── Public API — all delegate to browser thread ───────────────────────────────

def launch(headless: bool = None, block_ads: bool = None, timeout: int = None,
           mode: str = None, cdp_port: int = None) -> bool:
    """Start or connect to the Playwright browser. Thread-safe via job queue."""
    cfg = _get_browser_cfg()
    if headless is None:
        headless = cfg.get("headless", False)
    if block_ads is None:
        block_ads = cfg.get("block_ads", True)
    if timeout is None:
        timeout = int(cfg.get("nav_timeout", 30)) * 1000
    if mode is None:
        mode = cfg.get("browser_engine_mode", "cdp_mode")
    if cdp_port is None:
        cdp_port = int(cfg.get("cdp_port", 9222))

    def _launch():
        _state["last_error"] = ""

        if not _is_available():
            _state["last_error"] = _INSTALL_MSG
            return False

        from playwright.sync_api import sync_playwright

        if _state["browser"] and _state["browser"].is_connected():
            logger.debug(f"[BROWSER] Already connected (Mode: {mode}).")
            return True

        if not _state["pw_instance"]:
            _state["pw_instance"] = sync_playwright().start()

        _mode = mode

        if _mode != "cdp_mode" and _is_port_open(cdp_port):
            logger.info(f"[BROWSER] CDP port {cdp_port} open → upgrading to cdp_mode.")
            _mode = "cdp_mode"

        if _mode == "cdp_mode":
            logger.info(f"[BROWSER] Attempting CDP connection → http://localhost:{cdp_port}")
            try:
                endpoint = f"http://localhost:{cdp_port}"
                _state["browser"] = _state["pw_instance"].chromium.connect_over_cdp(endpoint)
                ctx = _state["browser"].contexts[0] if _state["browser"].contexts else _state["browser"].new_context()
                _state["page"] = ctx.pages[0] if ctx.pages else ctx.new_page()
                _state["page"].set_default_timeout(timeout)
                ctx_count = len(_state["browser"].contexts)
                page_count = sum(len(c.pages) for c in _state["browser"].contexts)
                logger.info(f"[BROWSER] ✅ CDP connected on port {cdp_port} — contexts={ctx_count}, pages={page_count}")
                return True
            except Exception as cdp_e:
                _state["last_error"] = f"CDP Takeover failed. Details: {cdp_e}."
                logger.error(f"[BROWSER] ❌ CDP failed on port {cdp_port}: {cdp_e}. Falling back to app_mode.")
                _mode = "app_mode"

        if _mode != "cdp_mode":
            try:
                _ensure_chromium(_state["pw_instance"])
            except Exception as er:
                _state["last_error"] = str(er)
                return False

            _state["browser"] = _state["pw_instance"].chromium.launch(
                headless=headless,
                channel="chrome",
                args=[
                    "--no-sandbox",
                    "--disable-infobars",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            ctx = _state["browser"].new_context(
                viewport={"width": 1000, "height": 900},
                ignore_https_errors=True,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            )
            if block_ads:
                ctx.route("**/*.{png,jpg,gif,webp,svg}", lambda r: r.abort())
                ctx.route(
                    "**/googleadservices/**,**/doubleclick.net/**,**/googlesyndication.com/**",
                    lambda r: r.abort()
                )
            _state["page"] = ctx.new_page()
            _state["page"].set_default_timeout(timeout)

            logger.info("[BROWSER] ✅ Isolated Chromium (App Mode) launched.")
            return True

    try:
        return _run_on_browser_thread(_launch)
    except Exception as e:
        logger.error(f"[BROWSER] Launch error: {e}")
        return False


def close():
    """Close the browser and stop Playwright."""
    def _close():
        try:
            if _state["browser"]:
                _state["browser"].close()
            if _state["pw_instance"]:
                _state["pw_instance"].stop()
        except Exception as e:
            logger.debug(f"[BROWSER] Close error: {e}")
        finally:
            _state["browser"] = None
            _state["page"] = None
            _state["pw_instance"] = None

    try:
        _run_on_browser_thread(_close)
    except Exception as e:
        logger.debug(f"[BROWSER] close() error: {e}")


def get_page():
    """Return the current active Playwright Page object (via browser thread).
    Never returns the Hecos chat page — creates a new tab if needed.
    """
    def _get_page():
        # Invalidate if current page is closed/detached
        if _state["page"] is not None and not _is_page_usable(_state["page"]):
            logger.debug("[BROWSER] get_page: cached page is detached/closed — searching for another.")
            _state["page"] = None

        # Invalidate if current page is Hecos UI
        if _state["page"] is not None:
            try:
                current_url = _state["page"].url or ""
                if _is_hecos_page(current_url):
                    logger.debug(f"[BROWSER] get_page: current page is Hecos UI ({current_url}) — will open new tab.")
                    _state["page"] = None
            except Exception:
                _state["page"] = None

        if _state["page"] is None:
            if _state["browser"] and _state["browser"].is_connected():
                valid_pages = []
                for ctx in _state["browser"].contexts:
                    for p in ctx.pages:
                        if not _is_page_usable(p):
                            continue
                        try:
                            u = p.url or ""
                            if not _is_hecos_page(u):
                                valid_pages.append(p)
                        except Exception:
                            continue

                if len(valid_pages) == 1:
                    _state["page"] = valid_pages[0]
                    return _state["page"]
                elif len(valid_pages) > 1:
                    raise RuntimeError(
                        f"Ambiguous active tab. Found {len(valid_pages)} open tabs. "
                        "You MUST call BROWSER__list_tabs and BROWSER__switch_tab(index) to explicitly select the correct tab before interacting."
                    )
                # No external page — open new blank tab
                new_page = _open_new_browser_tab_internal()
                if new_page:
                    return new_page

            # Browser not running — launch fresh
            if not _launch_internal():
                return None

        return _state["page"]

    return _run_on_browser_thread(_get_page)


def _launch_internal() -> bool:
    """Internal launch without queuing (already on browser thread)."""
    return launch.__wrapped__() if hasattr(launch, "__wrapped__") else False


def _open_new_browser_tab_internal():
    """Create a blank new tab — must be called from browser thread."""
    browser = _state["browser"]
    if not browser or not browser.is_connected():
        return None
    try:
        ctx = browser.contexts[0] if len(browser.contexts) > 0 else browser.new_context()
        page = ctx.new_page()
        _state["page"] = page
        logger.info("[BROWSER] New tab created in existing browser context.")
        return page
    except Exception as e:
        logger.error(f"[BROWSER] Could not create new tab: {e}")
        return None


def close_tab() -> bool:
    """Close the currently active tab."""
    def _close_tab():
        page = _state.get("page")
        if page and not page.is_closed():
            try:
                page.close()
            except Exception as e:
                logger.debug(f"[BROWSER] Error closing tab: {e}")
                return False

        _state["page"] = None
        if _state["browser"] and _state["browser"].is_connected():
            pages = []
            for ctx in _state["browser"].contexts:
                pages.extend(p for p in ctx.pages if _is_page_usable(p) and not _is_hecos_page(p.url or ""))
            _state["page"] = pages[-1] if pages else None
        return True

    try:
        return _run_on_browser_thread(_close_tab)
    except Exception as e:
        logger.error(f"[BROWSER] close_tab error: {e}")
        return False


def new_tab(url: str = "about:blank"):
    """Open a new tab and navigate to url. Returns the new Page object."""
    def _new_tab():
        if not _state["browser"] or not _state["browser"].is_connected():
            return None

        ctx = _state["browser"].contexts[0] if _state["browser"].contexts else _state["browser"].new_context()
        _state["page"] = ctx.new_page()

        if url and url != "about:blank":
            _url = url if url.startswith("http") else "https://" + url
            _state["page"].goto(_url, wait_until="domcontentloaded", timeout=timeout)
        return _state["page"]

    try:
        return _run_on_browser_thread(_new_tab)
    except Exception as e:
        logger.error(f"[BROWSER] new_tab error: {e}")
        return None


def get_last_error() -> str:
    return _state["last_error"]


def is_running() -> bool:
    return _state["browser"] is not None and _state["browser"].is_connected()


def find_chrome_executable() -> str:
    user_local = os.environ.get("LOCALAPPDATA", "")
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(user_local, r"Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return ""


def launch_external_browser(port: int = 9222) -> str:
    import subprocess
    exe = find_chrome_executable()
    if not exe:
        return "Errore: Non ho trovato Google Chrome o Microsoft Edge installati nei percorsi standard."

    user_data = os.path.join(os.environ.get("TEMP", "."), "hecos_browser_profile")
    if not os.path.exists(user_data):
        os.makedirs(user_data, exist_ok=True)

    cmd = [
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data}",
        "--no-first-run",
        "--no-default-browser-check"
    ]

    try:
        subprocess.Popen(cmd, creationflags=0x00000008, close_fds=True)
        return f"Browser lanciato con successo sulla porta {port}."
    except Exception as e:
        return f"Errore durante il lancio del browser: {e}"


def list_tabs() -> list:
    """Returns a list of all open tabs/pages in the current browser context."""
    def _list_tabs():
        if not _state["browser"]:
            return []
        tabs = []
        try:
            for context in _state["browser"].contexts:
                for idx, page in enumerate(context.pages):
                    try:
                        title = page.title()
                        url = page.url
                        is_active = page == _state["page"]
                        tabs.append({"id": idx, "title": title, "url": url, "active": is_active})
                    except Exception as pe:
                        logger.debug(f"[BROWSER] Tab [{idx}] unreadable: {pe}")
            logger.info(f"[BROWSER] list_tabs → {len(tabs)} tabs found")
        except Exception as e:
            logger.error(f"[BROWSER] list_tabs error: {e}")
        return tabs

    try:
        return _run_on_browser_thread(_list_tabs)
    except Exception as e:
        logger.error(f"[BROWSER] list_tabs error: {e}")
        return []


def switch_tab(index: int) -> bool:
    """Switches the active page handle to the tab at the given index."""
    def _switch_tab():
        if not _state["browser"]:
            return False
        pages = []
        for context in _state["browser"].contexts:
            pages.extend(context.pages)
        if 0 <= index < len(pages):
            _state["page"] = pages[index]
            _state["page"].bring_to_front()
            logger.info(f"[BROWSER] ✅ Switched to tab [{index}]: '{_state['page'].title()}'")
            return True
        logger.warning(f"[BROWSER] switch_tab({index}) — index out of range (max: {len(pages) - 1})")
        return False

    try:
        return _run_on_browser_thread(_switch_tab)
    except Exception as e:
        logger.error(f"[BROWSER] switch_tab error: {e}")
        return False
