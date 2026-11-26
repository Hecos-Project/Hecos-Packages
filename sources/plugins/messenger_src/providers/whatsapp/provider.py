"""
WhatsApp Provider implementation for Hecos Messenger (v2.4).
Delegates browser interaction to cdp_worker.py via serialized JSON file IPC:
  - Direct contact & Group chat text/photo/document delivery
  - Optional *[Persona]* group signature formatting
  - 1-Click live WhatsApp Group scanning (`scan_groups`)
  - Safe serialized background WhatsApp Group inbound polling (`start_listener` / `stop_listener`)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from typing import Any, Optional

from hecos.core.logging import logger
from ...core.base_provider import BaseMessengerProvider, InboundCallback, ProviderHealth, SendResult
from .config import WhatsAppConfig, WhatsAppGroupConfig
from .dom_driver import normalize_whatsapp_phone
from .listener import (
    record_hecos_whatsapp_outbound,
    start_whatsapp_group_listener,
    stop_whatsapp_group_listener,
)


if not hasattr(sys, "_hecos_wa_cdp_lock"):
    sys._hecos_wa_cdp_lock = threading.RLock()  # type: ignore[attr-defined]
_cdp_lock: threading.RLock = sys._hecos_wa_cdp_lock  # type: ignore[attr-defined]

_ALREADY_SIGNED_RE = re.compile(r"^\s*\*?\[[^\[\]\r\n]{1,36}\]\*?")


def _resolve_persona_signature_label(explicit_persona: Optional[str] = None) -> str:
    """
    Resolves a clean human display label for `[Persona]` group signatures
    (e.g. 'Urania_9800' -> 'Urania', 'Hecos_System_Soul' -> 'Hecos').
    """
    raw = (explicit_persona or "").strip()
    if not raw:
        try:
            mgr = getattr(sys, "hecos_config_manager", None)
            if mgr and isinstance(getattr(mgr, "config", None), dict):
                raw = str((mgr.config.get("ai") or {}).get("active_personality") or "")
            if not raw:
                from hecos.core.global_presets import get_active_soul
                soul = get_active_soul("global")
                if soul and getattr(soul.persona, "soul_file", None):
                    raw = str(soul.persona.soul_file)
        except Exception:
            raw = ""

    low = raw.lower()
    if "urania" in low:
        return "Urania"
    if "hecos" in low or not raw:
        return "Hecos"

    cleaned = raw.replace(".yaml", "").split("_")[0].strip()
    return cleaned.capitalize() if cleaned else "Hecos"


def _extract_group_target(recipient: str) -> Optional[str]:
    rec = (recipient or "").strip()
    if rec.lower().startswith("group:"):
        title = rec.split(":", 1)[1].strip()
        return title if title else None
    return None


def _find_group_config(cfg: WhatsAppConfig, group_title: str) -> Optional[WhatsAppGroupConfig]:
    norm_t = re.sub(r"\s+", " ", (group_title or "").replace("\u00a0", " ")).strip().lower()
    for g in getattr(cfg, "groups", None) or []:
        gt = re.sub(r"\s+", " ", (g.group_title or g.name or "").replace("\u00a0", " ")).strip().lower()
        gn = re.sub(r"\s+", " ", (g.name or "").replace("\u00a0", " ")).strip().lower()
        if norm_t and norm_t in (gt, gn):
            return g
    return None


def _resolve_effective_group_signature(
    cfg: WhatsAppConfig,
    group_title: str,
    persona_hint: Optional[str] = None,
) -> Optional[str]:
    """
    Returns the formatted signature badge (e.g. `*[Urania]*` or `*[Pippo]*`) to prepend
    for `group_title`, or `None` when the signature is disabled globally or for this group.
    """
    gcfg = _find_group_config(cfg, group_title)
    g_mode = str(getattr(gcfg, "signature_mode", "global") or "global").lower() if gcfg is not None else "global"

    # Respect legacy `sign_persona=False` if signature_mode was never explicitly changed from 'global'
    if gcfg is not None and g_mode == "global" and getattr(gcfg, "sign_persona", True) is False:
        g_mode = "off"

    if g_mode == "off":
        return None

    if g_mode == "custom":
        raw_custom = (getattr(gcfg, "custom_signature", "") or "").strip()
        label = raw_custom or (getattr(cfg, "group_signature_text", "") or "").strip() or _resolve_persona_signature_label(persona_hint)
    elif g_mode == "auto":
        label = _resolve_persona_signature_label(persona_hint)
    else:
        # 'global' -> inherit from WhatsAppConfig
        if not getattr(cfg, "group_signature_enabled", True):
            return None
        global_mode = str(getattr(cfg, "group_signature_mode", "auto") or "auto").lower()
        if global_mode == "custom":
            raw_global = (getattr(cfg, "group_signature_text", "") or "").strip()
            label = raw_global or _resolve_persona_signature_label(persona_hint)
        else:
            label = _resolve_persona_signature_label(persona_hint)

    clean_label = label.strip()
    if not clean_label:
        return None
    # Strip outer *[...]* or [...] if the user typed brackets themselves so we format consistently
    clean_label = re.sub(r"^\*?\[(.*)\]\*?$", r"\1", clean_label).strip()
    return f"*[{clean_label}]*" if clean_label else None


def _maybe_sign_group_text(
    cfg: WhatsAppConfig,
    group_title: str,
    text: str,
    persona_hint: Optional[str] = None,
) -> str:
    if not text or not text.strip():
        return text
    badge = _resolve_effective_group_signature(cfg, group_title, persona_hint=persona_hint)
    if not badge or _ALREADY_SIGNED_RE.match(text):
        return text
    return f"{badge} {text}"


class WhatsAppProvider(BaseMessengerProvider):
    name = "whatsapp"
    display_name = "WhatsApp"
    icon = "💬"
    supports_inbound = True
    supports_media = True

    def _describe_mode(self, cfg: WhatsAppConfig) -> str:
        base_port = int(getattr(cfg, "cdp_port", 9222) or 9222)
        if getattr(cfg, "session_mode", "cdp") == "persistent_profile":
            bg = "headless background" if getattr(cfg, "persistent_headless", False) else "visible window"
            return f"Dedicated Hecos Session (port {base_port + 1}, {bg})"
        return f"Shared User Browser (CDP port {base_port})"

    def _invoke_worker(
        self,
        cfg: WhatsAppConfig,
        payload: dict[str, Any],
        non_blocking: bool = False,
    ) -> dict[str, Any]:
        import tempfile

        acquired = _cdp_lock.acquire(blocking=not non_blocking)
        if not acquired:
            return {"ok": False, "busy": True, "error": "WhatsApp session is currently busy with an outbound action."}

        try:
            worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cdp_worker.py")
            if not os.path.exists(worker_script):
                return {"ok": False, "error": "WhatsApp cdp_worker.py script is missing."}

            full_payload = {
                "session_mode": getattr(cfg, "session_mode", "cdp"),
                "cdp_port": int(getattr(cfg, "cdp_port", 9222) or 9222),
                "auto_open_tab": bool(getattr(cfg, "auto_open_tab", True)),
                "persistent_headless": bool(getattr(cfg, "persistent_headless", False)),
                "cdp_timeout": int(getattr(cfg, "cdp_timeout", 30) or 30),
                **payload,
            }
            worker_timeout = int(getattr(cfg, "worker_timeout", 60) or 60)

            in_fd, in_path = tempfile.mkstemp(prefix="hecos_wa_in_", suffix=".json")
            out_fd, out_path = tempfile.mkstemp(prefix="hecos_wa_out_", suffix=".json")
            os.close(in_fd)
            os.close(out_fd)

            try:
                with open(in_path, "w", encoding="utf-8") as fh:
                    json.dump(full_payload, fh, ensure_ascii=False)

                proc = subprocess.Popen(
                    [sys.executable, worker_script, in_path, out_path],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
                try:
                    proc.wait(timeout=worker_timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    logger.warning("MESSENGER/WhatsApp", f"Worker timed out after {worker_timeout}s.")
                    return {
                        "ok": False,
                        "error": (
                            f"WhatsApp operation timed out after {worker_timeout}s. "
                            "Check that WhatsApp Web is responsive or increase Total Send Timeout in Messenger settings."
                        ),
                    }

                if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                    with open(out_path, "r", encoding="utf-8") as fh:
                        return json.load(fh)

                return {"ok": False, "error": f"WhatsApp worker exited (code {proc.returncode}) without output."}
            except Exception as exc:
                logger.warning("MESSENGER/WhatsApp", f"Worker execution error: {exc}")
                return {"ok": False, "error": f"Unexpected worker error: {exc}"}
            finally:
                for tmp in (in_path, out_path):
                    try:
                        if os.path.exists(tmp):
                            os.remove(tmp)
                    except Exception:
                        pass
        finally:
            _cdp_lock.release()

    def send_text(
        self,
        provider_cfg: WhatsAppConfig,
        recipient: str,
        text: str,
        **options: Any,
    ) -> SendResult:
        if not provider_cfg or not provider_cfg.enabled:
            return SendResult(
                ok=False,
                platform=self.name,
                recipient=recipient,
                message="WhatsApp provider is disabled. Enable it in Central Hub → Messenger.",
            )

        group_title = _extract_group_target(recipient)
        e164, digits = "", ""
        persona_hint = options.get("bot_name")
        outbound_text = text

        if group_title:
            outbound_text = _maybe_sign_group_text(provider_cfg, group_title, text, persona_hint=persona_hint)
            target_label = f"Group '{group_title}'"
            canonical_rec = f"group:{group_title}"
            record_hecos_whatsapp_outbound(text=outbound_text)
        else:
            try:
                e164, digits = normalize_whatsapp_phone(
                    recipient,
                    default_country_code=getattr(provider_cfg, "phone_country_code", "+39") or "+39",
                )
            except ValueError as exc:
                return SendResult(ok=False, platform=self.name, recipient=recipient, message=str(exc))
            contact_name = options.get("contact_name")
            target_label = f"{contact_name} ({e164})" if contact_name else e164
            canonical_rec = e164

        mode_desc = self._describe_mode(provider_cfg)
        logger.info("MESSENGER/WhatsApp", f"Sending to {target_label} via [{mode_desc}]...")

        res = self._invoke_worker(
            provider_cfg,
            {
                "action": "send_text",
                "e164": e164,
                "digits": digits,
                "group_title": group_title,
                "text": outbound_text,
                "contact_name": options.get("contact_name"),
                "single_block": bool(getattr(provider_cfg, "send_as_single_block", True)),
            },
        )
        method_used = res.get("method_used") or mode_desc

        if not res.get("ok"):
            err = res.get("error") or "Unknown WhatsApp send failure."
            logger.warning("MESSENGER/WhatsApp", f"Send failed for {target_label}: {err}")
            return SendResult(
                ok=False,
                platform=self.name,
                recipient=canonical_rec,
                message=(
                    f"WhatsApp send failed [{method_used}]: {err} "
                    "(Do NOT retry automatically and do NOT call EXECUTOR tools — report this status directly to the user.)"
                ),
                method_used=method_used,
            )

        if group_title:
            new_ids = list(res.get("new_ids") or [])
            if res.get("msg_id"):
                new_ids.append(str(res["msg_id"]))
            record_hecos_whatsapp_outbound(text=outbound_text, msg_ids=new_ids)

        verified = bool(res.get("verified", False))
        logger.info("MESSENGER/WhatsApp", f"Message sent to {target_label} (verified={verified}).")
        status_note = "delivery confirmed" if verified else "dispatched to chat, awaiting sync checkmark"
        return SendResult(
            ok=True,
            platform=self.name,
            recipient=canonical_rec,
            verified=verified,
            warning=not verified,
            method_used=method_used,
            message=f"WhatsApp message sent to {target_label} via {method_used} ({status_note}).",
        )

    def send_media(
        self,
        provider_cfg: WhatsAppConfig,
        recipient: str,
        file_paths: list[str],
        caption: str = "",
        **options: Any,
    ) -> SendResult:
        if not provider_cfg or not provider_cfg.enabled:
            return SendResult(
                ok=False,
                platform=self.name,
                recipient=recipient,
                message="WhatsApp provider is disabled. Enable it in Central Hub → Messenger.",
            )

        group_title = _extract_group_target(recipient)
        e164, digits = "", ""
        persona_hint = options.get("bot_name")
        outbound_caption = caption

        if group_title:
            if caption and caption.strip():
                outbound_caption = _maybe_sign_group_text(provider_cfg, group_title, caption, persona_hint=persona_hint)
            else:
                badge = _resolve_effective_group_signature(provider_cfg, group_title, persona_hint=persona_hint)
                if badge:
                    outbound_caption = badge
            target_label = f"Group '{group_title}'"
            canonical_rec = f"group:{group_title}"
            record_hecos_whatsapp_outbound(text=outbound_caption)
        else:
            try:
                e164, digits = normalize_whatsapp_phone(
                    recipient,
                    default_country_code=getattr(provider_cfg, "phone_country_code", "+39") or "+39",
                )
            except ValueError as exc:
                return SendResult(ok=False, platform=self.name, recipient=recipient, message=str(exc))
            contact_name = options.get("contact_name")
            target_label = f"{contact_name} ({e164})" if contact_name else e164
            canonical_rec = e164

        mode_desc = self._describe_mode(provider_cfg)
        res = self._invoke_worker(
            provider_cfg,
            {
                "action": "send_media",
                "e164": e164,
                "digits": digits,
                "group_title": group_title,
                "file_paths": file_paths,
                "caption": outbound_caption,
                "contact_name": options.get("contact_name"),
            },
        )
        method_used = res.get("method_used") or mode_desc
        if not res.get("ok"):
            return SendResult(
                ok=False,
                platform=self.name,
                recipient=canonical_rec,
                message=f"WhatsApp media send failed [{method_used}]: {res.get('error', 'unknown error')}",
                method_used=method_used,
            )

        if group_title:
            new_ids = list(res.get("new_ids") or [])
            if res.get("msg_id"):
                new_ids.append(str(res["msg_id"]))
            record_hecos_whatsapp_outbound(text=outbound_caption, msg_ids=new_ids)

        verified = bool(res.get("verified", False))
        return SendResult(
            ok=True,
            platform=self.name,
            recipient=canonical_rec,
            verified=verified,
            warning=not verified,
            method_used=method_used,
            message=f"WhatsApp attachment(s) sent to {target_label} via {method_used}.",
        )

    def open_session(self, provider_cfg: WhatsAppConfig) -> dict[str, Any]:
        """Opens or brings to front the configured WhatsApp Web session for QR login / inspection."""
        return self._invoke_worker(provider_cfg, {"action": "open_session"})

    def scan_groups(self, provider_cfg: WhatsAppConfig) -> dict[str, Any]:
        """Scans visible WhatsApp groups from the `#group-filter` tab for 1-click WebUI registration."""
        if not provider_cfg or not provider_cfg.enabled:
            return {"ok": False, "error": "Enable WhatsApp Provider first.", "groups": []}
        res = self._invoke_worker(provider_cfg, {"action": "scan_groups"})
        if res.get("ok") and res.get("groups"):
            import time as _t
            sys._hecos_wa_group_scan_cache = {"ts": _t.time(), "data": res}  # type: ignore[attr-defined]
        return res

    def scan_groups_cached(self, provider_cfg: WhatsAppConfig, ttl_sec: float = 30.0) -> dict[str, Any]:
        """Returns cached WhatsApp group scan if fresh (`ttl_sec`), otherwise performs a live scan."""
        import time as _t
        cache = getattr(sys, "_hecos_wa_group_scan_cache", None)
        if isinstance(cache, dict) and (_t.time() - float(cache.get("ts") or 0.0)) <= ttl_sec:
            return cache.get("data") or {"ok": False, "groups": []}
        return self.scan_groups(provider_cfg)

    def start_listener(
        self,
        provider_cfg: WhatsAppConfig,
        inbound_callback: Optional[InboundCallback] = None,
    ) -> None:
        def _poll_fn(group_titles: list[str]) -> dict[str, Any]:
            return self._invoke_worker(
                provider_cfg,
                {"action": "poll_groups", "group_titles": group_titles},
                non_blocking=True,
            )

        start_whatsapp_group_listener(provider_cfg, poll_fn=_poll_fn, inbound_callback=inbound_callback)

    def stop_listener(self) -> None:
        stop_whatsapp_group_listener()

    def check_health(self, provider_cfg: WhatsAppConfig) -> ProviderHealth:
        mode_desc = self._describe_mode(provider_cfg)
        if not provider_cfg or not provider_cfg.enabled:
            return ProviderHealth(
                platform=self.name,
                enabled=False,
                state="DISABLED",
                summary="Disabled",
                method_used=mode_desc,
            )

        try:
            import playwright  # noqa: F401
        except ImportError:
            return ProviderHealth(
                platform=self.name,
                enabled=True,
                state="MISSING_DEP",
                summary="Playwright is not installed in Python environment.",
                method_used=mode_desc,
            )

        res = self._invoke_worker(provider_cfg, {"action": "status"}, non_blocking=True)
        if res.get("busy"):
            return ProviderHealth(
                platform=self.name,
                enabled=True,
                state="ONLINE",
                summary=f"Active (currently dispatching/polling) via {mode_desc}",
                method_used=mode_desc,
            )

        if not res.get("ok"):
            return ProviderHealth(
                platform=self.name,
                enabled=True,
                state=res.get("state", "OFFLINE"),
                summary=res.get("error") or "Browser session unreachable.",
                method_used=res.get("method_used") or mode_desc,
                details=res,
            )

        return ProviderHealth(
            platform=self.name,
            enabled=True,
            state=res.get("state", "ONLINE"),
            summary=res.get("summary") or f"Ready via {mode_desc}",
            method_used=res.get("method_used") or mode_desc,
            details=res,
        )

    def describe_accounts(self, provider_cfg: WhatsAppConfig) -> list[str]:
        enabled = bool(provider_cfg and provider_cfg.enabled)
        mode_desc = self._describe_mode(provider_cfg) if provider_cfg else "CDP"
        status_icon = "✅ Enabled" if enabled else "⛔ Disabled"
        lines = [f"💬 **WhatsApp**: {status_icon}"]
        if enabled:
            lines.append(f"  └─ Active Delivery Method: **{mode_desc}**")
            groups = [g for g in (getattr(provider_cfg, "groups", None) or []) if g.enabled and (g.name or g.group_title)]
            if groups:
                g_desc = ", ".join(
                    f"'{g.name or g.group_title}' (title='{g.group_title or g.name}', inbound={g.inbound_mode}, sign={'on' if g.sign_persona else 'off'})"
                    for g in groups
                )
                lines.append(f"  └─ Configured WhatsApp Groups: {g_desc}")
            else:
                scan_res = self.scan_groups_cached(provider_cfg, ttl_sec=60.0)
                live_titles = [g.get("title") for g in (scan_res.get("groups") or [])[:8] if g.get("title")]
                if live_titles:
                    lines.append(f"  └─ Visible WhatsApp Web Groups: {', '.join(live_titles)}")
        return lines
