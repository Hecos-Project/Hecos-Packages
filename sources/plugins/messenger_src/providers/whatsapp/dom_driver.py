"""
WhatsApp Web DOM & Lexical Editor Driver (2026 WDS Architecture — v2.4).
Encapsulates all Playwright page-level interactions with WhatsApp Web:
  - Phone number normalization & non-critical promo modal dismissal
  - QR code & sync state detection
  - Direct contact chat opening (`send?phone=<digits>`) AND Group chat opening via `#side` search
  - Live 1-click Group discovery via `#group-filter`
  - Group message extraction (`data-id`, `[data-pre-plain-text]`, quoted replies, self vs member markers)
  - Lexical rich-text compose box input (single-block or multi-message)
  - Deterministic outgoing message verification via `#main [data-id]` / `[data-testid^="conv-msg-"]`
    and WDS `<svg><title>wds-ic-*</title></svg>` + `aria-label` delivery indicators
  - File & image attachment upload
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Optional


COMPOSE_BOX_SELECTORS = (
    '#main footer div[contenteditable="true"][role="textbox"]',
    '#main footer div[contenteditable="true"][data-tab="10"]',
    'div[contenteditable="true"][data-testid="conversation-compose-box-input"]',
    '#main footer div[contenteditable="true"]',
    'div[contenteditable="true"][data-tab="10"]',
)

SEND_BUTTON_SELECTORS = (
    '#main footer button[aria-label="Invia"]',
    '#main footer button[aria-label="Send"]',
    '#main footer button[aria-label="Enviar"]',
    '#main footer button[data-tab="11"]',
    '#main footer span[data-icon="wds-ic-send-filled"]',
    '#main footer span[data-icon="send"]',
)

SIDE_SEARCH_SELECTORS = (
    '#side input[data-tab="3"]',
    '#side input[role="textbox"]',
    '#side div[contenteditable="true"][data-tab="3"]',
    '[data-testid="chat-list-search"]',
)

SIDE_CLEAR_SEARCH_SELECTORS = (
    '#side button[aria-label="Annulla ricerca"]',
    '#side button[aria-label="Cancel search"]',
    '#side button[aria-label="Cancelar búsqueda"]',
    '#side span[data-icon="x-alt"]',
)

QR_SELECTORS = (
    'div[data-testid="qrcode"]',
    'canvas[aria-label*="QR"]',
    'canvas[aria-label*="Scan"]',
    'div[data-ref] canvas',
)

INVALID_NUMBER_SELECTORS = (
    'div[data-animate-modal-popup="true"]',
    'div[role="dialog"]',
)

ATTACH_BTN_SELECTORS = (
    '#main footer button[aria-label="Allega"]',
    '#main footer button[aria-label="Attach"]',
    '#main footer button[aria-label="Adjuntar"]',
    '#main footer div[title="Allega"]',
    '#main footer div[title="Attach"]',
    '#main footer span[data-icon="plus-rounded"]',
    '#main footer span[data-icon="plus"]',
    '#main footer span[data-icon="clip"]',
)

MEDIA_SEND_SELECTORS = (
    'div[aria-label="Invia"][role="button"]',
    'div[aria-label="Send"][role="button"]',
    'button[aria-label="Invia"]',
    'button[aria-label="Send"]',
    'span[data-icon="wds-ic-send-filled"]',
    'span[data-icon="send"]',
)


def _norm_ws(value: str) -> str:
    """Normalizes non-breaking spaces (`\\u00a0`) and multiple spaces for reliable title comparison."""
    return re.sub(r"\s+", " ", (value or "").replace("\u00a0", " ")).strip()


def normalize_whatsapp_phone(raw_phone: str, default_country_code: str = "+39") -> tuple[str, str]:
    """
    Normalizes a phone string into (e164_with_plus, digits_only).
    Preserves Italian landline leading '0' while converting '00' international prefix.
    """
    cleaned = re.sub(r"[\s\-\(\)\.]", "", (raw_phone or "").strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    elif not cleaned.startswith("+"):
        cc = (default_country_code or "+39").strip()
        if not cc.startswith("+"):
            cc = "+" + cc
        cleaned = cc + cleaned

    digits = re.sub(r"\D", "", cleaned)
    if len(digits) < 7 or len(digits) > 15:
        raise ValueError(f"Invalid WhatsApp phone number '{raw_phone}' (normalized: '{cleaned}').")
    return f"+{digits}", digits


def is_qr_login_visible(page: Any, timeout_ms: int = 1200) -> bool:
    """Returns True if WhatsApp Web is currently showing the QR login screen."""
    for sel in QR_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=timeout_ms):
                return True
        except Exception:
            continue
    return False


def dismiss_non_critical_modals(page: Any) -> None:
    """
    Dismisses non-blocking WhatsApp Web promo/notification dialogs (e.g. 'Turn on notifications',
    'Ricevi notifiche per WhatsApp') that intercept pointer clicks on `#side`.
    Leaves invalid-phone dialogs untouched when checking phone validity.
    """
    try:
        dismissed = page.evaluate(
            """() => {
                let clicked = false;
                const dialogs = Array.from(document.querySelectorAll('div[role="dialog"][aria-modal="true"]'));
                for (const dlg of dialogs) {
                    const txt = ((dlg.innerText || '') + ' ' + (dlg.getAttribute('aria-label') || '')).toLowerCase();
                    if (
                        txt.includes('non è valido') || txt.includes('invalid') ||
                        txt.includes('non è su whatsapp') || txt.includes("isn't on whatsapp")
                    ) {
                        continue;
                    }
                    const btns = Array.from(dlg.querySelectorAll('button'));
                    for (const b of btns) {
                        const bt = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).toLowerCase();
                        if (
                            bt.includes('chiudi') || bt.includes('close') || bt.includes('non ora') ||
                            bt.includes('not now') || bt.includes('ahora no') || bt.includes('annulla') || bt.includes('cancel')
                        ) {
                            b.click();
                            clicked = true;
                            break;
                        }
                    }
                }
                return clicked;
            }"""
        )
        if dismissed:
            time.sleep(0.25)
    except Exception:
        pass


def _mark_active_chat_digits(page: Any, digits: str) -> None:
    """Tags the current `#main header` title with `digits` so follow-up sends skip full page reload."""
    try:
        page.evaluate(
            """(d) => {
                const hdr = document.querySelector('#main header');
                const title = hdr ? (hdr.innerText || '').split('\\n')[0].trim() : '';
                window.__hecosActiveChat = { digits: d, groupTitle: '', headerTitle: title };
            }""",
            digits,
        )
    except Exception:
        pass


def _mark_active_group_title(page: Any, group_title: str) -> None:
    """Tags the current `#main header` title with `group_title`."""
    try:
        page.evaluate(
            """(g) => {
                const hdr = document.querySelector('#main header');
                const title = hdr ? (hdr.innerText || '').split('\\n')[0].trim() : '';
                window.__hecosActiveChat = { digits: '', groupTitle: g, headerTitle: title };
            }""",
            _norm_ws(group_title).lower(),
        )
    except Exception:
        pass


def _is_target_chat_already_open(page: Any, digits: str, contact_name: Optional[str] = None) -> bool:
    """Checks whether `#main` is already open on `digits` via cached header binding, JID, or title."""
    try:
        suffix = digits[-8:] if len(digits) >= 8 else digits
        matched_cached = page.evaluate(
            """(args) => {
                const hdr = document.querySelector('#main header');
                if (!hdr) return false;
                const currentTitle = (hdr.innerText || '').split('\\n')[0].trim();
                if (
                    window.__hecosActiveChat &&
                    window.__hecosActiveChat.digits === args.digits &&
                    window.__hecosActiveChat.headerTitle &&
                    window.__hecosActiveChat.headerTitle === currentTitle
                ) {
                    return true;
                }
                const el = document.querySelector('#main [data-id]');
                if (el && args.suffix) {
                    const did = el.getAttribute('data-id') || '';
                    if (did.includes(args.suffix + '@')) return true;
                }
                return false;
            }""",
            {"digits": digits, "suffix": suffix},
        )
        if matched_cached:
            return True

        header = page.locator("#main header").first
        if not header.is_visible(timeout=400):
            return False
        header_text = (header.inner_text(timeout=400) or "").strip()
        if not header_text:
            return False

        header_digits = re.sub(r"\D", "", header_text)
        if suffix and suffix in header_digits:
            return True

        if contact_name and not contact_name.lower().startswith("group:"):
            cname = _norm_ws(contact_name).lower()
            first_line = _norm_ws(header_text.splitlines()[0]).lower()
            if cname and (cname == first_line or cname in first_line):
                return True
    except Exception:
        pass
    return False


def is_group_chat_already_open(page: Any, group_title: str) -> bool:
    """Returns True if `#main header`'s primary title matches `group_title`."""
    target_norm = _norm_ws(group_title).lower()
    if not target_norm:
        return False
    try:
        hdr_title = page.evaluate(
            """() => {
                const hdr = document.querySelector('#main header');
                if (!hdr) return '';
                return ((hdr.innerText || '').split('\\n')[0] || '').trim();
            }"""
        )
        cur_norm = _norm_ws(str(hdr_title or "")).lower()
        return bool(cur_norm and cur_norm == target_norm)
    except Exception:
        return False


