"""
search/copilot_planner.py
Pure-logic helpers for Net Search AI Copilot:
- Global Preset (SoulProfile) resolution, avatar/voice summary, & special instructions
- Conversational filler stripping, mode/filter normalization, & heuristic/LLM turn planner
- Search-aware LLM system prompt & responder configuration builder
"""
from __future__ import annotations

import copy
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("net_search.search.copilot_planner")

VALID_MODES = {"clear", "dark", "files", "osint", "deep"}
MODE_VALID_FILTERS = {
    "clear": {"all", "web", "images", "videos", "audio", "files"},
    "dark": {"all", "dark_directories", "dark_forums", "dark_leaks", "dark_market"},
    "files": {"all", "files_docs", "files_data", "files_archives", "files_code"},
    "osint": {"all", "osint_social", "osint_dev", "osint_media"},
    "deep": {"all", "deep_clear", "deep_dark", "deep_media", "deep_files"},
}


# ── 1. Preset / Soul Resolution ────────────────────────────────────────────────

def format_soul_name(soul_file: str) -> str:
    if not soul_file:
        return "Hecos AI"
    s = str(soul_file).replace(".yaml", "").strip()
    parts = s.split("_")
    cap_parts = [p.capitalize() if p.islower() else p for p in parts]
    return " ".join(cap_parts).strip()


def get_soul_display_name(s: Any) -> str:
    if not s:
        return "Hecos AI"
    persona_obj = getattr(s, "persona", None)
    soul_raw = (getattr(persona_obj, "soul_file", None) or "").strip() if persona_obj else ""
    if soul_raw:
        return format_soul_name(soul_raw)
    meta_obj = getattr(s, "meta", None)
    meta_name = (getattr(meta_obj, "name", None) or getattr(meta_obj, "id", None) or "").strip() if meta_obj else ""
    return meta_name or "Hecos AI"


def resolve_preset_voice_summary(s: Any, sys_tts_engine: str, sys_tts_voice: str) -> Dict[str, Any]:
    voice = getattr(s, "voice", None)
    raw_eng = (getattr(voice, "tts_engine", None) or "").strip() if voice else ""
    eff_eng = raw_eng if raw_eng and raw_eng != "unknown" else (sys_tts_engine or "piper")
    raw_v = ""
    if voice:
        eng_l = eff_eng.lower()
        if eng_l == "kokoro":
            raw_v = getattr(voice, "kokoro_voice", None) or getattr(voice, "kokoro_preset", None) or getattr(voice, "tts_voice", None) or ""
        elif eng_l == "xtts2":
            raw_v = getattr(voice, "xtts_speaker_wav", None) or getattr(voice, "xtts_preset", None) or getattr(voice, "tts_voice", None) or ""
        elif eng_l in ("fish_speech", "fish"):
            raw_v = getattr(voice, "fish_reference_audio", None) or getattr(voice, "fish_preset", None) or getattr(voice, "tts_voice", None) or ""
        else:
            raw_v = getattr(voice, "tts_voice", None) or ""
    eff_voice = (str(raw_v).strip() or sys_tts_voice or "Default")
    return {
        "tts_engine": eff_eng,
        "tts_voice": eff_voice,
        "is_default": not bool(raw_eng and raw_eng != "unknown"),
    }


