"""
Platform-agnostic Inbound Message Router for Hecos Messenger (v2.3.1).
Handles pre-callbacks, built-in utility commands (/id), Remote Access Pro
commands (for admin accounts), Persona/Soul-aware Hecos AI conversation routing,
and automatic delivery of generated [[IMG:...]] and local media files in AI replies.
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
import time
import urllib.request
import uuid
from typing import Any, Callable, Optional

from hecos.core.logging import logger
from .media_resolver import resolve_photo_path
from .registry import ProviderRegistry, registry as default_registry
from .session_memory import has_outbound_since


_LOCAL_FILE_RE = re.compile(r'([A-Za-z]:[/\\][^\s"\'<>]+?\.[a-zA-Z0-9]{2,5})')
_IMG_TAG_RE = re.compile(r"\[\[IMG:([^\]]+)\]\]", re.IGNORECASE)
_UI_TOKEN_STRIP_RE = re.compile(r"\[\[(?:IMG|HSEARCH|HMEDIA):[^\]]+\]\]", re.IGNORECASE)
_IGEN_META_STRIP_RE = re.compile(
    r"(?m)^\s*>\s*(?:🖥️\s*)?\*\*\[(?:Image Gen Config|SwarmUI Auto-Start)\]\*\*[^\r\n]*(?:\r?\n)?"
)
_SYNC_ACK_PREFIX_RE = re.compile(
    r"^\s*['\"`]*SYNCHRONIZED['\"`]*[\s,.:;!\-–—]*",
    re.IGNORECASE,
)

_ollama_probe_cache: dict[str, Any] = {"ts": 0.0, "installed": [], "loaded": []}


class _InboundMergedConfigManager:
    """Lightweight read-only ConfigManager wrapper holding a Soul-merged config dict."""

    def __init__(self, base_mgr: Any, merged_dict: dict[str, Any]) -> None:
        self._base = base_mgr
        self.config = merged_dict

    def save_config(self) -> None:
        pass

    def __getattr__(self, name: str) -> Any:
        if self._base is not None:
            return getattr(self._base, name)
        raise AttributeError(name)


def _norm_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _probe_ollama_models(ollama_url: str = "http://127.0.0.1:11434") -> tuple[list[str], list[str]]:
    """Returns `(installed_models, vram_loaded_models)` with a 20s in-memory cache."""
    now = time.time()
    if (now - float(_ollama_probe_cache.get("ts") or 0.0)) <= 20.0 and _ollama_probe_cache.get("installed"):
        return list(_ollama_probe_cache["installed"]), list(_ollama_probe_cache["loaded"])

    base = (ollama_url or "http://127.0.0.1:11434").rstrip("/")
    installed: list[str] = []
    loaded: list[str] = []
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            installed = [str(m.get("name")) for m in (data.get("models") or []) if m.get("name")]
    except Exception:
        pass

    try:
        with urllib.request.urlopen(f"{base}/api/ps", timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            loaded = [str(m.get("name")) for m in (data.get("models") or []) if m.get("name")]
    except Exception:
        pass

    if installed or loaded:
        _ollama_probe_cache["ts"] = now
        _ollama_probe_cache["installed"] = installed
        _ollama_probe_cache["loaded"] = loaded

    return installed, loaded


def _match_soul_for_account(account_name: str, souls: list[Any], installed_models: list[str]) -> Any:
    """
    Finds the best matching SoulProfile for a bot `account_name` (e.g. 'Urania' -> 'urania_9800_gp',
    'hecos' -> 'hecos_default'). Skips pure coding/planner presets unless explicitly matched by ID.
    """
    acc_norm = _norm_token(account_name)
    if not acc_norm or not souls:
        return None

    best_soul = None
    best_score = -1

    for soul in souls:
        sid = str(getattr(soul.meta, "id", "") or "")
        sname = str(getattr(soul.meta, "name", "") or "")
        sfile = str(getattr(soul.persona, "soul_file", "") or "")
        mname = str(getattr(soul.model, "model_name", "") or "")

        sid_n = _norm_token(sid)
        sname_n = _norm_token(sname)
        sfile_n = _norm_token(sfile)

        # Avoid selecting specialized coder/planner/storyboard presets for general chat bots
        if any(tag in sid.lower() for tag in ("coder", "planner", "storyboard")) and sid_n != acc_norm:
            continue

        score = -1
        if sid_n == acc_norm or sname_n == acc_norm or sfile_n == acc_norm:
            score = 100
        elif sid.lower() == f"{acc_norm}_9800_gp" or sid.lower() == f"{acc_norm}_default":
            score = 98
        elif sfile_n.startswith(acc_norm) or sid_n.startswith(acc_norm) or sname_n.startswith(acc_norm):
            score = 85
        elif len(acc_norm) >= 4 and (acc_norm in sfile_n or acc_norm in sid_n or acc_norm in sname_n):
            score = 70

        if score < 0:
            continue

        # Prefer presets with a valid installed model configured
        if mname and (not installed_models or mname in installed_models):
            score += 10
        if sid.lower().endswith("_gp"):
            score += 3

        if score > best_score:
            best_score = score
            best_soul = soul

    return best_soul


def _ensure_valid_backend_model(
    merged: dict[str, Any],
    preferred_fallback_model: str = "",
    base_cfg: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Guarantees that `merged['backend'][btype]['model']` is populated and valid so
    inbound messages NEVER fail with 'ERROR: Model configuration missing.' or stale tags.
    """
    backend = merged.setdefault("backend", {})
    btype = str(backend.get("type") or "ollama").lower()
    eff_btype = str(backend.get("active_model_source") or "ollama").lower() if btype == "hybrid" else btype

    b_dict = backend.setdefault(eff_btype, {})
    if not isinstance(b_dict, dict):
        b_dict = {}
        backend[eff_btype] = b_dict

    cur_model = str(b_dict.get("model") or "").strip()
    if cur_model == "N/D":
        cur_model = ""

    if eff_btype == "ollama":
        ollama_url = str(b_dict.get("url") or "http://127.0.0.1:11434")
        installed, loaded = _probe_ollama_models(ollama_url)

        def _is_usable(m: str) -> bool:
            if not m or m == "N/D":
                return False
            if installed and m not in installed:
                return False
            return True

        if not _is_usable(cur_model):
            base_ollama_model = str(
                (((base_cfg or {}).get("backend") or {}).get("ollama") or {}).get("model") or ""
            ).strip()
            candidates = [
                preferred_fallback_model,
                loaded[0] if loaded else "",
                base_ollama_model,
                next((m for m in installed if "embed" not in m.lower()), ""),
            ]
            chosen = next((c for c in candidates if _is_usable(c)), "") or preferred_fallback_model or base_ollama_model
            if chosen:
                logger.info(
                    "MESSENGER",
                    f"Inbound model fallback resolved '{chosen}' (previous='{cur_model or 'N/D'}').",
                )
                b_dict["model"] = chosen
    elif not cur_model and preferred_fallback_model:
        b_dict["model"] = preferred_fallback_model

    return merged