def _clear_side_search(page: Any) -> None:
    """Clears the left-sidebar search box without closing the active `#main` conversation."""
    for csel in SIDE_CLEAR_SEARCH_SELECTORS:
        try:
            btn = page.locator(csel).first
            if btn.is_visible(timeout=250):
                btn.click(timeout=1000)
                return
        except Exception:
            continue
    for ssel in SIDE_SEARCH_SELECTORS:
        try:
            inp = page.locator(ssel).first
            if inp.is_visible(timeout=200):
                inp.fill("")
                return
        except Exception:
            continue


def open_group_chat_on_page(
    page: Any,
    group_title: str,
    nav_timeout_sec: int = 25,
) -> tuple[Optional[Any], Optional[str]]:
    """
    Opens a WhatsApp group conversation by searching its `group_title` in `#side`,
    performing a trusted Playwright click on the exact matching row, and verifying `#main header`.
    """
    clean_title = _norm_ws(group_title)
    if not clean_title:
        return None, "WhatsApp group title cannot be empty."

    current_url = page.url or ""
    if "web.whatsapp.com" not in current_url:
        try:
            page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=max(12, nav_timeout_sec) * 1000)
        except Exception as exc:
            return None, f"Failed to load WhatsApp Web: {exc}"

    if is_qr_login_visible(page, timeout_ms=500):
        return None, "WhatsApp Web is not logged in (QR code visible). Scan the QR code from your phone."

    # Fast path: group is already open in #main!
    if is_group_chat_already_open(page, clean_title):
        box, err = _find_compose_box(page, total_timeout_sec=4.0)
        if box is not None:
            return box, None

    dismiss_non_critical_modals(page)

    # Locate #side search input (waiting if WhatsApp Web just booted)
    search_box = None
    deadline = time.time() + max(8.0, float(nav_timeout_sec))
    while time.time() < deadline and search_box is None:
        if is_qr_login_visible(page, timeout_ms=250):
            return None, "WhatsApp Web is not logged in (QR code visible)."
        dismiss_non_critical_modals(page)
        for ssel in SIDE_SEARCH_SELECTORS:
            try:
                loc = page.locator(ssel).first
                if loc.is_visible(timeout=250):
                    search_box = loc
                    break
            except Exception:
                continue
        if search_box is None:
            time.sleep(0.3)

    if search_box is None:
        return None, "Could not locate WhatsApp Web sidebar search box (make sure WhatsApp Web finished syncing)."

    try:
        # Ensure 'All' filter is active before searching so archived/group chats appear consistently
        all_btn = page.locator("button#all-filter").first
        if all_btn.is_visible(timeout=400):
            if (all_btn.get_attribute("aria-pressed") or "") != "true":
                all_btn.click(timeout=1500)
                time.sleep(0.25)
        search_box.click(timeout=2000)
        search_box.fill("")
        search_box.fill(clean_title)
        time.sleep(0.65)
    except Exception as exc:
        return None, f"Failed typing group name '{clean_title}' in WhatsApp search box: {exc}"

    # Find exact matching span[title] inside #pane-side (normalizing NBSPs)
    match_info = page.evaluate(
        """(targetNorm) => {
            const norm = (s) => (s || '').replace(/\\u00a0/g, ' ').replace(/\\s+/g, ' ').trim().toLowerCase();
            const spans = Array.from(document.querySelectorAll('#pane-side span[title]'));
            let exactIdx = -1;
            let partialIdx = -1;
            let partialCount = 0;
            const seenTitles = [];
            spans.forEach((sp, i) => {
                const rawT = sp.getAttribute('title') || '';
                const nt = norm(rawT);
                if (!nt) return;
                seenTitles.push(rawT);
                if (exactIdx === -1 && nt === targetNorm) {
                    exactIdx = i;
                } else if (nt.includes(targetNorm) || targetNorm.includes(nt)) {
                    partialIdx = i;
                    partialCount += 1;
                }
            });
            const chosenIdx = exactIdx !== -1 ? exactIdx : (partialCount === 1 ? partialIdx : -1);
            return {
                chosenIdx,
                chosenTitle: chosenIdx !== -1 ? (spans[chosenIdx].getAttribute('title') || '') : '',
                seenTitles: seenTitles.slice(0, 8)
            };
        }""",
        clean_title.lower(),
    )

    chosen_idx = int(match_info.get("chosenIdx", -1))
    if chosen_idx < 0:
        _clear_side_search(page)
        seen = [t for t in (match_info.get("seenTitles") or []) if t]
        seen_hint = f" Visible search results: {seen[:5]}." if seen else ""
        return None, (
            f"WhatsApp group '{clean_title}' was not found in your WhatsApp Web chats.{seen_hint} "
            "Verify the exact group title in Central Hub -> Messenger -> WhatsApp Groups."
        )

    try:
        target_span = page.locator("#pane-side span[title]").nth(chosen_idx)
        target_span.click(timeout=3000)
        time.sleep(0.6)
    except Exception as exc:
        _clear_side_search(page)
        return None, f"Failed clicking WhatsApp group '{clean_title}': {exc}"

    _clear_side_search(page)

    box, err = _find_compose_box(page, total_timeout_sec=10.0)
    if err or box is None:
        return None, err or f"WhatsApp group '{clean_title}' opened, but compose box is unavailable (read-only announcement group?)."

    # Verify #main header matches the chosen group title (preventing misdirected messages!)
    chosen_raw = str(match_info.get("chosenTitle") or clean_title)
    if not is_group_chat_already_open(page, chosen_raw) and not is_group_chat_already_open(page, clean_title):
        hdr_now = page.evaluate(
            "() => { const h = document.querySelector('#main header'); return h ? (h.innerText || '').split('\\n')[0] : ''; }"
        )
        return None, (
            f"Safety abort: expected WhatsApp header '{clean_title}', but active chat header is '{hdr_now}'. "
            "Message was NOT sent."
        )

    _mark_active_group_title(page, chosen_raw)
    return box, None


