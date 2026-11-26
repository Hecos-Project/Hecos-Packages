"""
Smart Target, Group & Contact Resolver for Hecos Messenger (v2.4).
Resolves:
  - Dedicated WhatsApp Groups & Telegram Groups/Channels ('group:Hecos', 'gruppo Famiglia', phonetic aliases like 'Ecos')
    with full cross-platform disambiguation when a group name exists on both platforms
  - Natural contact names ('Rowena', 'admin') from Hecos Contacts
  - 15-minute follow-up channel continuations ('last' or omitted platform)
  - Explicit platform-prefixed targets ('whatsapp:+39...', 'whatsapp:group:Famiglia', 'telegram:Urania:123456')
Never guesses on unknown groups or ambiguous targets, and blocks seeded example dummy numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from .registry import ProviderRegistry, registry as default_registry
from .session_memory import (
    FOLLOWUP_ALIASES,
    get_recent_context,
    is_followup_token,
    matches_recent_contact,
)


_PHONE_LIKE_RE = re.compile(r"^\+?[0-9][0-9\s\-\(\)\.]{5,20}$")
_NUMERIC_ID_RE = re.compile(r"^-?[0-9]{5,20}$")
_SEED_PLACEHOLDER_DIGITS = frozenset({"3331234567", "393331234567"})

_GROUP_PREFIX_RE = re.compile(
    r"^(?:(?:group|channel|gruppo|canale)\s*:\s*|(?:il\s+)?(?:gruppo|canale|group|channel)(?:\s+(?:di|del|della|su|on|of))?\s+)(.+)$",
    re.IGNORECASE,
)


@dataclass
class ResolvedTarget:
    platform: str
    recipient: str
    contact_name: Optional[str] = None
    bot_name: Optional[str] = None
    field_type: Optional[str] = None


def _looks_like_phone(value: str) -> bool:
    s = value.strip()
    if not s:
        return False
    digits = re.sub(r"\D", "", s)
    return bool(_PHONE_LIKE_RE.match(s)) and 7 <= len(digits) <= 15


def _is_seed_placeholder_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value or "")
    return digits in _SEED_PLACEHOLDER_DIGITS


def _norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").strip().lower()).strip()


def _phonetic_skeleton(value: str) -> str:
    """
    Produces an Italian/English STT-tolerant phonetic skeleton so voice transcriptions
    like 'haicos', 'aicos', 'heicos', 'echos', 'ecos', 'ekos', 'iqos', 'hecos'
    all normalize deterministically to 'ekos'.
    """
    s = re.sub(r"[^a-z0-9]+", "", (value or "").lower())
    if not s:
        return ""
    s = s.replace("ch", "k").replace("ck", "k").replace("qu", "k").replace("q", "k").replace("c", "k")
    s = s.replace("h", "")
    # Normalize English/Italian diphthong pronunciations before 'k' ('aikos'/'aykos'/'eikos'/'ikos' -> 'ekos')
    s = re.sub(r"^(?:ai|ay|ei|ey|i)(?=k)", "e", s)
    # Collapse repeated consonants/vowels ('ekkos' -> 'ekos')
    s = re.sub(r"(.)\1+", r"\1", s)
    return s


def _query_candidate_tokens(clean_q: str) -> list[str]:
    """Splits compound LLM queries like 'iqos_Ecos' or 'gruppo di echos' into clean candidate keys."""
    full = _norm_key(clean_q)
    out = [full] if full else []
    stop_words = {"di", "del", "della", "su", "on", "of", "the", "il", "lo", "la", "gruppo", "group", "whatsapp", "wazzap", "telegram"}
    parts = [p for p in re.split(r"[\s_\-\/]+", clean_q.strip().lower()) if p and p not in stop_words]
    for p in parts:
        np = _norm_key(p)
        if np and len(np) >= 3 and np not in out:
            out.append(np)
    return out


def _matches_group_aliases(query_tokens: list[str], names_and_aliases: set[str]) -> bool:
    if not query_tokens or not names_and_aliases:
        return False
    target_norms = {_norm_key(x) for x in names_and_aliases if _norm_key(x)}
    target_phonetics = {_phonetic_skeleton(x) for x in target_norms if len(_phonetic_skeleton(x)) >= 3}

    for qt in query_tokens:
        if qt in target_norms:
            return True
        qp = _phonetic_skeleton(qt)
        if len(qp) >= 3 and qp in target_phonetics:
            return True
    return False


def _extract_group_intent(candidate: str) -> tuple[bool, str]:
    """Returns `(explicit_group_syntax, inner_query)` if `candidate` explicitly names a group/channel."""
    m = _GROUP_PREFIX_RE.match((candidate or "").strip())
    if m:
        return True, m.group(1).strip()
    return False, (candidate or "").strip()


def _lookup_telegram_group(
    query: str,
    root_cfg: Any,
    explicit_bot: Optional[str] = None,
) -> Optional[ResolvedTarget]:
    """Matches `query` against enabled entries in `root_cfg.telegram.groups` (name, chat_id, or aliases)."""
    tg_cfg = getattr(root_cfg, "telegram", None) if root_cfg is not None else None
    if not tg_cfg or not getattr(tg_cfg, "enabled", False):
        return None

    _, clean_q = _extract_group_intent(query)
    q_tokens = _query_candidate_tokens(clean_q)
    q_raw_low = clean_q.strip().lower().lstrip("@")
    if not q_tokens and not q_raw_low:
        return None

    for grp in getattr(tg_cfg, "groups", None) or []:
        if not getattr(grp, "enabled", True) or not getattr(grp, "chat_id", "").strip():
            continue
        gname = (grp.name or "").strip()
        cid = grp.chat_id.strip()
        cid_clean = cid.lower().lstrip("@")

        alias_pool = {gname, cid_clean, re.split(r"\s*[\-—|]\s*", gname)[0].strip()}
        for raw_al in (grp.aliases or "").split(","):
            if raw_al.strip():
                alias_pool.add(raw_al.strip())
        alias_pool.discard("")

        if q_raw_low == cid_clean or _matches_group_aliases(q_tokens, alias_pool):
            pref_bot = (getattr(grp, "preferred_bot", "") or "").strip() or None
            return ResolvedTarget(
                platform="telegram",
                recipient=cid,
                contact_name=f"Group: {gname}" if gname else cid,
                bot_name=explicit_bot or pref_bot,
                field_type="telegram_group",
            )

    return None


def _live_discover_whatsapp_group(
    q_tokens: list[str],
    q_raw_low: str,
    wa_cfg: Any,
    reg: ProviderRegistry,
    explicit_bot: Optional[str] = None,
) -> Optional[ResolvedTarget]:
    """
    Live-scans WhatsApp Web's `#group-filter` list when a requested WhatsApp group is not yet
    in `messenger.toml` (e.g. user just created a new group on their phone!) and auto-registers
    an unambiguous match so future calls and inbound `@mention` replies work immediately.
    """
    wa_prov = reg.get("whatsapp")
    if not wa_prov or not hasattr(wa_prov, "scan_groups_cached"):
        return None

    scan_res = wa_prov.scan_groups_cached(wa_cfg)
    live_groups = (scan_res or {}).get("groups") or []
    if not live_groups:
        return None

    matches: list[dict[str, Any]] = []
    for g in live_groups:
        title = str(g.get("title") or "").strip()
        raw_title = str(g.get("raw_title") or title).strip()
        if not title:
            continue
        head_part = re.split(r"\s*[\-—|:]\s*", title)[0].strip()
        first_word = title.split()[0].strip() if title.split() else ""
        pool = {title, head_part}
        if len(first_word) >= 4:
            pool.add(first_word)
        if q_raw_low == title.lower() or _matches_group_aliases(q_tokens, pool):
            matches.append({"title": title, "raw_title": raw_title, "short_name": head_part or title})

    if len(matches) != 1:
        return None

    chosen = matches[0]
    # Auto-persist newly discovered group into messenger.toml so user sees it in UI & listener watches it
    try:
        from ..messenger_config.config_manager import get_config, save_config
        raw_cfg = get_config()
        wa_sec = raw_cfg.setdefault("whatsapp", {})
        existing_list = wa_sec.setdefault("groups", [])
        already = any(
            str(x.get("group_title") or "").strip().lower() == chosen["raw_title"].lower()
            for x in existing_list if isinstance(x, dict)
        )
        if not already:
            existing_list.append({
                "name": chosen["short_name"],
                "enabled": True,
                "group_title": chosen["raw_title"],
                "aliases": "",
                "sign_persona": True,
                "inbound_mode": "mention",
                "inbound_keywords": "urania, hecos",
                "default_persona": "",
            })
            save_config(raw_cfg)
    except Exception:
        pass

    return ResolvedTarget(
        platform="whatsapp",
        recipient=f"group:{chosen['raw_title']}",
        contact_name=f"Group: {chosen['title']}",
        bot_name=explicit_bot,
        field_type="whatsapp_group",
    )


def _lookup_whatsapp_group(
    query: str,
    root_cfg: Any,
    explicit_bot: Optional[str] = None,
    allow_live_scan: bool = False,
    reg: ProviderRegistry = default_registry,
) -> Optional[ResolvedTarget]:
    """Matches `query` against enabled entries in `root_cfg.whatsapp.groups` (plus optional live scan)."""
    wa_cfg = getattr(root_cfg, "whatsapp", None) if root_cfg is not None else None
    if not wa_cfg or not getattr(wa_cfg, "enabled", False):
        return None

    _, clean_q = _extract_group_intent(query)
    q_tokens = _query_candidate_tokens(clean_q)
    q_raw_low = clean_q.strip().lower()
    if not q_tokens and not q_raw_low:
        return None

    for grp in getattr(wa_cfg, "groups", None) or []:
        if not getattr(grp, "enabled", True):
            continue
        gname = (getattr(grp, "name", "") or "").strip()
        gtitle = (getattr(grp, "group_title", "") or gname).strip()
        if not gtitle:
            continue

        head_title = re.split(r"\s*[\-—|:]\s*", gtitle)[0].strip()
        alias_pool = {gname, gtitle, head_title}
        for raw_al in (getattr(grp, "aliases", "") or "").split(","):
            if raw_al.strip():
                alias_pool.add(raw_al.strip())
        alias_pool.discard("")

        if q_raw_low in (gtitle.lower(), gname.lower()) or _matches_group_aliases(q_tokens, alias_pool):
            label = gname or gtitle
            return ResolvedTarget(
                platform="whatsapp",
                recipient=f"group:{gtitle}",
                contact_name=f"Group: {label}",
                bot_name=explicit_bot,
                field_type="whatsapp_group",
            )

    if allow_live_scan:
        return _live_discover_whatsapp_group(q_tokens, q_raw_low, wa_cfg, reg=reg, explicit_bot=explicit_bot)

    return None


def _resolve_configured_group(
    query: str,
    root_cfg: Any,
    norm_platform: str = "",
    explicit_bot: Optional[str] = None,
    recent: Any = None,
    allow_live_wa_scan: bool = False,
    reg: ProviderRegistry = default_registry,
) -> Optional[ResolvedTarget]:
    """
    Searches configured WhatsApp and/or Telegram groups according to `norm_platform`.
    Raises `ValueError('CLARIFICATION_REQUIRED: ...')` if both platforms match and no platform was specified.
    """
    if norm_platform == "whatsapp":
        return _lookup_whatsapp_group(
            query,
            root_cfg,
            explicit_bot=explicit_bot,
            allow_live_scan=allow_live_wa_scan,
            reg=reg,
        )
    if norm_platform == "telegram":
        return _lookup_telegram_group(query, root_cfg, explicit_bot=explicit_bot)

    wa_match = _lookup_whatsapp_group(query, root_cfg, explicit_bot=explicit_bot, allow_live_scan=False, reg=reg)
    tg_match = _lookup_telegram_group(query, root_cfg, explicit_bot=explicit_bot)

    if not wa_match and not tg_match and allow_live_wa_scan:
        wa_match = _lookup_whatsapp_group(query, root_cfg, explicit_bot=explicit_bot, allow_live_scan=True, reg=reg)

    if wa_match and tg_match:
        if recent is not None:
            if recent.platform == "whatsapp":
                return wa_match
            if recent.platform == "telegram":
                return tg_match
        _, clean_q = _extract_group_intent(query)
        raise ValueError(
            f"CLARIFICATION_REQUIRED: Group '{clean_q}' is configured on BOTH WhatsApp and Telegram. "
            "Do NOT guess — ask the user whether to send to the WhatsApp group or the Telegram group."
        )

    return wa_match or tg_match


def _list_configured_group_labels(root_cfg: Any, norm_platform: str = "") -> list[str]:
    labels: list[str] = []
    if norm_platform in ("", "whatsapp"):
        wa_cfg = getattr(root_cfg, "whatsapp", None) if root_cfg else None
        for g in getattr(wa_cfg, "groups", None) or []:
            if getattr(g, "enabled", True) and (g.name or g.group_title):
                labels.append(f"WhatsApp:'{g.name or g.group_title}'")
    if norm_platform in ("", "telegram"):
        tg_cfg = getattr(root_cfg, "telegram", None) if root_cfg else None
        for g in getattr(tg_cfg, "groups", None) or []:
            if getattr(g, "enabled", True) and g.name:
                labels.append(f"Telegram:'{g.name}'")
    return labels


def _lookup_contact_for_platform(query: str, platform: str) -> Optional[dict[str, Any]]:
    """Looks up a contact in Hecos Contacts store, ignoring seeded example placeholder phone numbers."""
    try:
        from hecos.hpm.contacts import store as contact_store
    except ImportError:
        return None

    res = contact_store.resolve_for_platform(query, platform)
    if res:
        if platform == "whatsapp" and _is_seed_placeholder_phone(str(res.get("address", ""))):
            return None
        return res

    tokens = [t for t in re.split(r"\s+", query.strip()) if t]
    if len(tokens) > 1:
        for tok in tokens:
            res = contact_store.resolve_for_platform(tok, platform)
            if res:
                if platform == "whatsapp" and _is_seed_placeholder_phone(str(res.get("address", ""))):
                    continue
                c = res.get("contact") or {}
                full = f"{c.get('first_name', '')} {c.get('last_name', '')} {c.get('display_name', '')}".lower()
                if all(t.lower() in full for t in tokens):
                    return res
    return None


def _find_contact_any(query: str) -> Optional[dict[str, Any]]:
    try:
        from hecos.hpm.contacts import store as contact_store
        return contact_store.get_by_id(query) or contact_store.find_by_name(query)
    except Exception:
        return None


def resolve_target(
    to: str,
    platform: Optional[str] = None,
    root_cfg: Any = None,
    bot_name: Optional[str] = None,
    reg: ProviderRegistry = default_registry,
) -> ResolvedTarget:
    """
    Resolves user/LLM target specification into a concrete ResolvedTarget.
    Raises ValueError (prefixed with CLARIFICATION_REQUIRED when ambiguous) if resolution fails.
    """
    raw_to = (to or "").strip()
    norm_platform = reg.normalize_name(platform) if platform else ""
    known_platforms = set(reg.names())

    if norm_platform and norm_platform not in known_platforms:
        raise ValueError(
            f"Unsupported platform '{platform}'. Supported platforms: {', '.join(sorted(known_platforms))}."
        )

    remember_enabled = bool(getattr(root_cfg, "remember_last_channel", True)) if root_cfg is not None else True
    ttl_min = int(getattr(root_cfg, "last_channel_ttl_minutes", 15) or 15) if root_cfg is not None else 15
    recent = get_recent_context(ttl_min) if remember_enabled else None

    enabled_names = [p.name for p in reg.enabled_providers(root_cfg)] if root_cfg else list(known_platforms)
    candidates_to_check = enabled_names or list(known_platforms)

    extracted_bot = (bot_name or "").strip() or None

    # 0. Follow-up placeholder or omitted 'to' ('', 'last', 'same', 'previous')
    if is_followup_token(raw_to):
        explicit_followup_word = raw_to.lower() in (FOLLOWUP_ALIASES - {""})
        if recent is not None:
            if not norm_platform or norm_platform == recent.platform:
                if recent.platform in candidates_to_check:
                    return ResolvedTarget(
                        platform=recent.platform,
                        recipient=recent.recipient,
                        contact_name=recent.contact_name,
                        bot_name=extracted_bot or recent.bot_name,
                    )
            elif recent.contact_name or recent.raw_query:
                raw_to = recent.contact_name or recent.raw_query or ""

        if is_followup_token(raw_to):
            if not explicit_followup_word and norm_platform == "telegram":
                return ResolvedTarget(platform="telegram", recipient="", bot_name=extracted_bot)

            raise ValueError(
                f"CLARIFICATION_REQUIRED: No active follow-up recipient/platform from the last {ttl_min} minutes "
                "(or follow-up window expired). Do NOT guess — ask the user to whom they want to send the message "
                "and on which platform (WhatsApp or Telegram)."
            )

    explicit_contact = False
    candidate = raw_to

    # 1. Strip optional 'contact:' prefix
    if candidate.lower().startswith("contact:"):
        explicit_contact = True
        candidate = candidate.split(":", 1)[1].strip()

    # 2. Extract optional leading '<platform>:' prefix BEFORE group matching (e.g. 'whatsapp:group:Hecos')
    if not explicit_contact and ":" in candidate:
        prefix, _, rest = candidate.partition(":")
        norm_prefix = reg.normalize_name(prefix)
        if norm_prefix in known_platforms:
            norm_platform = norm_prefix
            candidate = rest.strip()
            if candidate.lower().startswith("contact:"):
                explicit_contact = True
                candidate = candidate.split(":", 1)[1].strip()

    # 3. Check explicit 'group:' / 'channel:' / 'gruppo ...' intent across WhatsApp & Telegram
    explicit_group, group_inner = _extract_group_intent(candidate) if not explicit_contact else (False, candidate)
    if explicit_group:
        grp_match = _resolve_configured_group(
            group_inner,
            root_cfg,
            norm_platform=norm_platform,
            explicit_bot=extracted_bot,
            recent=recent,
            allow_live_wa_scan=True,
            reg=reg,
        )
        if grp_match:
            return grp_match
        if norm_platform != "whatsapp" and (group_inner.startswith("@") or _NUMERIC_ID_RE.match(group_inner)):
            return ResolvedTarget(platform="telegram", recipient=group_inner, bot_name=extracted_bot)
        configured_groups = _list_configured_group_labels(root_cfg, norm_platform)
        avail_note = f" Configured groups: {', '.join(configured_groups)}." if configured_groups else ""
        plat_label = norm_platform.capitalize() if norm_platform else "WhatsApp/Telegram"
        raise ValueError(
            f"CLARIFICATION_REQUIRED: {plat_label} group '{group_inner}' is not registered in Messenger settings.{avail_note} "
            "NEVER fall back to 'admin' when a group was requested — ask the user to confirm the group name or add it in Messenger settings."
        )

    # 4. Handle Telegram 'bot_name:chat_id_or_contact' notation
    if norm_platform == "telegram" and ":" in candidate and not explicit_contact:
        b_part, _, r_part = candidate.partition(":")
        if b_part.strip() and r_part.strip():
            extracted_bot = extracted_bot or b_part.strip()
            candidate = r_part.strip()

    # 5. Check configured Groups by name/alias BEFORE Contacts (respecting explicit platform when set)
    if not explicit_contact and candidate:
        grp_direct = _resolve_configured_group(
            candidate,
            root_cfg,
            norm_platform=norm_platform,
            explicit_bot=extracted_bot,
            recent=recent,
            allow_live_wa_scan=False,
            reg=reg,
        )
        if grp_direct:
            return grp_direct
        if norm_platform == "whatsapp" and not _looks_like_phone(candidate) and not _lookup_contact_for_platform(candidate, "whatsapp"):
            live_wa_grp = _lookup_whatsapp_group(candidate, root_cfg, explicit_bot=extracted_bot, allow_live_scan=True, reg=reg)
            if live_wa_grp:
                return live_wa_grp
        # If LLM guessed wrong platform on a voice-transcribed group alias (e.g. 'Ecos' exists only on the other platform),
        # check cross-platform ONLY if there is no personal Contact with that name on norm_platform
        if norm_platform and not _lookup_contact_for_platform(candidate, norm_platform):
            other_plat = "telegram" if norm_platform == "whatsapp" else "whatsapp"
            other_grp = _resolve_configured_group(candidate, root_cfg, norm_platform=other_plat, explicit_bot=extracted_bot)
            if other_grp and not _looks_like_phone(candidate) and not candidate.startswith("@"):
                raise ValueError(
                    f"CLARIFICATION_REQUIRED: '{candidate}' is registered as a {other_plat.capitalize()} group ({other_grp.contact_name}), "
                    f"not on {norm_platform.capitalize()}. Ask the user whether to send to {other_plat.capitalize()} ({other_grp.contact_name}) "
                    f"or register the group under {norm_platform.capitalize()} Groups in Messenger settings."
                )

    # 6. Block accidental dispatches to seeded placeholder phone 3331234567
    if _is_seed_placeholder_phone(candidate):
        raise ValueError(
            "SAFETY BLOCK: '+39 333 123 4567' is a dummy example phone number from the default Contacts seed — "
            "sending to it would message a random stranger from your WhatsApp account! Ask the user for the real recipient."
        )

    # 7. If platform is still omitted, infer ONLY when unambiguous or backed by active follow-up memory
    if not norm_platform:
        if not explicit_contact:
            if candidate.startswith("+") and _looks_like_phone(candidate) and "whatsapp" in candidates_to_check:
                norm_platform = "whatsapp"
            elif candidate.startswith("@") and "telegram" in candidates_to_check:
                norm_platform = "telegram"

        if not norm_platform and candidate:
            matched_resolutions: list[tuple[str, dict[str, Any]]] = []
            for p_name in candidates_to_check:
                res = _lookup_contact_for_platform(candidate, p_name)
                if res:
                    matched_resolutions.append((p_name, res))

            if len(matched_resolutions) == 1:
                p_name, res = matched_resolutions[0]
                c_obj = res.get("contact") or {}
                return ResolvedTarget(
                    platform=p_name,
                    recipient=str(res["address"]).strip(),
                    contact_name=c_obj.get("display_name") or candidate,
                    bot_name=extracted_bot,
                    field_type=res.get("field_type"),
                )

            if len(matched_resolutions) > 1:
                if recent is not None:
                    for p_name, res in matched_resolutions:
                        c_obj = res.get("contact") or {}
                        disp = c_obj.get("display_name")
                        if p_name == recent.platform and matches_recent_contact(candidate, disp, recent):
                            return ResolvedTarget(
                                platform=p_name,
                                recipient=str(res["address"]).strip(),
                                contact_name=disp or candidate,
                                bot_name=extracted_bot or recent.bot_name,
                                field_type=res.get("field_type"),
                            )

                plats = ", ".join(p for p, _ in matched_resolutions)
                disp_label = (matched_resolutions[0][1].get("contact") or {}).get("display_name") or candidate
                raise ValueError(
                    f"CLARIFICATION_REQUIRED: Contact '{disp_label}' is available on multiple platforms ({plats}) "
                    f"and there is no active follow-up channel from the last {ttl_min} minutes. "
                    "Do NOT guess — ask the user whether to send on WhatsApp or Telegram."
                )

        if not norm_platform:
            raise ValueError(
                f"CLARIFICATION_REQUIRED: Cannot determine recipient or messaging platform for '{raw_to}'. "
                "Do NOT guess — ask the user to whom and on which platform (WhatsApp or Telegram) to send the message."
            )

    # 8. Platform is known: decide whether 'candidate' is a direct address or a contact name
    if norm_platform == "whatsapp":
        if not candidate:
            raise ValueError(
                "CLARIFICATION_REQUIRED: Missing recipient for WhatsApp. "
                "Do NOT guess — ask the user to whom the WhatsApp message should be sent."
            )

        if not explicit_contact and _looks_like_phone(candidate):
            return ResolvedTarget(platform="whatsapp", recipient=candidate)

        res = _lookup_contact_for_platform(candidate, "whatsapp")
        if res:
            c_obj = res.get("contact") or {}
            return ResolvedTarget(
                platform="whatsapp",
                recipient=str(res["address"]).strip(),
                contact_name=c_obj.get("display_name") or candidate,
                field_type=res.get("field_type"),
            )

        existing = _find_contact_any(candidate)
        if existing:
            if any(_is_seed_placeholder_phone(str(f.get("value", ""))) for f in (existing.get("fields") or [])):
                raise ValueError(
                    f"SAFETY BLOCK: Contact '{existing.get('display_name', candidate)}' only has the dummy example number '3331234567'. "
                    "Do NOT send to dummy numbers — ask the user for a real recipient or group."
                )
            raise ValueError(
                f"CLARIFICATION_REQUIRED: Contact '{existing.get('display_name', candidate)}' exists in Contacts "
                "but has no phone or WhatsApp number saved. Ask the user for their number or whether to use Telegram."
            )

        raise ValueError(
            f"CLARIFICATION_REQUIRED: Contact or WhatsApp group '{candidate}' was not found. "
            "Ask the user for the phone number or register the group under WhatsApp Groups in Messenger settings."
        )

    # Telegram fallback
    if norm_platform == "telegram":
        if not candidate:
            return ResolvedTarget(platform="telegram", recipient="", bot_name=extracted_bot)

        if not explicit_contact and (candidate.startswith("@") or _NUMERIC_ID_RE.match(candidate)):
            return ResolvedTarget(platform="telegram", recipient=candidate, bot_name=extracted_bot)

        res = _lookup_contact_for_platform(candidate, "telegram")
        if res:
            c_obj = res.get("contact") or {}
            return ResolvedTarget(
                platform="telegram",
                recipient=str(res["address"]).strip(),
                contact_name=c_obj.get("display_name") or candidate,
                bot_name=extracted_bot,
                field_type=res.get("field_type"),
            )

        existing = _find_contact_any(candidate)
        if existing:
            raise ValueError(
                f"CLARIFICATION_REQUIRED: Contact '{existing.get('display_name', candidate)}' exists in Contacts "
                "but has no Telegram ID or @username saved. Ask the user for their Telegram ID (via `/id`) or whether to use WhatsApp."
            )

        raise ValueError(
            f"CLARIFICATION_REQUIRED: Contact or Telegram group '{candidate}' was not found. "
            "NEVER guess or fall back to 'admin' — ask the user for the recipient's Telegram @username / Chat ID or group name."
        )

    raise ValueError(f"CLARIFICATION_REQUIRED: Could not resolve '{raw_to}'.")