def _build_inbound_runtime_context(
    platform: str,
    chat_id: str,
    account_name: Optional[str] = None,
) -> tuple[dict[str, Any], Any, str]:
    """
    Resolves `(turn_cfg, config_manager, session_id)` for an inbound Messenger message,
    automatically merging the active Global Preset / Soul and matching `account_name`
    (e.g. 'Urania' vs 'hecos') to its corresponding Soul personality.
    """
    safe_plat = re.sub(r"[^a-z0-9_]+", "_", (platform or "chat").lower()).strip("_") or "chat"
    safe_acc = re.sub(r"[^a-z0-9_]+", "_", (account_name or "default").lower()).strip("_") or "default"
    safe_cid = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(chat_id or "0")).strip("_") or "0"
    session_id = f"messenger_{safe_plat}_{safe_acc}_{safe_cid}"

    base_mgr = getattr(sys, "hecos_config_manager", None)
    base_cfg: Optional[dict[str, Any]] = None
    if base_mgr is not None and isinstance(getattr(base_mgr, "config", None), dict) and base_mgr.config:
        base_cfg = base_mgr.config
    else:
        from hecos.core.processing import processore
        if isinstance(processore.current_config, dict) and processore.current_config.get("backend"):
            base_cfg = processore.current_config
        else:
            from hecos.core.llm import brain
            base_cfg = brain.load_config() or {}

    try:
        from hecos.config.session_config_manager import merge_session_config
        merged = merge_session_config(base_cfg, session_id=session_id)
    except Exception as merge_exc:
        logger.warning("MESSENGER", f"merge_session_config fallback triggered: {merge_exc}")
        merged = copy.deepcopy(base_cfg) if isinstance(base_cfg, dict) else {}

    # Preserve the active global preset's working model before applying bot-specific persona
    active_ollama_model = str((((merged.get("backend") or {}).get("ollama")) or {}).get("model") or "").strip()

    # Match Telegram/provider bot account (e.g. 'Urania' vs 'hecos') to the right Soul
    if account_name:
        acc_norm = _norm_token(account_name)
        cur_persona = str((merged.get("ai") or {}).get("active_personality") or "")
        if acc_norm and acc_norm not in _norm_token(cur_persona):
            try:
                from hecos.core.global_presets import list_souls, merge_soul_into_config
                ollama_url = str(
                    (((merged.get("backend") or {}).get("ollama")) or {}).get("url") or "http://127.0.0.1:11434"
                )
                installed_models, loaded_models = _probe_ollama_models(ollama_url)
                souls = list_souls()
                matched_soul = _match_soul_for_account(account_name, souls, installed_models)
                if matched_soul is not None:
                    merged = merge_soul_into_config(merged, matched_soul)
                    # Keep hot VRAM model when switching to auto-generated hecos_default so we avoid VRAM thrashing
                    if getattr(matched_soul.meta, "id", "") == "hecos_default" and (loaded_models or active_ollama_model):
                        hot_model = loaded_models[0] if loaded_models else active_ollama_model
                        if hot_model:
                            merged.setdefault("backend", {}).setdefault("ollama", {})["model"] = hot_model
                    logger.info(
                        "MESSENGER",
                        f"Inbound bot '{account_name}' matched to Soul '{matched_soul.meta.name}' "
                        f"(persona='{matched_soul.persona.soul_file}').",
                    )
                elif acc_norm == "hecos":
                    merged.setdefault("ai", {})["active_personality"] = "Hecos_System_Soul"
            except Exception as soul_exc:
                logger.warning("MESSENGER", f"Bot-to-Soul matching warning for '{account_name}': {soul_exc}")

    merged = _ensure_valid_backend_model(
        merged,
        preferred_fallback_model=active_ollama_model,
        base_cfg=base_cfg,
    )

    # Clean transient per-turn flags and ensure fast non-starving inference defaults
    for key in list(merged.keys()):
        if str(key).startswith("_turn_"):
            merged.pop(key, None)

    pctrl = merged.setdefault("payload_control", {})
    if isinstance(pctrl, dict):
        pctrl.setdefault("send_tools", True)
        pctrl.setdefault("send_personality", True)
        pctrl.setdefault("send_memory", True)
        b_cfg = merged.get("backend") or {}
        b_type = str(b_cfg.get("type") or "ollama").lower()
        if b_type == "hybrid":
            b_type = str(b_cfg.get("active_model_source") or "ollama").lower()
        if b_type == "ollama":
            o_cfg = b_cfg.get("ollama") or {}
            if pctrl.get("enable_thinking") is None:
                if o_cfg.get("enable_thinking") is not None:
                    pctrl["enable_thinking"] = bool(o_cfg.get("enable_thinking"))
                else:
                    try:
                        n_pred = int(o_cfg.get("num_predict") or 0)
                    except (TypeError, ValueError):
                        n_pred = 0
                    if 0 < n_pred <= 2048:
                        pctrl["enable_thinking"] = False

    wrapped_mgr = _InboundMergedConfigManager(base_mgr, merged)
    return merged, wrapped_mgr, session_id