def scan_groups_on_page(page: Any) -> dict[str, Any]:
    """
    Clicks WhatsApp Web's `#group-filter` button, extracts visible group titles and previews,
    and restores `#all-filter`. Returns `{"ok": True, "groups": [...]}`.
    """
    if "web.whatsapp.com" not in (page.url or ""):
        try:
            page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=25000)
        except Exception as exc:
            return {"ok": False, "error": f"Could not open WhatsApp Web: {exc}", "groups": []}

    if is_qr_login_visible(page, timeout_ms=1000):
        return {
            "ok": False,
            "error": "WhatsApp Web is not logged in (scan QR code first via 'Open / Link WhatsApp Web').",
            "groups": [],
        }

    dismiss_non_critical_modals(page)
    _clear_side_search(page)

    try:
        gf_btn = page.locator("button#group-filter").first
        if gf_btn.is_visible(timeout=1500):
            gf_btn.click(timeout=2500)
            time.sleep(0.6)

        groups = page.evaluate(
            """() => {
                const rows = Array.from(document.querySelectorAll('#pane-side [role="row"], #pane-side [role="listitem"]'));
                const out = [];
                const seen = new Set();
                for (const r of rows) {
                    const sp = r.querySelector('span[title]');
                    const rawTitle = sp ? (sp.getAttribute('title') || '') : ((r.innerText || '').split('\\n')[0] || '');
                    const cleanTitle = rawTitle.replace(/\\u00a0/g, ' ').replace(/\\s+/g, ' ').trim();
                    if (!cleanTitle || seen.has(cleanTitle.toLowerCase())) continue;
                    seen.add(cleanTitle.toLowerCase());
                    const lines = (r.innerText || '').split('\\n').map(l => l.trim()).filter(Boolean);
                    out.push({
                        title: cleanTitle,
                        raw_title: rawTitle.trim(),
                        last_activity: lines[1] || ''
                    });
                }
                return out;
            }"""
        )
    except Exception as exc:
        return {"ok": False, "error": f"Failed scanning WhatsApp groups: {exc}", "groups": []}
    finally:
        try:
            af_btn = page.locator("button#all-filter").first
            if af_btn.is_visible(timeout=1000):
                af_btn.click(timeout=1500)
        except Exception:
            pass

    return {"ok": True, "groups": groups or []}


