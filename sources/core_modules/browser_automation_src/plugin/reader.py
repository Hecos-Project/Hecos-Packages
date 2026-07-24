"""
browser/reader.py
DOM Intelligence Layer — reads structured content from the current page.

NOTE: All functions here are designed to be called from WITHIN the browser thread
(i.e. inside a lambda passed to engine._run_on_browser_thread). They access
engine._state["page"] directly to avoid re-entering the job queue (deadlock).
"""

import logging
import os
import sys

logger = logging.getLogger("browser")

_here = os.path.dirname(__file__)
if _here not in sys.path:
    sys.path.insert(0, _here)
import engine


def _page():
    """Returns the current page from shared state — safe to call from browser thread."""
    return engine._state.get("page")


def get_page_text(max_chars: int = 4000) -> str:
    """Return all visible text from the current page, trimmed to max_chars."""
    page = _page()
    if page is None or page.is_closed():
        return "⚠️ Browser is not open."
    try:
        text = page.evaluate("() => document.body.innerText")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n...[truncated, {len(text) - max_chars} more chars]"
        return text.strip()
    except Exception as e:
        logger.error(f"[BROWSER] get_page_text error: {e}")
        return f"[BROWSER] Could not read page text: {e}"


def get_links(max_results: int = 30) -> str:
    """Return all hyperlinks on the current page as a numbered list (label → url)."""
    page = _page()
    if page is None or page.is_closed():
        return "⚠️ Browser is not open."
    try:
        links = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href]'))
                .map(a => ({ label: a.innerText.trim().slice(0, 80), href: a.href }))
                .filter(l => l.label && l.href.startsWith('http'))
                .slice(0, 50);
        }""")
        if not links:
            return "[BROWSER] No links found on this page."
        result = f"[BROWSER] Links on current page ({len(links[:max_results])}):\n"
        result += "\n".join(f"  [{i}] {l['label']} → {l['href']}" for i, l in enumerate(links[:max_results]))
        return result
    except Exception as e:
        return f"[BROWSER] get_links error: {e}"


def find_element(text_or_aria: str):
    """
    Find a page element by its visible text, aria-label, name, or CSS selector.
    Returns the Playwright Locator or None.
    Tries multiple strategies in order of specificity.
    """
    page = _page()
    if page is None or page.is_closed():
        return None
    try:
        # 1. aria-label (most reliable for icon-based UI like Google/YouTube)
        loc = page.get_by_label(text_or_aria)
        if loc.count() > 0:
            return loc.first

        # 2. name attribute (handles Google's search box: name="q")
        loc = page.locator(f"input[name='{text_or_aria}'], textarea[name='{text_or_aria}']")
        if loc.count() > 0:
            return loc.first

        # 3. Placeholder text (case insensitive)
        loc = page.get_by_placeholder(text_or_aria)
        if loc.count() > 0:
            return loc.first

        # 4. Visible text match
        loc = page.get_by_text(text_or_aria, exact=False)
        if loc.count() > 0:
            return loc.first

        # 5. Raw CSS selector fallback
        try:
            loc = page.locator(text_or_aria)
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass

        return None
    except Exception as e:
        logger.debug(f"[BROWSER] find_element error: {e}")
        return None


def find_input_element(label_or_selector: str):
    """
    Find an input field specifically. Tries name, placeholder, aria-label, then CSS.
    Handles common cases like Google's search box (name='q').
    """
    page = _page()
    if page is None or page.is_closed():
        return None

    strategies = [
        # 1. name attribute
        f"input[name='{label_or_selector}'], textarea[name='{label_or_selector}']",
        # 2. id attribute
        f"input#{label_or_selector}, textarea#{label_or_selector}",
        # 3. placeholder (case insensitive)
        f"input[placeholder*='{label_or_selector}' i], textarea[placeholder*='{label_or_selector}' i]",
        # 4. aria-label (case insensitive)
        f"input[aria-label*='{label_or_selector}' i], textarea[aria-label*='{label_or_selector}' i]",
        # 5. title attribute
        f"input[title*='{label_or_selector}' i]",
    ]

    for selector in strategies:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0:
                return loc
        except Exception:
            continue

    # Fallback: try as raw CSS or aria-label via playwright API
    try:
        loc = page.get_by_label(label_or_selector)
        if loc.count() > 0:
            return loc.first
    except Exception:
        pass

    try:
        loc = page.get_by_placeholder(label_or_selector)
        if loc.count() > 0:
            return loc.first
    except Exception:
        pass

    return None


def get_inputs() -> str:
    """Return all form inputs (text fields, buttons) on the current page."""
    page = _page()
    if page is None or page.is_closed():
        return "⚠️ Browser is not open."
    try:
        inputs = page.evaluate("""() => {
            const fields = [];
            document.querySelectorAll('input, textarea, button, select').forEach(el => {
                fields.push({
                    tag: el.tagName,
                    type: el.type || '',
                    name: el.name || el.id || el.placeholder || el.ariaLabel || el.innerText?.trim() || ''
                });
            });
            return fields.slice(0, 40);
        }""")
        if not inputs:
            return "[BROWSER] No input elements found on this page."
        result = "[BROWSER] Interactive elements:\n"
        result += "\n".join(f"  [{i}] <{f['tag'].lower()} type={f['type']}> name/id={f['name']}" for i, f in enumerate(inputs))
        return result
    except Exception as e:
        return f"[BROWSER] get_inputs error: {e}"
