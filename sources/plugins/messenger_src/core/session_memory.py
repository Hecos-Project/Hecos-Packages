"""
Short-lived in-memory follow-up context tracker AND turn-aware anti-burst circuit breaker
for Hecos Messenger (v2.2).
  1. Remembers the last verified outbound `(platform, recipient, contact_name)` for a
     configurable window (default: 15 minutes) so follow-ups stay on the same channel.
  2. Prevents multi-step agent loops from re-sending the same text message 2x/3x across
     long turns (e.g. while working on a second step like `send_photo`) via per-turn_id
     completion tracking + a 180-second exact-duplicate guard.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Optional


FOLLOWUP_ALIASES = frozenset({"", "last", "same", "previous", "prev", "ultimo", "stesso"})


@dataclass(frozen=True)
class LastVerifiedSend:
    platform: str
    recipient: str
    contact_name: Optional[str] = None
    raw_query: Optional[str] = None
    bot_name: Optional[str] = None
    timestamp: float = 0.0


@dataclass(frozen=True)
class OutboundAttempt:
    platform: str
    norm_recipient: str
    norm_text: str
    kind: str  # "text" | "media"
    turn_id: str
    ok: bool
    timestamp: float


_lock = threading.Lock()
_last_send: Optional[LastVerifiedSend] = None
_recent_attempts: list[OutboundAttempt] = []


def _get_current_turn_id() -> str:
    try:
        from hecos.core.agent.trace_session import get_active_session
        sess = get_active_session()
        if sess and getattr(sess, "turn_id", None):
            return str(sess.turn_id)
    except Exception:
        pass
    return ""


def _normalize_recipient_key(platform: str, recipient: str) -> str:
    plat = (platform or "").strip().lower()
    rec = (recipient or "").strip()
    if plat == "whatsapp":
        if rec.lower().startswith("group:"):
            return re.sub(r"\s+", " ", rec.lower()).strip()
        digits = re.sub(r"\D", "", rec)
        return digits[-9:] if len(digits) >= 9 else digits
    return rec.lower()


def _normalize_text_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def check_burst_guard(
    platform: str,
    recipient: str,
    text: str,
    kind: str = "text",
    duplicate_window_sec: float = 180.0,
    failure_cooldown_sec: float = 18.0,
    max_sends_in_burst: int = 2,
    burst_window_sec: float = 25.0,
) -> Optional[str]:
    """
    Returns an immediate tool output string if a turn-duplicate, 3-minute exact duplicate,
    or post-dispatch-failure retry loop is detected, or `None` if safe to proceed.
    """
    now = time.time()
    plat = (platform or "").strip().lower()
    rec_key = _normalize_recipient_key(plat, recipient)
    txt_key = _normalize_text_key(text)
    cur_turn = _get_current_turn_id()
    if not plat or not rec_key:
        return None

    with _lock:
        _recent_attempts[:] = [a for a in _recent_attempts if (now - a.timestamp) <= 240.0]
        same_target = [a for a in _recent_attempts if a.platform == plat and a.norm_recipient == rec_key]

    if not same_target:
        return None

    # 1. Per-turn guard: if a text (or identical media) was ALREADY delivered in this exact agentic turn,
    # prevent re-sending it in later iterations of the same turn (fixes 3x text sends during multi-tool turns!)
    if cur_turn:
        for att in reversed(same_target):
            if att.ok and att.turn_id == cur_turn and att.kind == kind:
                if kind == "text" or att.norm_text == txt_key:
                    return (
                        f"✅ Already sent in this turn: the {plat} {kind} to this recipient was already delivered. "
                        "Do NOT call send_message again — complete only any remaining unsent media step or formulate your final response."
                    )

    # 2. 3-minute exact duplicate guard across turns
    for att in reversed(same_target):
        age = now - att.timestamp
        if att.ok and att.kind == kind and age <= duplicate_window_sec and txt_key and att.norm_text == txt_key:
            return (
                f"✅ Duplicate guard: this exact {plat} {kind} was already sent {age:.0f}s ago. "
                "Do NOT invoke MESSENGER again — confirm delivery to the user now."
            )

    # 3. Post-provider-failure circuit breaker (only recorded when a real provider dispatch failed)
    last_att = same_target[-1]
    if not last_att.ok and last_att.kind == kind and (now - last_att.timestamp) <= failure_cooldown_sec:
        return (
            f"⛔ Safety Circuit Breaker: the previous {plat} {kind} dispatch failed {now - last_att.timestamp:.1f}s ago. "
            "Automatic retries are blocked to prevent sending duplicate messages. "
            "STOP calling MESSENGER or EXECUTOR tools immediately and report the status to the user."
        )

    # 4. Hard burst cap per kind
    recent_sent_count = sum(1 for a in same_target if a.kind == kind and (now - a.timestamp) <= burst_window_sec)
    if recent_sent_count >= max_sends_in_burst:
        return (
            f"⛔ Rate limit: {recent_sent_count} {kind} dispatches were already sent to this recipient "
            f"in the last {int(burst_window_sec)}s. STOP calling MESSENGER tools and reply to the user."
        )

    return None


def record_outbound_attempt(
    platform: str,
    recipient: str,
    text: str,
    ok: bool,
    kind: str = "text",
) -> None:
    """Records a real provider dispatch attempt for turn-dedup & anti-burst protection."""
    plat = (platform or "").strip().lower()
    rec_key = _normalize_recipient_key(plat, recipient)
    if not plat or not rec_key:
        return
    cur_turn = _get_current_turn_id()
    with _lock:
        _recent_attempts.append(
            OutboundAttempt(
                platform=plat,
                norm_recipient=rec_key,
                norm_text=_normalize_text_key(text),
                kind=kind,
                turn_id=cur_turn,
                ok=bool(ok),
                timestamp=time.time(),
            )
        )


def has_outbound_since(
    since_ts: float,
    platform: str,
    chat_id: str = "",
    turn_id: str = "",
) -> bool:
    """
    Returns True if a successful outbound message/media dispatch already occurred on `platform`
    to `chat_id` (or within `turn_id` to `chat_id`) at or after `since_ts`.
    Used by InboundRouter to avoid sending a duplicate bubble when the LLM explicitly called
    a MESSENGER tool targeting the same chat during an inbound conversation turn.
    """
    plat = (platform or "").strip().lower()
    target_key = _normalize_recipient_key(plat, chat_id) if chat_id else ""
    if not plat:
        return False

    with _lock:
        candidates = [
            a for a in _recent_attempts
            if a.ok and a.platform == plat and a.timestamp >= (since_ts - 0.05)
        ]

    for att in candidates:
        if turn_id and att.turn_id and att.turn_id != turn_id:
            continue
        if not target_key or att.norm_recipient == target_key:
            return True
    return False


def record_verified_send(
    platform: str,
    recipient: str,
    contact_name: Optional[str] = None,
    raw_query: Optional[str] = None,
    bot_name: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> None:
    """Records a verified outbound message as the active follow-up target."""
    global _last_send
    clean_plat = (platform or "").strip().lower()
    clean_rec = (recipient or "").strip()
    if not clean_plat or not clean_rec:
        return

    clean_raw = (raw_query or "").strip()
    if clean_raw.lower() in FOLLOWUP_ALIASES:
        clean_raw = ""

    with _lock:
        prev_raw = _last_send.raw_query if (_last_send and not clean_raw) else None
        _last_send = LastVerifiedSend(
            platform=clean_plat,
            recipient=clean_rec,
            contact_name=(contact_name or "").strip() or None,
            raw_query=clean_raw or prev_raw,
            bot_name=(bot_name or "").strip() or None,
            timestamp=float(timestamp if timestamp is not None else time.time()),
        )


def get_recent_context(ttl_minutes: int = 15) -> Optional[LastVerifiedSend]:
    """Returns the last verified send if within `ttl_minutes`, otherwise None."""
    if ttl_minutes <= 0:
        return None
    with _lock:
        current = _last_send
    if current is None:
        return None
    if (time.time() - current.timestamp) > (ttl_minutes * 60.0):
        return None
    return current


def clear_recent_context() -> None:
    """Clears stored follow-up context and burst history (used by tests or resets)."""
    global _last_send
    with _lock:
        _last_send = None
        _recent_attempts.clear()


def is_followup_token(raw_to: str) -> bool:
    """Returns True when `to` is omitted or uses an explicit follow-up placeholder like 'last'."""
    return (raw_to or "").strip().lower() in FOLLOWUP_ALIASES


def matches_recent_contact(
    candidate: str,
    contact_display_name: Optional[str],
    recent: LastVerifiedSend,
) -> bool:
    """Checks whether `candidate` or resolved `contact_display_name` refers to `recent`."""
    cand_norm = (candidate or "").strip().lower()
    if cand_norm in FOLLOWUP_ALIASES:
        return True

    if recent.raw_query and cand_norm == recent.raw_query.strip().lower():
        return True

    if contact_display_name and recent.contact_name:
        if contact_display_name.strip().lower() == recent.contact_name.strip().lower():
            return True

    if recent.contact_name and cand_norm == recent.contact_name.strip().lower():
        return True

    cand_digits = re.sub(r"\D", "", candidate or "")
    rec_digits = re.sub(r"\D", "", recent.recipient or "")
    if len(cand_digits) >= 8 and rec_digits.endswith(cand_digits[-8:]):
        return True

    return cand_norm == (recent.recipient or "").strip().lower()