def read_recent_group_messages(page: Any, group_title: str, max_messages: int = 12) -> dict[str, Any]:
    """
    Opens `group_title` (instant if already active in `#main`) and extracts the last `max_messages`
    chat messages with `data_id`, `sender`, `text`, `quoted_text`, and `from_self`.
    """
    _, err = open_group_chat_on_page(page, group_title, nav_timeout_sec=18)
    if err:
        return {"ok": False, "error": err, "messages": []}

    try:
        messages = page.evaluate(
            """(limit) => {
                const nodes = Array.from(document.querySelectorAll('#main [data-id]'));
                const slice = nodes.slice(-Math.max(5, limit));
                const results = [];

                for (const n of slice) {
                    const dataId = n.getAttribute('data-id') || '';
                    if (!dataId) continue;

                    const preEl = n.querySelector('[data-pre-plain-text]');
                    const prePlain = preEl ? (preEl.getAttribute('data-pre-plain-text') || '') : '';
                    const arias = Array.from(n.querySelectorAll('[aria-label]'))
                        .map(a => (a.getAttribute('aria-label') || '').trim());

                    const fromSelf =
                        dataId.startsWith('true_') ||
                        arias.some(a => {
                            const low = a.toLowerCase();
                            return low === 'tu:' || low === 'you:' || low === 'tú:';
                        });

                    // Extract sender from prePlain ('[10:15, 26/11/2026] Sender Name: ') or aria-label ('Sender:')
                    let sender = '';
                    if (prePlain) {
                        const m = prePlain.match(/\\]\\s*([^:]+):\\s*$/);
                        if (m && m[1]) sender = m[1].trim();
                    }
                    if (!sender) {
                        for (const a of arias) {
                            if (a.endsWith(':') && a.length > 1 && a.length < 45) {
                                sender = a.slice(0, -1).trim();
                                break;
                            }
                        }
                    }

                    // Extract main message body (excluding quoted header and timestamp)
                    let text = '';
                    if (preEl) {
                        const selSpans = Array.from(preEl.querySelectorAll('span.selectable-text, [data-testid="selectable-text"]'));
                        if (selSpans.length > 0) {
                            text = selSpans.map(s => s.innerText || '').join('\\n').trim();
                        } else {
                            text = (preEl.innerText || '').trim();
                        }
                    } else {
                        const selSpans = Array.from(n.querySelectorAll('span.selectable-text, [data-testid="selectable-text"]'));
                        if (selSpans.length > 0) {
                            text = selSpans[selSpans.length - 1].innerText.trim();
                        }
                    }

                    // Extract optional quoted reply snippet if present outside preEl
                    let quotedText = '';
                    const quoteNode = n.querySelector('[aria-label*="Messaggio citato"], [aria-label*="Quoted message"], [data-testid="quoted-message"]');
                    if (quoteNode) {
                        quotedText = (quoteNode.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 200);
                    }

                    // Skip system encryption banners / deleted message placeholders without selectable text
                    if (!text) continue;

                    results.push({
                        data_id: dataId,
                        sender: sender || (fromSelf ? 'Me' : 'Member'),
                        text,
                        quoted_text: quotedText,
                        from_self: fromSelf
                    });
                }
                return results;
            }""",
            int(max_messages),
        )
        return {"ok": True, "messages": messages or []}
    except Exception as exc:
        return {"ok": False, "error": f"Failed reading messages in group '{group_title}': {exc}", "messages": []}