def load_copilot_presets_payload(log: Optional[logging.Logger] = None) -> Dict[str, Any]:
    """Discovers available Global Presets (SoulProfiles) with model/inference/voice metadata."""
    _log = log or logger
    try:
        from hecos.core.global_presets.manager import list_souls, get_active_soul_id
        from hecos.core.persona.persona_media import PersonaMediaManager

        sys_cfg: Dict[str, Any] = {}
        try:
            from hecos.core.llm.brain import load_config
            sys_cfg = load_config() or {}
        except Exception:
            pass

        try:
            from hecos.core.audio.device_manager import get_audio_config
            acfg = get_audio_config() or {}
            sys_tts_engine = acfg.get("tts_engine") or sys_cfg.get("ai", {}).get("tts_engine") or "piper"
            sys_tts_voice = acfg.get("tts_voice") or sys_cfg.get("ai", {}).get("tts_voice") or ""
        except Exception:
            ai_s = sys_cfg.get("ai", {})
            sys_tts_engine = ai_s.get("tts_engine") or "piper"
            sys_tts_voice = ai_s.get("tts_voice") or ""

        ai_defaults = sys_cfg.get("ai", {}) if isinstance(sys_cfg, dict) else {}
        sys_model = ai_defaults.get("model") or ai_defaults.get("model_name") or "System Default"
        sys_backend = ai_defaults.get("backend_type") or sys_cfg.get("llm", {}).get("backend_type") or "auto"
        active_global_id = get_active_soul_id("global") or ""

        presets: List[Dict[str, Any]] = []
        for s in list_souls():
            if s and s.meta and s.meta.id:
                pname = getattr(s.persona, "soul_file", None) or s.meta.id
                av_info = PersonaMediaManager.resolve_avatar(pname)
                soul_raw = getattr(s.persona, "soul_file", None) or ""
                soul_clean = get_soul_display_name(s)
                m_obj = getattr(s, "model", None)
                inf_obj = getattr(s, "inference", None)
                raw_model = (getattr(m_obj, "model_name", None) or "").strip() if m_obj else ""
                raw_backend = (getattr(m_obj, "backend_type", None) or "").strip() if m_obj else ""
                presets.append({
                    "id": s.meta.id,
                    "name": s.meta.name or s.meta.id,
                    "soul_file": soul_raw,
                    "soul_name": soul_clean,
                    "icon": getattr(s.meta, "icon", "🧠") or "🧠",
                    "avatar_url": av_info.get("url", "/assets/Hecos_Logo_NBG.png"),
                    "avatar_type": av_info.get("type", "image"),
                    "description": getattr(s.meta, "description", "") or "",
                    "is_active_global": (s.meta.id == active_global_id),
                    "model": {
                        "model_name": raw_model or sys_model,
                        "backend_type": raw_backend or sys_backend,
                        "is_default": not bool(raw_model),
                    },
                    "inference": {
                        "preset_name": (getattr(inf_obj, "preset_name", None) or "") if inf_obj else "",
                        "temperature": getattr(inf_obj, "temperature", None) if inf_obj else None,
                        "top_p": getattr(inf_obj, "top_p", None) if inf_obj else None,
                        "repeat_penalty": getattr(inf_obj, "repeat_penalty", None) if inf_obj else None,
                        "num_ctx": getattr(inf_obj, "num_ctx", None) if inf_obj else None,
                        "max_tokens": getattr(inf_obj, "max_tokens", None) if inf_obj else None,
                    },
                    "voice": resolve_preset_voice_summary(s, sys_tts_engine, sys_tts_voice),
                })

        if not presets:
            presets = [{
                "id": "default", "name": "Default Soul", "soul_file": "Hecos_System_Soul",
                "soul_name": "Hecos AI", "icon": "🧠", "avatar_url": "/assets/Hecos_Logo_NBG.png",
                "avatar_type": "image", "description": "Standard Assistant",
                "is_active_global": True,
                "model": {"model_name": sys_model, "backend_type": sys_backend, "is_default": True},
                "inference": {"preset_name": "", "temperature": None, "top_p": None, "repeat_penalty": None, "num_ctx": None, "max_tokens": None},
                "voice": {"tts_engine": sys_tts_engine, "tts_voice": sys_tts_voice or "Default", "is_default": True},
            }]
        return {"ok": True, "active_global_id": active_global_id, "presets": presets}
    except Exception as e:
        _log.warning(f"[HecosAI] Failed to list soul presets: {e}")
        return {
            "ok": True,
            "presets": [
                {"id": "balanced", "name": "Balanced Assistant", "soul_file": "balanced", "soul_name": "Balanced Assistant", "icon": "🧠", "avatar_url": "/assets/Hecos_Logo_NBG.png", "avatar_type": "image", "description": "General AI"},
                {"id": "creative", "name": "Creative Investigator", "soul_file": "creative", "soul_name": "Creative Investigator", "icon": "🎨", "avatar_url": "/assets/Hecos_Logo_NBG.png", "avatar_type": "image", "description": "Open exploration"},
                {"id": "precise", "name": "Precise Analyst", "soul_file": "precise", "soul_name": "Precise Analyst", "icon": "🎯", "avatar_url": "/assets/Hecos_Logo_NBG.png", "avatar_type": "image", "description": "Accurate & concise"},
            ],
        }


