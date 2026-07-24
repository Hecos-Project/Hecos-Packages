"""
Browser Automation - LLM Tool Bridge
Entry point loaded by Hecos module_scanner. Exposes BrowserTools class
with all callable methods matching the tool_schema in hpkg_manifest.toml.

All Playwright interactions are dispatched via engine._run_on_browser_thread()
so they always execute on the single dedicated HecosPlaywrightThread.
"""

import logging
import os
import sys

logger = logging.getLogger("browser")

# Absolute-path imports so this works both as a package and via importlib.util
_here = os.path.dirname(__file__)
if _here not in sys.path:
    sys.path.insert(0, _here)

import engine
import reader


def _get_browser_cfg():
    try:
        from hecos.app.config import ConfigManager
        return ConfigManager().config.get("plugins", {}).get("BROWSER", {})
    except Exception:
        return {}


def _bt(fn, timeout=None):
    """Shorthand: run fn on the Playwright thread and return result."""
    if timeout is None:
        cfg = _get_browser_cfg()
        timeout = float(cfg.get("thread_timeout", 60.0))
    return engine._run_on_browser_thread(fn, timeout=timeout)


class BrowserTools:
    """Hecos AI Browser — Playwright-powered web interaction tools."""

    # ── Navigation ────────────────────────────────────────────────────────────

    def open_url(self, url: str) -> str:
        """Opens a URL in the Hecos AI browser. If the browser is already running, opens a new tab."""
        if not url.startswith("http"):
            url = "https://" + url

        logger.info(f"[BROWSER] open_url requested: {url}")

        def _do_open():
            # If browser not running, launch it first
            if not (engine._state["browser"] and engine._state["browser"].is_connected()):
                from engine import launch as _launch
                ok = _launch.__wrapped__() if hasattr(_launch, "__wrapped__") else False
                # Direct internal launch since we're already on the browser thread
                _do_launch_internal()

            # Open in a new tab (or use existing page if first launch)
            browser = engine._state["browser"]
            if not browser or not browser.is_connected():
                raise RuntimeError(f"Could not launch browser. {engine._state['last_error']}")

            cfg = _get_browser_cfg()
            t_nav = int(cfg.get("nav_timeout", 30)) * 1000

            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            # If there's already a page from launch and it's blank, reuse it
            existing = engine._state.get("page")
            if existing and not existing.is_closed():
                try:
                    if existing.url in ("about:blank", "chrome://newtab/", ""):
                        existing.goto(url, timeout=t_nav, wait_until="domcontentloaded")
                        return existing.title(), existing.url
                except Exception:
                    pass
            # Otherwise open a new tab
            p = ctx.new_page()
            engine._state["page"] = p
            p.goto(url, timeout=t_nav, wait_until="domcontentloaded")
            return p.title(), p.url

        def _do_launch_internal():
            """Launch without queuing — must be on browser thread already."""
            import socket as _socket
            from playwright.sync_api import sync_playwright as _swp
            s = engine._state
            s["last_error"] = ""
            if s["browser"] and s["browser"].is_connected():
                return True
            if not s["pw_instance"]:
                s["pw_instance"] = _swp().start()
            # Try CDP first
            cdp_port = 9222
            def _port_open(p):
                with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as sock:
                    sock.settimeout(0.1)
                    return sock.connect_ex(('127.0.0.1', p)) == 0
            if _port_open(cdp_port):
                try:
                    endpoint = f"http://localhost:{cdp_port}"
                    s["browser"] = s["pw_instance"].chromium.connect_over_cdp(endpoint)
                    ctx = s["browser"].contexts[0] if s["browser"].contexts else s["browser"].new_context()
                    s["page"] = ctx.pages[0] if ctx.pages else ctx.new_page()
                    logger.info(f"[BROWSER] ✅ CDP connected on port {cdp_port}")
                    return True
                except Exception as e:
                    logger.warning(f"[BROWSER] CDP failed: {e}")
            # App mode fallback
            try:
                s["browser"] = s["pw_instance"].chromium.launch(
                    headless=False, channel="chrome",
                    args=["--no-sandbox", "--disable-infobars", "--disable-blink-features=AutomationControlled"]
                )
                ctx = s["browser"].new_context(viewport={"width": 1000, "height": 900}, ignore_https_errors=True)
                s["page"] = ctx.new_page()
                logger.info("[BROWSER] ✅ App mode launched.")
                return True
            except Exception as e:
                s["last_error"] = str(e)
                return False

        try:
            title, current_url = _bt(_do_open)
            logger.info(f"[BROWSER] ✅ Browser opened: {title}")
            return (
                f"✅ Browser opened: {title} — {current_url}\n"
                f"Page is ready. Now proceed with the NEXT step of the task immediately "
                f"(e.g. type_in_field to search, click_element, etc.). Do NOT wait for user confirmation."
            )
        except Exception as e:
            logger.error(f"[BROWSER] Navigation error: {e}")
            return f"⚠️ Navigation error: {e}"


    def get_current_url(self) -> str:
        """Returns the URL currently loaded in the Hecos browser."""
        def _get():
            p = engine._state.get("page")
            if p and not p.is_closed():
                return p.url
            return None
        try:
            url = _bt(_get)
            return url if url else "Browser is not open. Use BROWSER__open_url first."
        except Exception as e:
            return f"⚠️ {e}"

    def go_back(self) -> str:
        """Navigate the browser back to the previous page."""
        def _go():
            p = engine._state.get("page")
            if not p or p.is_closed():
                raise RuntimeError("Browser is not open.")
            cfg = _get_browser_cfg()
            t_wait = int(cfg.get("wait_timeout", 8)) * 1000
            p.go_back(timeout=t_wait)
            return p.url
        try:
            url = _bt(_go)
            return f"✅ Back → {url}"
        except Exception as e:
            return f"⚠️ go_back error: {e}"

    # ── Reading ───────────────────────────────────────────────────────────────

    def get_page_text(self, max_chars: int = 4000) -> str:
        """Returns all visible text from the current browser page."""
        def _read():
            return reader.get_page_text(max_chars=max_chars)
        try:
            return _bt(_read)
        except Exception as e:
            return f"⚠️ get_page_text error: {e}"

    def get_links(self, max_results: int = 30) -> str:
        """Returns all hyperlinks on the current page as a numbered list."""
        def _read():
            return reader.get_links(max_results=max_results)
        try:
            return _bt(_read)
        except Exception as e:
            return f"⚠️ get_links error: {e}"

    def get_inputs(self) -> str:
        """Lists all input fields, buttons and form elements on the current page."""
        def _read():
            return reader.get_inputs()
        try:
            return _bt(_read)
        except Exception as e:
            return f"⚠️ get_inputs error: {e}"

    def get_title(self) -> str:
        """Returns the title of the current browser page."""
        def _get():
            p = engine._state.get("page")
            if not p or p.is_closed():
                return "Browser is not open."
            return p.title()
        try:
            return _bt(_get)
        except Exception as e:
            return f"⚠️ {e}"

    # ── Interaction ───────────────────────────────────────────────────────────

    def click_element(self, text_or_selector: str) -> str:
        """Clicks a page element by its visible text label or CSS selector."""
        import time

        def _click():
            p = engine._state.get("page")
            if not p or p.is_closed():
                raise RuntimeError("Browser is not open.")
            loc = reader.find_element(text_or_selector)
            if loc:
                loc.click()
                time.sleep(0.5)
                return f"✅ Clicked: '{text_or_selector}'. Proceed with the NEXT step if the task is not yet complete."
            # Fallback: try as CSS selector
            cfg = _get_browser_cfg()
            t_action = int(cfg.get("action_timeout", 5)) * 1000
            p.click(text_or_selector, timeout=t_action)
            time.sleep(0.5)
            return f"✅ Clicked selector: '{text_or_selector}'. Proceed with the NEXT step if the task is not yet complete."

        try:
            return _bt(_click)
        except Exception as e:
            return f"⚠️ click_element error: {e}"

    def type_in_field(self, label_or_selector: str, text: str, press_enter: bool = False) -> str:
        """Finds an input field and types text into it.
        Uses key-by-key typing to properly trigger JavaScript event handlers on
        sites like YouTube and Google. Optionally presses Enter to submit.
        """
        import time

        def _type():
            p = engine._state.get("page")
            if not p or p.is_closed():
                raise RuntimeError("Browser is not open. Call BROWSER__open_url first.")
            cfg = _get_browser_cfg()
            t_action = int(cfg.get("action_timeout", 5)) * 1000
            t_wait = int(cfg.get("wait_timeout", 8)) * 1000

            loc = reader.find_input_element(label_or_selector)
            if loc is None:
                loc = p.locator("input[type='text'], input[type='search'], textarea").first
            loc.click(timeout=t_action)
            loc.press_sequentially(text, delay=50)
            if press_enter:
                time.sleep(0.5)
                loc.press("Enter")
                try:
                    p.wait_for_load_state("domcontentloaded", timeout=t_wait)
                except Exception:
                    pass
            result = f"✅ Typed '{text}' in '{label_or_selector}'" + (" + Enter" if press_enter else "")
            if press_enter:
                result += (
                    "\nSearch submitted. The page is now loading results. "
                    "Proceed immediately with the NEXT step: read the results with "
                    "BROWSER__get_page_text or BROWSER__get_links, then click the desired item."
                )
            return result

        try:
            return _bt(_type)
        except Exception as e:
            return f"⚠️ type_in_field error: {e}"

    def scroll(self, direction: str = "down", amount: int = 300) -> str:
        """Scrolls the browser page up or down."""
        def _scroll():
            p = engine._state.get("page")
            if not p or p.is_closed():
                raise RuntimeError("Browser is not open.")
            delta = amount if direction == "down" else -amount
            p.mouse.wheel(0, delta)
            return f"✅ Scrolled {direction} by {amount}px"
        try:
            return _bt(_scroll)
        except Exception as e:
            return f"⚠️ scroll error: {e}"

    def press_key(self, key: str) -> str:
        """Presses a keyboard key in the browser context."""
        def _press():
            p = engine._state.get("page")
            if not p or p.is_closed():
                raise RuntimeError("Browser is not open.")
            p.keyboard.press(key)
            return f"✅ Key pressed: {key}"
        try:
            return _bt(_press)
        except Exception as e:
            return f"⚠️ press_key error: {e}"

    def run_js(self, code: str) -> str:
        """Executes JavaScript in the browser and returns the result."""
        def _js():
            p = engine._state.get("page")
            if not p or p.is_closed():
                raise RuntimeError("Browser is not open.")
            result = p.evaluate(code)
            return str(result) if result is not None else "(no return value)"
        try:
            return _bt(_js)
        except Exception as e:
            return f"⚠️ run_js error: {e}"

    def screenshot(self) -> str:
        """Takes a screenshot of the current browser viewport."""
        def _shot():
            import time
            p = engine._state.get("page")
            if not p or p.is_closed():
                raise RuntimeError("Browser is not open.")
            screenshots_dir = os.path.join(os.environ.get("USERPROFILE", "."), "hecos_browser_screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)
            fname = f"browser_{int(time.time())}.png"
            fpath = os.path.join(screenshots_dir, fname)
            p.screenshot(path=fpath)
            return f"[[IMG:{fname}]]"
        try:
            return _bt(_shot)
        except Exception as e:
            return f"⚠️ screenshot error: {e}"

    # ── Tab Management ────────────────────────────────────────────────────────

    def list_tabs(self) -> str:
        """List all open tabs/pages in the current browser."""
        if not engine.is_running():
            import engine as _engine
            ok = _engine.launch()
            if not ok:
                return "CDP connection is not active. Launch browser with BROWSER__open_url or use AUTOMATION__get_browser_tabs."
        tabs = engine.list_tabs()
        if not tabs:
            return "No tabs found."
        return "\n".join(f"[{t['id']}] {'● ACTIVE' if t['active'] else '  '} {t['title']} ({t['url']})" for t in tabs)

    def switch_tab(self, index: int) -> str:
        """Switches the active browser focus to a specific tab by its ID."""
        ok = engine.switch_tab(index)
        if ok:
            def _title():
                p = engine._state.get("page")
                return p.title() if p else "?"
            try:
                title = _bt(_title)
            except Exception:
                title = "?"
            return f"✅ Switched to tab [{index}]: {title}"
        return f"⚠️ Could not switch to tab {index}."

    def new_tab(self, url: str = "") -> str:
        """Opens a new tab in the browser."""
        if not engine.is_running():
            return "Browser is not open. Use BROWSER__open_url first."
        try:
            p = engine.new_tab(url if url else "about:blank")
            if p is None:
                return "⚠️ Could not open new tab."
            def _title():
                return p.title() if not p.is_closed() else "?"
            title = _bt(_title)
            if url:
                return f"✅ New tab opened: {title}"
            return "✅ New blank tab opened."
        except Exception as e:
            return f"⚠️ new_tab error: {e}"

    def close_tab(self) -> str:
        """Closes the currently active browser tab."""
        ok = engine.close_tab()
        return "✅ Tab closed." if ok else "⚠️ Could not close tab."

    def close(self) -> str:
        """Closes the entire Hecos AI browser window."""
        engine.close()
        return "✅ Browser closed."

    # ✨ Slash Commands ✨

    def slash_b(self, args: str) -> str:
        if not args:
            return "Devi specificare un URL o una ricerca. Esempio: /b youtube.com oppure /b gatti divertenti"

        url = args.strip()
        if not url.startswith("http"):
            if " " in url or "." not in url:
                import urllib.parse
                url = "https://google.com/search?q=" + urllib.parse.quote(url)
            else:
                url = "https://" + url

        return self.open_url(url)

    def slash_b_close(self, args: str = "") -> str:
        return self.close()

    def slash_b_tabs(self, args: str = "") -> str:
        return self.list_tabs()

    def slash_b_back(self, args: str = "") -> str:
        return self.go_back()

    def slash_b_click(self, args: str) -> str:
        if not args:
            return "Devi specificare cosa cliccare. Esempio: /b_click Accedi"
        return self.click_element(args.strip())

    def slash_b_type(self, args: str) -> str:
        if not args or "|" not in args:
            return "Devi specificare il campo e il testo separati da |. Esempio: /b_type cerca | gatti"
        label, text = args.split("|", 1)
        return self.type_in_field(label.strip(), text.strip(), press_enter=False)

    def slash_b_scroll(self, args: str) -> str:
        d = args.strip().lower() if args else "down"
        return self.scroll(direction=d)

    def slash_b_shot(self, args: str = "") -> str:
        return self.screenshot()

    def slash_b_new(self, args: str = "") -> str:
        return self.new_tab(args.strip())

    def slash_b_close_tab(self, args: str = "") -> str:
        return self.close_tab()

    def slash_b_switch(self, args: str) -> str:
        if not args or not args.strip().isdigit():
            return "Devi specificare l'ID della scheda. Usa /b_tabs per vedere gli ID."
        return self.switch_tab(int(args.strip()))


# Module-level export expected by Hecos hpm loader
tools = BrowserTools()