def _find_compose_box(page: Any, total_timeout_sec: float = 18.0) -> tuple[Optional[Any], Optional[str]]:
    """
    Polls for either the conversation compose box, QR screen, or an invalid-number modal.
    Returns (locator, error_message).
    """
    deadline = time.time() + max(5.0, total_timeout_sec)
    while time.time() < deadline:
        if is_qr_login_visible(page, timeout_ms=250):
            return None, (
                "WhatsApp Web is not logged in (QR code visible). "
                "Open WhatsApp Web and scan the QR code from your phone."
            )

        for msel in INVALID_NUMBER_SELECTORS:
            try:
                modal = page.locator(msel).first
                if modal.is_visible(timeout=150):
                    mtxt = (modal.inner_text(timeout=300) or "").lower()
                    if any(
                        kw in mtxt
                        for kw in (
                            "non è valido",
                            "invalid",
                            "url",
                            "non è su whatsapp",
                            "isn't on whatsapp",
                            "no está en whatsapp",
                        )
                    ):
                        return None, f"Phone number is invalid or not registered on WhatsApp ({mtxt[:120].strip()})."
            except Exception:
                pass

        for sel in COMPOSE_BOX_SELECTORS:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=250):
                    return loc, None
            except Exception:
                continue

        time.sleep(0.3)

    return None, (
        "Timed out waiting for WhatsApp Web chat input box. "
        "Make sure WhatsApp Web has finished syncing and you are logged in."
    )


def open_chat_for_recipient(
    page: Any,
    digits: str,
    contact_name: Optional[str] = None,
    nav_timeout_sec: int = 30,
    group_title: Optional[str] = None,
) -> tuple[Optional[Any], Optional[str]]:
    """Opens either a WhatsApp group (when `group_title` is set) or a direct phone conversation."""
    if group_title and group_title.strip():
        return open_group_chat_on_page(page, group_title.strip(), nav_timeout_sec=nav_timeout_sec)

    current_url = page.url or ""
    if "web.whatsapp.com" in current_url and _is_target_chat_already_open(page, digits, contact_name):
        box, err = _find_compose_box(page, total_timeout_sec=4.0)
        if box is not None:
            return box, None

    target_url = f"https://web.whatsapp.com/send?phone={digits}"
    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=max(10, nav_timeout_sec) * 1000)
    except Exception as exc:
        return None, f"Failed to navigate to WhatsApp Web chat URL: {exc}"

    box, err = _find_compose_box(page, total_timeout_sec=float(max(12, nav_timeout_sec)))
    if box is not None:
        _mark_active_chat_digits(page, digits)
    return box, err