def resolve_active_soul(preset_id: str, log: Optional[logging.Logger] = None) -> Any:
    """Resolve effective Global Preset (explicit preset_id -> active_global_preset -> None)."""
    _log = log or logger
    try:
        from hecos.core.global_presets.manager import get_soul, get_active_soul_id
        if preset_id and preset_id not in ("default", "", None):
            soul = get_soul(preset_id)
            if soul:
                return soul
        active_id = get_active_soul_id("global")
        if active_id and active_id not in ("default", "", None):
            soul = get_soul(active_id)
            if soul:
                _log.info(f"[Copilot] Using system active preset '{active_id}' (payload had '{preset_id}')")
                return soul
    except Exception as e:
        _log.warning(f"[Copilot] Could not resolve soul preset: {e}")
    return None


def build_preset_instructions(soul: Any) -> str:
    """Collect special_instructions + custom_instructions from a preset without overwriting either."""
    if not soul:
        return ""
    parts = []
    special = (getattr(soul.persona, "special_instructions", None) or "").strip()
    custom = (getattr(soul.persona, "custom_instructions", None) or "").strip()
    if special:
        parts.append(special)
    if custom:
        parts.append(custom)
    return "\n".join(parts)


# ── 2. Intent Planner & Query Normalizer ───────────────────────────────────────

def strip_conversational_fillers(raw_text: str) -> str:
    """Deterministically removes Italian/English request wrappers and partitive fillers."""
    s = (raw_text or "").strip()
    if not s:
        return ""
    wrapper_re = re.compile(
        r"^(?:/search|/hsearch|/s|/find|/images|/videos|/files|/dark"
        r"|fai\s+una\s+ricerca(?:\s+(?:su|per))?|esegui\s+una\s+ricerca(?:\s+(?:su|per))?"
        r"|fammi\s+vedere|mostrami|cercami|trovami|dammi|cerca|trova"
        r"|mi\s+servono|mi\s+serve|ho\s+bisogno\s+di|vorrei(?:\s+(?:vedere|cercare|trovare))?"
        r"|search(?:\s+for)?|find(?:\s+me|\s+for)?|look\s+(?:up(?:\s+for)?|for)"
        r"|show\s+me|get\s+me|give\s+me|i\s+need(?:\s+some)?|i\s+want(?:\s+some)?"
        r"|un\s+p[oò]['’]?\s+di|qualche|alcun[ei]|degli|delle|dell['’]|dei|del|della|dello"
        r"|su|sul|sulla|sui|sugli|sulle|nel|nella|in|per|some)\b[\s,:;-]*",
        re.IGNORECASE,
    )
    for _ in range(4):
        nxt = wrapper_re.sub("", s).strip()
        if nxt == s or not nxt:
            break
        s = nxt
    s = re.sub(r"[\s,]+(?:per\s+favore|grazie|please|thanks)[.!?\s]*$", "", s, flags=re.IGNORECASE).strip()
    return s.strip('"\' ') or raw_text.strip()