def _extract_reply_text_and_media(raw_reply: str) -> tuple[str, list[str]]:
    """
    Extracts verified local media files (both `[[IMG:...]]` tags and raw file paths)
    and cleans UI-only metadata/tokens from the visible chat text.
    """
    if not raw_reply:
        return "", []

    media_files: list[str] = []

    # 1. Resolve [[IMG:...]] tags generated by IMAGE_GEN
    for img_match in _IMG_TAG_RE.finditer(raw_reply):
        resolved_img, err = resolve_photo_path(img_match.group(0))
        if resolved_img and not err and resolved_img not in media_files:
            media_files.append(resolved_img)

    # 2. Resolve explicit absolute local file paths (e.g. PDFs / screenshots)
    for path_match in _LOCAL_FILE_RE.findall(raw_reply):
        if os.path.isfile(path_match):
            norm_p = os.path.abspath(path_match)
            if norm_p not in media_files:
                media_files.append(norm_p)

    # 3. Clean UI-only badges, [[IMG:...]] tokens, local file paths, and protocol prefixes
    cleaned = _IGEN_META_STRIP_RE.sub("", raw_reply)
    cleaned = _UI_TOKEN_STRIP_RE.sub("", cleaned)
    if media_files:
        cleaned = _LOCAL_FILE_RE.sub("", cleaned)
    cleaned = _SYNC_ACK_PREFIX_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    return cleaned, media_files