def _snapshot_outgoing_state(page: Any) -> dict[str, Any]:
    """
    Captures all existing message `data-id` / `data-testid="conv-msg-*"` identifiers in `#main`
    before clicking Send (works across both 2026 hex stanza IDs like `3EB0...` and legacy `true_...`).
    """
    try:
        data = page.evaluate(
            """() => {
                const nodes = Array.from(
                    document.querySelectorAll('#main [data-id], #main [data-testid^="conv-msg-"]')
                );
                const ids = nodes
                    .map(n => n.getAttribute('data-id') || n.getAttribute('data-testid'))
                    .filter(Boolean);
                const rowCount = document.querySelectorAll('#main [role="row"], #main div.message-out').length;
                return { ids, rowCount };
            }"""
        )
        return {
            "ids": set(data.get("ids") or []),
            "row_count": int(data.get("rowCount") or 0),
        }
    except Exception:
        return {"ids": set(), "row_count": 0}


def _click_send_or_enter(page: Any) -> None:
    for sel in SEND_BUTTON_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=300):
                btn.click(timeout=1500)
                return
        except Exception:
            continue
    page.keyboard.press("Enter")


def _verify_outgoing_stanza(
    page: Any,
    before_state: dict[str, Any],
    wait_sec: float = 6.0,
) -> dict[str, Any]:
    """
    Deterministically verifies whether WhatsApp Web created and ACKed a new outgoing message
    by inspecting newly added `#main [data-id]` / `[data-testid^="conv-msg-"]` message nodes,
    WDS `<svg><title>wds-ic-*</title></svg>`, `[data-icon]`, and `[aria-label]` status markers.
    Returns {"dispatched": bool, "verified": bool, "msg_id": str, "error": str}.
    """
    prev_ids: set[str] = before_state.get("ids") or set()
    prev_row_count: int = int(before_state.get("row_count") or 0)
    start_ts = time.time()
    deadline = start_ts + wait_sec

    detected_id = ""
    bubble_created_at = 0.0

    while time.time() < deadline:
        try:
            probe = page.evaluate(
                """(prevList) => {
                    const prevSet = new Set(prevList || []);
                    const nodes = Array.from(
                        document.querySelectorAll('#main [data-id], #main [data-testid^="conv-msg-"]')
                    );
                    const newNodes = nodes.filter(n => {
                        const id = n.getAttribute('data-id') || n.getAttribute('data-testid');
                        return id && !prevSet.has(id);
                    });
                    const allRows = Array.from(document.querySelectorAll('#main [role="row"], #main div.message-out'));

                    const compose = document.querySelector('#main footer div[contenteditable="true"]');
                    const composeEmpty = compose ? (compose.innerText || '').trim().length === 0 : true;

                    let target = null;
                    for (let idx = newNodes.length - 1; idx >= 0; idx--) {
                        const cand = newNodes[idx];
                        const titles = Array.from(cand.querySelectorAll('svg title'))
                            .map(t => (t.textContent || '').toLowerCase());
                        const arias = Array.from(cand.querySelectorAll('[aria-label]'))
                            .map(a => (a.getAttribute('aria-label') || '').trim().toLowerCase());
                        const icons = Array.from(cand.querySelectorAll('[data-icon]'))
                            .map(i => (i.getAttribute('data-icon') || '').toLowerCase());
                        const did = cand.getAttribute('data-id') || '';

                        const looksOutgoing =
                            did.startsWith('true_') ||
                            did.startsWith('3EB0') ||
                            cand.querySelector('[data-testid="msg-meta"]') !== null ||
                            titles.some(t => t.includes('wds-ic-') || t.includes('msg-')) ||
                            icons.some(i => i.includes('check') || i.includes('tail-out') || i.includes('clock') || i.includes('time')) ||
                            arias.some(a =>
                                a === 'tu:' || a === 'you:' || a === 'tú:' ||
                                a.includes('inviato') || a.includes('consegnato') || a.includes('letto') ||
                                a.includes('in attesa') || a.includes('sent') || a.includes('delivered') ||
                                a.includes('read') || a.includes('pending') || a.includes('sending') ||
                                a.includes('enviado') || a.includes('entregado') || a.includes('leído')
                            );
                        if (looksOutgoing) {
                            target = cand;
                            break;
                        }
                    }
                    if (!target && newNodes.length > 0) {
                        target = newNodes[newNodes.length - 1];
                    }

                    if (!target) {
                        return { newCount: 0, rowCount: allRows.length, composeEmpty };
                    }

                    const dataId = target.getAttribute('data-id') || target.getAttribute('data-testid') || '';
                    const svgTitles = Array.from(target.querySelectorAll('svg title'))
                        .map(el => (el.textContent || '').trim().toLowerCase());
                    const ariaLabels = Array.from(target.querySelectorAll('[aria-label]'))
                        .map(el => (el.getAttribute('aria-label') || '').trim().toLowerCase());
                    const dataIcons = Array.from(target.querySelectorAll('[data-icon]'))
                        .map(el => (el.getAttribute('data-icon') || '').trim().toLowerCase());

                    const hasError =
                        svgTitles.some(t => t.includes('error') || t.includes('alert')) ||
                        dataIcons.some(i => i.includes('error') || i.includes('alert')) ||
                        ariaLabels.some(a => a.includes('errore') || a.includes('error') || a.includes('failed') || a.includes('non inviato'));

                    const hasClock =
                        svgTitles.some(t => t.includes('clock') || t.includes('time') || t.includes('pending')) ||
                        dataIcons.some(i => i.includes('time') || i.includes('clock')) ||
                        ariaLabels.some(a => a.includes('attesa') || a.includes('pending') || a.includes('sending') || a.includes('pendiente'));

                    const hasCheck =
                        svgTitles.some(t =>
                            t.includes('wds-ic-sent') || t.includes('wds-ic-delivered') || t.includes('wds-ic-read') ||
                            t.includes('check') || t.includes('dblcheck')
                        ) ||
                        dataIcons.some(i => i.includes('check') || i.includes('dblcheck')) ||
                        ariaLabels.some(a =>
                            a.includes('inviato') || a.includes('consegnato') || a.includes('letto') ||
                            a.includes('sent') || a.includes('delivered') || a.includes('read') ||
                            a.includes('enviado') || a.includes('entregado') || a.includes('leído')
                        );

                    const allNewIds = newNodes.map(n => n.getAttribute('data-id') || n.getAttribute('data-testid')).filter(Boolean);

                    return {
                        newCount: newNodes.length,
                        rowCount: allRows.length,
                        composeEmpty,
                        dataId,
                        allNewIds,
                        hasError,
                        hasClock,
                        hasCheck,
                        svgTitles,
                        ariaLabels
                    };
                }""",
                list(prev_ids),
            )

            is_new_bubble = (probe.get("newCount", 0) > 0) or (probe.get("rowCount", 0) > prev_row_count)
            if is_new_bubble:
                if not bubble_created_at:
                    bubble_created_at = time.time()
                detected_id = probe.get("dataId") or detected_id
                all_new_ids = probe.get("allNewIds") or ([detected_id] if detected_id else [])

                if probe.get("hasError"):
                    return {
                        "dispatched": False,
                        "verified": False,
                        "msg_id": detected_id,
                        "new_ids": all_new_ids,
                        "error": "WhatsApp Web displayed a delivery failure icon on the outgoing message.",
                    }

                if probe.get("hasCheck"):
                    return {
                        "dispatched": True,
                        "verified": True,
                        "msg_id": detected_id,
                        "new_ids": all_new_ids,
                        "error": "",
                    }

                if (
                    probe.get("composeEmpty")
                    and not probe.get("hasClock")
                    and (time.time() - bubble_created_at) >= 0.8
                ):
                    return {
                        "dispatched": True,
                        "verified": True,
                        "msg_id": detected_id,
                        "new_ids": all_new_ids,
                        "error": "",
                    }
        except Exception:
            pass

        time.sleep(0.2)

    if bubble_created_at > 0:
        return {
            "dispatched": True,
            "verified": False,
            "msg_id": detected_id,
            "new_ids": [detected_id] if detected_id else [],
            "error": "",
        }

    return {
        "dispatched": False,
        "verified": False,
        "msg_id": "",
        "new_ids": [],
        "error": "WhatsApp Web did NOT generate a new outgoing message bubble in the chat.",
    }