def normalize_mode_and_filter(mode: str, flt: str, active_mode: str, auto_mode: bool) -> Tuple[str, str]:
    m = (mode or "").strip().lower()
    if m == "media":
        m = "clear"
    if not auto_mode:
        am = (active_mode or "clear").strip().lower()
        m = am if am in VALID_MODES else "clear"
    elif m not in VALID_MODES:
        m = "deep"

    f = (flt or "all").strip().lower()
    if m == "deep" and f in {"images", "videos", "audio"}:
        f = "deep_media"
    valid_filters = MODE_VALID_FILTERS.get(m, {"all"})
    if f not in valid_filters:
        f = "all"
    return m, f


def heuristic_plan(
    user_message: str,
    has_results: bool,
    active_mode: str,
    auto_mode: bool,
) -> Dict[str, str]:
    clean = (user_message or "").strip()
    lower = clean.lower()

    is_greeting = bool(re.match(
        r"^(?:ciao|buongiorno|buonasera|salve|hey|hello|hi|chi sei|come ti chiami|cosa puoi fare|help|aiuto)[\s!?.]*$",
        lower,
    ))
    if is_greeting:
        m, f = normalize_mode_and_filter("deep", "all", active_mode, auto_mode)
        return {"action": "chat", "query": "", "mode": m, "filter": f}

    is_analyze = has_results and bool(re.search(
        r"\b(?:riassumi|riepilogo|sintetizza|summarize|summary|key\s+(?:findings|points|takeaways)|"
        r"find\s+media|questi\s+risultati|these\s+results|this\s+search|among\s+these|"
        r"confronta|compare|analizza\s+i\s+risultati|extract)\b",
        lower,
    ))
    if is_analyze:
        m, f = normalize_mode_and_filter(active_mode, "all", active_mode, auto_mode)
        return {"action": "analyze_current", "query": "", "mode": m, "filter": f}

    mode = "deep"
    flt = "all"
    if any(w in lower for w in ("dark web", "darknet", ".onion", "tor ", " tor", "hidden service")):
        mode = "dark"
    elif any(w in lower for w in ("osint", "username", "profilo", "account")):
        mode = "osint"
    elif any(w in lower for w in (".pdf", ".docx", ".xlsx", ".zip", ".epub", "dork", "filetype:", "documento", "documenti", "archivio")):
        mode = "files"
    elif any(w in lower for w in ("foto", "immagini", "immagine", "photo", "photos", "pictures", "image", "images")):
        mode = "clear"
        flt = "images"
    elif any(w in lower for w in ("video", "filmati", "filmato", "youtube")):
        mode = "clear"
        flt = "videos"
    elif any(w in lower for w in ("audio", "musica", "canzoni", "canzone", "podcast", "mp3")):
        mode = "clear"
        flt = "audio"

    m, f = normalize_mode_and_filter(mode, flt, active_mode, auto_mode)
    return {
        "action": "new_search",
        "query": strip_conversational_fillers(clean),
        "mode": m,
        "filter": f,
    }


