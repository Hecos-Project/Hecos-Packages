"""
Authorized WhatsApp Group Background Listener & Anti-Self-Loop Ledger (v2.4).
Polls ONLY WhatsApp groups explicitly authorized by the user (`inbound_mode != 'off'`),
establishing a baseline watermark on first observation so historical messages are never
re-answered, and enforcing multi-layer self-echo protection so Hecos/Urania NEVER replies
to its own outgoing WhatsApp messages.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from typing import Any, Callable, Optional

from hecos.core.logging import logger
from ...core.base_provider import InboundCallback
from .config import WhatsAppConfig, WhatsAppGroupConfig


_PERSONA_SIGNATURE_PREFIX_RE = re.compile(r"^\s*\*?\[([^\[\]\r\n]{1,36})\]\*?(?:\s|$)")
_MENTION_TAG_RE = re.compile(r"@([A-Za-z0-9_]{2,24})\b")

if not hasattr(sys, "_hecos_wa_listener_state"):
    sys._hecos_wa_listener_state = {  # type: ignore[attr-defined]
        "thread": None,
        "stop_event": None,
        "seen_ids": {},      # norm_group_title -> set[str]
        "sent_ids": set(),   # stanza IDs created by Hecos
        "sent_texts": [],    # list[tuple[float, str]] recent Hecos outbound texts
    }

_state: dict[str, Any] = sys._hecos_wa_listener_state  # type: ignore[attr-defined]
_ledger_lock = threading.Lock()


def _norm_txt(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").replace("\u00a0", " ")).strip().lower()


def record_hecos_whatsapp_outbound(text: str = "", msg_ids: Optional[list[str]] = None) -> None:
    """Records stanza IDs and normalized text sent by Hecos so the listener ignores self-echoes."""
    now = time.time()
    nt = _norm_txt(text)
    with _ledger_lock:
        if msg_ids:
            for mid in msg_ids:
                if mid:
                    _state["sent_ids"].add(str(mid))
        if nt:
            _state["sent_texts"].append((now, nt))
        # Prune old text entries (> 10 minutes) and cap ID set
        _state["sent_texts"][:] = [(ts, t) for (ts, t) in _state["sent_texts"] if (now - ts) <= 600.0]
        if len(_state["sent_ids"]) > 2000:
            _state["sent_ids"].clear()


def is_authored_by_hecos(data_id: str, text: str) -> bool:
    """Returns True if a WhatsApp message bubble was sent by Hecos/Urania."""
    if not text:
        return True
    # 1. Explicit *[Persona]* signature prefix
    if _PERSONA_SIGNATURE_PREFIX_RE.match(text):
        return True

    nt = _norm_txt(text)
    now = time.time()
    with _ledger_lock:
        if data_id and data_id in _state["sent_ids"]:
            return True
        for ts, sent_nt in _state["sent_texts"]:
            if (now - ts) <= 300.0 and sent_nt and (nt == sent_nt or sent_nt in nt or nt in sent_nt):
                return True
    return False


def _evaluate_group_trigger(
    grp: WhatsAppGroupConfig,
    msg: dict[str, Any],
) -> tuple[bool, str, Optional[str]]:
    """
    Evaluates whether `msg` in `grp` should trigger an AI reply.
    Returns `(should_respond, cleaned_text, target_persona_name)`.
    """
    raw_text = str(msg.get("text") or "").strip()
    data_id = str(msg.get("data_id") or "")
    from_self = bool(msg.get("from_self", False))

    if not raw_text or is_authored_by_hecos(data_id, raw_text):
        return False, "", None

    mode = str(getattr(grp, "inbound_mode", "off") or "off").lower()
    if mode == "off":
        return False, "", None

    text_low = raw_text.lower()
    mentions = [m.lower() for m in _MENTION_TAG_RE.findall(raw_text)]
    kws = [k.strip().lower().lstrip("@") for k in (getattr(grp, "inbound_keywords", "") or "").split(",") if k.strip()]

    _hecos_phonetics = ("hecos", "ecos", "echos", "ekos", "iqos", "haicos", "aicos", "haikos", "aikos", "heicos", "eicos")
    target_persona: Optional[str] = (getattr(grp, "default_persona", "") or "").strip() or None
    for m_tok in mentions:
        if "urania" in m_tok:
            target_persona = "Urania"
            break
        if any(hp in m_tok for hp in _hecos_phonetics):
            target_persona = "hecos"
            break

    has_known_mention = any(
        ("urania" in m or any(hp in m for hp in _hecos_phonetics) or m in kws)
        for m in mentions
    )
    has_keyword = any(re.search(rf"\b{re.escape(kw)}\b", text_low) for kw in kws if kw)

    if not target_persona and has_keyword:
        if re.search(r"\burania\b", text_low):
            target_persona = "Urania"
        elif re.search(r"\b(?:hecos|ecos|echos|ekos|iqos|haicos|aicos|haikos|eicos)\b", text_low):
            target_persona = "hecos"

    should_respond = False
    if mode == "mention":
        should_respond = has_known_mention
    elif mode == "keyword":
        should_respond = has_known_mention or has_keyword
    elif mode == "all":
        # In 'all' mode: respond to all messages from other group members,
        # and to @mentions/keywords when the account owner types from their own phone!
        should_respond = (not from_self) or has_known_mention or has_keyword

    if not should_respond:
        return False, "", None

    # Strip leading @urania / @hecos / @haicos tag cleanly before sending to LLM
    cleaned = re.sub(
        r"@(?:urania[a-z0-9_]*|hecos[a-z0-9_]*|ecos|echos|ekos|iqos|haicos|aicos|haikos|eicos)\b",
        "",
        raw_text,
        flags=re.IGNORECASE,
    ).strip()
    if not cleaned:
        cleaned = raw_text

    return True, cleaned, target_persona


def start_whatsapp_group_listener(
    cfg: WhatsAppConfig,
    poll_fn: Callable[[list[str]], dict[str, Any]],
    inbound_callback: Optional[InboundCallback],
) -> None:
    """Starts or restarts the background WhatsApp group listener if any group has `inbound_mode != 'off'`."""
    stop_whatsapp_group_listener()

    if not cfg or not cfg.enabled or not inbound_callback:
        return

    watched_groups = [
        g for g in (cfg.groups or [])
        if g.enabled and (g.group_title or g.name).strip() and g.inbound_mode != "off"
    ]
    if not watched_groups:
        return

    stop_ev = threading.Event()
    interval = max(4, int(getattr(cfg, "inbound_poll_seconds", 8) or 8))

    def _worker() -> None:
        titles = [(g.group_title or g.name).strip() for g in watched_groups]
        logger.info(
            "MESSENGER/WhatsApp",
            f"Group listener active (every {interval}s) for {len(titles)} group(s): {', '.join(titles)}",
        )
        while not stop_ev.is_set():
            try:
                res = poll_fn(titles)
                if res and res.get("ok") and isinstance(res.get("groups_data"), dict):
                    gdata_map = res["groups_data"]
                    for grp in watched_groups:
                        gtitle = (grp.group_title or grp.name).strip()
                        gkey = _norm_title(gtitle)
                        g_res = gdata_map.get(gtitle) or {}
                        if not g_res.get("ok"):
                            continue
                        msgs = g_res.get("messages") or []

                        # Establish baseline watermark on first poll so old history is never replayed!
                        if gkey not in _state["seen_ids"]:
                            _state["seen_ids"][gkey] = {
                                str(m.get("data_id")) for m in msgs if m.get("data_id")
                            }
                            logger.debug(
                                "MESSENGER/WhatsApp",
                                f"Baseline watermark initialized for group '{gtitle}' ({len(_state['seen_ids'][gkey])} msgs).",
                            )
                            continue

                        seen_set: set[str] = _state["seen_ids"][gkey]
                        for m in msgs:
                            did = str(m.get("data_id") or "")
                            if not did or did in seen_set:
                                continue
                            seen_set.add(did)

                            ok_trig, clean_txt, target_persona = _evaluate_group_trigger(grp, m)
                            if not ok_trig:
                                continue

                            sender = str(m.get("sender") or "Member").strip()
                            quoted = str(m.get("quoted_text") or "").strip()
                            envelope = f"[{sender}]: {clean_txt}"
                            if quoted:
                                envelope = f'> [Quoted: "{quoted}"]\n{envelope}'

                            logger.info(
                                "MESSENGER/WhatsApp",
                                f"[Group: {gtitle}] From {sender} -> persona='{target_persona or 'active'}': {clean_txt}",
                            )
                            threading.Thread(
                                target=inbound_callback,
                                args=("whatsapp", f"group:{gtitle}", envelope, target_persona, False),
                                daemon=True,
                            ).start()
            except Exception as poll_exc:
                logger.debug("MESSENGER/WhatsApp", f"Group poll warning: {poll_exc}")

            stop_ev.wait(interval)

    th = threading.Thread(target=_worker, name="hecos-wa-group-listener", daemon=True)
    _state["stop_event"] = stop_ev
    _state["thread"] = th
    th.start()


def stop_whatsapp_group_listener() -> None:
    """Stops any running WhatsApp group background listener thread."""
    stop_ev = _state.get("stop_event")
    th = _state.get("thread")
    if stop_ev is not None:
        stop_ev.set()
    if th is not None and th.is_alive() and th is not threading.current_thread():
        th.join(timeout=1.5)
    _state["stop_event"] = None
    _state["thread"] = None