def send_text_on_page(
    page: Any,
    digits: str,
    e164: str,
    text: str,
    single_block: bool = True,
    contact_name: Optional[str] = None,
    nav_timeout_sec: int = 30,
    group_title: Optional[str] = None,
) -> dict[str, Any]:
    """Executes the full chat/group open + Lexical input + send + stanza verification sequence."""
    compose_box, err = open_chat_for_recipient(
        page,
        digits,
        contact_name=contact_name,
        nav_timeout_sec=nav_timeout_sec,
        group_title=group_title,
    )
    if err or compose_box is None:
        return {"ok": False, "error": err or "Compose box unavailable."}

    before_state = _snapshot_outgoing_state(page)

    try:
        compose_box.click(timeout=2000)
        time.sleep(0.12)

        try:
            existing_draft = (compose_box.inner_text(timeout=400) or "").strip()
            if existing_draft:
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                time.sleep(0.1)
        except Exception:
            pass

        normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized_text.split("\n")

        if single_block:
            for idx, line in enumerate(lines):
                if line:
                    page.keyboard.insert_text(line)
                if idx < len(lines) - 1:
                    page.keyboard.press("Shift+Enter")
            time.sleep(0.15)
            _click_send_or_enter(page)
        else:
            non_empty = [ln for ln in lines if ln.strip()] or [normalized_text]
            for ln in non_empty:
                page.keyboard.insert_text(ln)
                time.sleep(0.12)
                _click_send_or_enter(page)
                time.sleep(0.2)

    except Exception as exc:
        return {"ok": False, "error": f"Error typing or clicking Send in WhatsApp Web: {exc}"}

    ver = _verify_outgoing_stanza(page, before_state, wait_sec=6.0)
    target_label = f"group:{group_title}" if group_title else e164
    if not ver["dispatched"]:
        return {
            "ok": False,
            "error": ver["error"] or f"Message was not dispatched to {target_label}.",
        }

    return {
        "ok": True,
        "verified": ver["verified"],
        "warning": not ver["verified"],
        "msg_id": ver.get("msg_id", ""),
        "new_ids": ver.get("new_ids", []),
        "recipient": target_label,
    }