def plan_copilot_turn(
    user_message: str,
    current_query: str,
    has_results: bool,
    active_mode: str,
    auto_mode: bool,
    preset_instructions: str,
    cfg: dict,
    log: Optional[logging.Logger] = None,
) -> Dict[str, str]:
    """
    Autonomous LLM planner for Net Search Copilot.
    Decides action (new_search | analyze_current | chat), cleans/optimizes query,
    and selects mode + category tab when Auto-Mode is enabled.
    """
    _log = log or logger
    fallback = heuristic_plan(user_message, has_results, active_mode, auto_mode)
    if fallback["action"] == "chat":
        return fallback

    try:
        from hecos.core.llm.brain import generate_response

        plan_cfg = copy.deepcopy(cfg) if cfg else {}
        plan_cfg["disable_tools"] = True
        plan_cfg["payload_control"] = {
            "send_personality": False,
            "send_memory": False,
            "send_tools": False,
        }
        plan_cfg["llm"] = {**(plan_cfg.get("llm") or {}), "temperature": 0.1, "max_tokens": 220}
        if "ai" not in plan_cfg:
            plan_cfg["ai"] = {}

        mode_rule = (
            "AUTO-MODE IS ON: You MUST choose the best mode autonomously regardless of current UI mode pill. "
            "Use 'deep' (Global Sweep) for general/broad topics when the user did NOT request a specific network. "
            "Use 'clear' for surface web, news, photos, images, videos, or audio (and set filter to 'images'/'videos'/'audio'/'web'). "
            "Use 'files' for downloadable files/PDF/DOCX/archives. "
            "Use 'osint' for usernames/social profiles. "
            "Use 'dark' ONLY if the user explicitly mentions dark web, darknet, .onion, Tor, or hidden services."
            if auto_mode
            else f"AUTO-MODE IS OFF (MANUAL): Always keep mode='{active_mode}'."
        )

        lang_hint = f"\nPreset language/search rules:\n{preset_instructions}" if preset_instructions else ""

        plan_cfg["ai"]["special_instructions"] = (
            "You are the autonomous search orchestrator inside Hecos Net Search (NOT a general chat or image generator). "
            "Output ONLY a single valid JSON object with keys: action, query, mode, filter.\n\n"
            "Rules:\n"
            "1. action:\n"
            "   - 'new_search': whenever the user asks to search, find, get, show, or wants any topic, object, animal, media, document, site, or info "
            "(EVEN IF previous results are already open for a different topic!). Never refuse a search and never treat a new topic as 'analyze_current'.\n"
            "   - 'analyze_current': ONLY when has_results=true AND the user explicitly asks to summarize/analyze/filter the currently loaded results.\n"
            "   - 'chat': ONLY for pure greetings or questions about how the search assistant works.\n"
            "2. query:\n"
            "   - Extract clean search keywords ONLY (max 8 words). Strip ALL conversational wrappers like 'cercami', 'un pò di', 'mi servono', 'vorrei', 'trovami', 'find me', 'i need some'.\n"
            "   - Translate to English ONLY if Preset rules explicitly require searching in English; otherwise keep concise keywords.\n"
            "   - Empty string '' if action is 'analyze_current' or 'chat'.\n"
            f"3. mode: one of ['deep', 'clear', 'dark', 'files', 'osint']. {mode_rule}\n"
            "4. filter: 'all', 'web', 'images', 'videos', 'audio', 'files', or 'deep_media'/'deep_clear'/'deep_dark'/'deep_files'.\n"
            f"{lang_hint}"
        )

        planner_input = json.dumps({
            "user_message": user_message,
            "current_query": current_query or "",
            "has_results": bool(has_results),
            "current_ui_mode": active_mode,
            "auto_mode": bool(auto_mode),
        }, ensure_ascii=False)

        t_plan = time.time()
        raw = generate_response(
            user_text=f"Plan this Net Search turn:\n{planner_input}",
            external_config=plan_cfg,
            save_history=False,
            tag="COPILOT_QUERY_OPT",
        ) or ""
        _log.debug(f"[Copilot] Planner raw LLM response in {round((time.time() - t_plan) * 1000)}ms: {raw[:240]!r}")

        cleaned_raw = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.IGNORECASE).strip()
        json_match = re.search(r"\{[\s\S]*\}", cleaned_raw)
        if json_match:
            parsed = json.loads(json_match.group(0))
            action = str(parsed.get("action") or fallback["action"]).strip().lower()
            if action not in {"new_search", "analyze_current", "chat"}:
                action = fallback["action"]
            if action == "analyze_current" and not has_results:
                action = "new_search"

            raw_q = str(parsed.get("query") or "").strip().strip('"').strip("'")
            if action == "new_search":
                cleaned_q = strip_conversational_fillers(raw_q) if raw_q else fallback["query"]
                if not cleaned_q or len(cleaned_q) > 200 or "\n" in cleaned_q:
                    cleaned_q = fallback["query"]
            else:
                cleaned_q = ""

            m, f = normalize_mode_and_filter(
                parsed.get("mode") or fallback["mode"],
                parsed.get("filter") or fallback["filter"],
                active_mode,
                auto_mode,
            )
            plan = {"action": action, "query": cleaned_q, "mode": m, "filter": f}
            _log.info(f"[Copilot] Planned turn: '{user_message}' → {plan} (auto_mode={auto_mode})")
            return plan
    except Exception as e:
        _log.warning(f"[Copilot] LLM planner fallback used ({e})")

    return fallback