class InboundRouter:
    """Routes incoming messages from any provider listener to Hecos."""

    def __init__(self, reg: ProviderRegistry = default_registry) -> None:
        self._reg = reg
        self._pre_callbacks: dict[str, Callable[[str], Optional[str]]] = {}

    def register_pre_callback(self, name: str, fn: Callable[[str], Optional[str]]) -> None:
        """Registers an interceptor; if fn(text) returns a non-None string, it is sent as reply."""
        self._pre_callbacks[name] = fn
        logger.info("MESSENGER", f"Inbound pre-callback '{name}' registered.")

    def _send_inbound_reply(
        self,
        platform: str,
        chat_id: str,
        text: str = "",
        file_paths: Optional[list[str]] = None,
        account_name: Optional[str] = None,
        root_cfg: Any = None,
    ) -> None:
        provider = self._reg.get(platform)
        if not provider:
            logger.warning("MESSENGER", f"Cannot send inbound reply: unknown provider '{platform}'.")
            return
        pcfg = provider.get_provider_config(root_cfg) if root_cfg else None
        if file_paths:
            provider.send_media(
                pcfg,
                chat_id,
                file_paths=file_paths,
                caption=text or "",
                bot_name=account_name,
                prefer_listener_loop=True,
            )
        elif text:
            provider.send_text(
                pcfg,
                chat_id,
                text,
                bot_name=account_name,
                prefer_listener_loop=True,
            )

    def handle_incoming(
        self,
        platform: str,
        chat_id: str,
        text: str,
        account_name: Optional[str] = None,
        is_admin: bool = False,
        root_cfg: Any = None,
    ) -> None:
        """Processes a single incoming message from a background listener."""
        if not text or not text.strip():
            return

        cleaned = text.strip()

        try:
            # 1. Registered Pre-Callbacks
            for cb_name, cb_fn in list(self._pre_callbacks.items()):
                try:
                    intercepted = cb_fn(cleaned)
                    if intercepted is not None:
                        logger.info("MESSENGER", f"Message intercepted by pre-callback '{cb_name}'.")
                        self._send_inbound_reply(
                            platform, chat_id, text=str(intercepted), account_name=account_name, root_cfg=root_cfg
                        )
                        return
                except Exception as cb_err:
                    logger.warning("MESSENGER", f"Pre-callback '{cb_name}' error: {cb_err}")

            # 2. Built-in Slash Commands (/id, /getid) & Remote Access Pro
            if cleaned.startswith("/"):
                cmd_lower = cleaned.split()[0].lower()
                if cmd_lower in ("/id", "/getid"):
                    id_msg = f"🆔 Your {platform.capitalize()} Chat ID is:\n\n`{chat_id}`"
                    self._send_inbound_reply(
                        platform, chat_id, text=id_msg, account_name=account_name, root_cfg=root_cfg
                    )
                    try:
                        from hecos.hpm.contacts import store as contact_store
                        field_key = f"{platform}_id"
                        if not contact_store.find_by_platform_value(field_key, chat_id):
                            self._send_inbound_reply(
                                platform,
                                chat_id,
                                text="ℹ️ Add this ID to your Hecos Contacts card to enable outbound messages by name.",
                                account_name=account_name,
                                root_cfg=root_cfg,
                            )
                    except Exception:
                        pass
                    return

                if is_admin:
                    try:
                        from hecos.hpm.remote_access_pro.main import handle_remote_command
                        rap_result = handle_remote_command(cleaned)
                        if rap_result is not None:
                            logger.info("MESSENGER", f"[RAP] Command '{cmd_lower}' handled directly.")
                            self._send_inbound_reply(
                                platform, chat_id, text=str(rap_result), account_name=account_name, root_cfg=root_cfg
                            )
                            return
                    except ImportError:
                        pass
                    except Exception as rap_err:
                        logger.error("MESSENGER", f"[RAP] Command error: {rap_err}")

            # 3. Route to Hecos Agentic Loop with Soul-merged & bot-matched runtime config
            from hecos.core.agent.loop import AgentExecutor

            turn_start_ts = time.time()
            turn_id = f"inb_{uuid.uuid4().hex[:10]}"
            turn_cfg, cfg_mgr, session_id = _build_inbound_runtime_context(
                platform=platform,
                chat_id=chat_id,
                account_name=account_name,
            )
            eff_persona = (turn_cfg.get("ai") or {}).get("active_personality") or "Hecos_System_Soul"
            eff_btype = str((turn_cfg.get("backend") or {}).get("type") or "ollama")
            eff_model = ((turn_cfg.get("backend") or {}).get(eff_btype) or {}).get("model", "?")

            logger.info(
                "MESSENGER",
                f"Routing inbound {platform}:{chat_id} via bot='{account_name or 'default'}' "
                f"(persona='{eff_persona}', model='{eff_model}', session='{session_id}')...",
            )

            user_id = "admin" if is_admin else f"{platform}_{re.sub(r'[^a-zA-Z0-9_-]+', '_', str(chat_id))}"
            executor = AgentExecutor(
                config=turn_cfg,
                config_manager=cfg_mgr,
                state_manager=None,
                current_user_id=user_id,
                current_user_role="admin" if is_admin else "user",
                session_id=session_id,
                turn_id=turn_id,
            )
            video_response, _ = executor.run_agentic_loop(cleaned, voice_status=False)

            # If the LLM already dispatched directly to this exact chat via a MESSENGER tool during the turn,
            # avoid sending a duplicate bubble from InboundRouter.
            if has_outbound_since(turn_start_ts, platform=platform, chat_id=chat_id, turn_id=turn_id):
                logger.info(
                    "MESSENGER",
                    f"Skipping InboundRouter echo for {platform}:{chat_id} (already delivered via MESSENGER tool in turn {turn_id}).",
                )
                return

            caption, real_files = _extract_reply_text_and_media(video_response or "")
            if real_files:
                if caption and len(caption) <= 1000:
                    self._send_inbound_reply(
                        platform,
                        chat_id,
                        text=caption,
                        file_paths=real_files,
                        account_name=account_name,
                        root_cfg=root_cfg,
                    )
                else:
                    self._send_inbound_reply(
                        platform,
                        chat_id,
                        text="",
                        file_paths=real_files,
                        account_name=account_name,
                        root_cfg=root_cfg,
                    )
                    if caption:
                        self._send_inbound_reply(
                            platform,
                            chat_id,
                            text=caption,
                            account_name=account_name,
                            root_cfg=root_cfg,
                        )
                return

            reply_text = caption or "..."
            self._send_inbound_reply(
                platform, chat_id, text=reply_text, account_name=account_name, root_cfg=root_cfg
            )

        except Exception as exc:
            logger.error("MESSENGER", f"Error routing inbound message from {platform}:{chat_id}: {exc}")
            try:
                self._send_inbound_reply(
                    platform,
                    chat_id,
                    text=f"⚠️ Internal Hecos error while processing message: {exc}",
                    account_name=account_name,
                    root_cfg=root_cfg,
                )
            except Exception:
                pass