def send_files_on_page(
    page: Any,
    digits: str,
    e164: str,
    file_paths: list[str],
    caption: str = "",
    contact_name: Optional[str] = None,
    nav_timeout_sec: int = 30,
    group_title: Optional[str] = None,
) -> dict[str, Any]:
    """Uploads one or more local files/images into the target WhatsApp Web chat or group."""
    valid_files = [os.path.abspath(p) for p in file_paths if os.path.isfile(p)]
    if not valid_files:
        return {"ok": False, "error": f"File(s) not found on disk: {file_paths}"}

    compose_box, err = open_chat_for_recipient(
        page,
        digits,
        contact_name=contact_name,
        nav_timeout_sec=nav_timeout_sec,
        group_title=group_title,
    )
    if err or compose_box is None:
        return {"ok": False, "error": err or "Compose box unavailable."}

    before_state = _snapshot_outgoing_state(page)

    try:
        clicked_attach = False
        for asel in ATTACH_BTN_SELECTORS:
            try:
                abtn = page.locator(asel).first
                if abtn.is_visible(timeout=500):
                    abtn.click(timeout=1500)
                    clicked_attach = True
                    break
            except Exception:
                continue

        if not clicked_attach:
            return {"ok": False, "error": "Could not locate Attach button in WhatsApp Web."}

        time.sleep(0.4)
        all_images = all(
            os.path.splitext(p)[1].lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov")
            for p in valid_files
        )
        input_sel = 'input[type="file"][accept*="image"]' if all_images else 'input[type="file"]'
        file_input = page.locator(input_sel).first
        file_input.set_input_files(valid_files if len(valid_files) > 1 else valid_files[0])

        time.sleep(1.2)
        if caption and caption.strip():
            try:
                cap_box = page.locator('div[contenteditable="true"][role="textbox"]').first
                if cap_box.is_visible(timeout=2000):
                    cap_box.click()
                    cap_lines = caption.strip().replace("\r\n", "\n").replace("\r", "\n").split("\n")
                    for c_i, c_ln in enumerate(cap_lines):
                        if c_ln:
                            page.keyboard.insert_text(c_ln)
                        if c_i < len(cap_lines) - 1:
                            page.keyboard.press("Shift+Enter")
                    time.sleep(0.2)
            except Exception:
                pass

        sent_clicked = False
        for msel in MEDIA_SEND_SELECTORS:
            try:
                mbtn = page.locator(msel).last
                if mbtn.is_visible(timeout=2000):
                    mbtn.click(timeout=1500)
                    sent_clicked = True
                    break
            except Exception:
                continue
        if not sent_clicked:
            page.keyboard.press("Enter")

    except Exception as exc:
        return {"ok": False, "error": f"Failed to attach/send media on WhatsApp Web: {exc}"}

    ver = _verify_outgoing_stanza(page, before_state, wait_sec=8.0)
    target_label = f"group:{group_title}" if group_title else e164
    return {
        "ok": ver["dispatched"],
        "verified": ver["verified"],
        "warning": ver["dispatched"] and not ver["verified"],
        "msg_id": ver.get("msg_id", ""),
        "new_ids": ver.get("new_ids", []),
        "recipient": target_label,
        "error": "" if ver["dispatched"] else (ver["error"] or "Media upload was not confirmed in chat."),
    }