def build_responder_config(
    resolved_sess: Any,
    merged_cfg: Any,
    soul: Any,
    preset_instructions: str,
) -> Dict[str, Any]:
    """Builds the search-context-injected LLM config for the Net Search Copilot responder."""
    search_context = ""
    if resolved_sess and getattr(resolved_sess, "results", None):
        items_summary = []
        for i, r in enumerate(resolved_sess.results[:15], 1):
            snip = (r.snippet or "")[:140].replace("\n", " ").strip()
            items_summary.append(f"[{i}] {r.title} ({r.engine}, {r.category}): {snip} (URL: {r.url})")
        search_context = (
            f"\n\n[ACTIVE NET SEARCH RESULTS FOR \"{resolved_sess.query}\" (Mode: {resolved_sess.mode})]\n"
            f"Total results: {resolved_sess.total_results} | Duration: {resolved_sess.duration_ms}ms\n"
            f"Top indexed sources:\n" + "\n".join(items_summary)
        )
    elif resolved_sess is not None:
        search_context = (
            f"\n\n[ACTIVE NET SEARCH RESULTS FOR \"{resolved_sess.query}\" (Mode: {resolved_sess.mode})]\n"
            "Total results: 0. Inform the user clearly that this search yielded 0 results and suggest trying Global Sweep or broader keywords."
        )

    copilot_base = (
        "You are speaking INSIDE the dedicated Hecos Net Search Copilot sidebar — NOT the general main chat. "
        "CRITICAL RULES FOR NET SEARCH CONTEXT:\n"
        "1. NEVER use IMAGE_GEN, NEVER output `/img` commands, and NEVER offer or pretend to generate AI images here (the user uses the main chat for image generation; here they want real web/media search results).\n"
        "2. NEVER invent, imagine, or roleplay delivering items/bouquets/data in place of real search results, and NEVER prefix your answer with 'SYNCHRONIZED'.\n"
        "3. Real web results, galleries, and image/video thumbnails are ALREADY displayed live in the main Net Search results panel next to this chat — guide the user to explore/filter them there (e.g. under the Images tab), cite top sources with [1], [2], etc., and when sharing specific links format them as Markdown `[Source Title](URL)` or full `https://...` URLs.\n"
        "4. Keep your character tone/personality from preset directives without breaking rules 1-3."
    )

    cfg_copy = copy.deepcopy(merged_cfg) if isinstance(merged_cfg, dict) else {}
    cfg_copy["disable_tools"] = True
    if "ai" not in cfg_copy:
        cfg_copy["ai"] = {}

    system_prompt_parts = [copilot_base]
    if preset_instructions:
        soul_label = soul.meta.name if (soul and soul.meta) else "Active"
        system_prompt_parts.append(f"[PRESET DIRECTIVES — {soul_label}]:\n{preset_instructions}")
    if search_context:
        system_prompt_parts.append(search_context)
    final_system_prompt = "\n\n".join(system_prompt_parts)

    existing_si = (cfg_copy["ai"].get("special_instructions") or "").strip()
    if existing_si and existing_si != preset_instructions:
        cfg_copy["ai"]["special_instructions"] = existing_si + "\n\n" + copilot_base + search_context
    else:
        cfg_copy["ai"]["special_instructions"] = final_system_prompt
    return cfg_copy

