"""
Default user-editable AI routing instructions and anti-hallucination guard prompts for Messenger (v2.4).
All strings here serve as transparent defaults for the Messenger configuration panel and TOML config;
the user can inspect, customize, reset, or disable each section from Central Hub -> Messenger.
"""

from __future__ import annotations

from typing import Any


DEFAULT_GENERAL_ROUTING_OVERRIDE = (
    "- NEVER claim, imply, or roleplay that a message, photo, or document was sent unless you actually invoked "
    "`MESSENGER__send_message`, `MESSENGER__send_photo`, or `MESSENGER__send_document` in this exact turn and received a `✅` confirmation.\n"
    "- Write all `text` messages and photo `caption`s strictly in first-person staying true to your active persona/character "
    "(e.g., refer to selfies/portraits as 'my selfie' / 'a photo of me' — NEVER break character by mentioning AI, generation, prompts, or tools).\n"
    "- NEVER use `EXECUTOR` filesystem tools (`write_file`, `create_dir`, `read_file`, `run_aider_task`) to fabricate fake `.jpg`/`.png` image files!\n"
    "- When the user asks to message themselves ('to me', 'my number', 'a me', 'al mio numero'), pass `to='admin'`.\n"
    "- For follow-up requests ('send another one', 'mandane un altro', 'inviane un altro') where no new recipient or platform is named, "
    "OMIT `platform` (and pass `to='last'` or the same contact) so Messenger reuses the verified channel from the last follow-up window; NEVER switch platforms on your own.\n"
    "- If `MESSENGER` returns `CLARIFICATION_REQUIRED`, or if recipient/platform is unknown with no recent context, DO NOT guess: "
    "ask the user ('To whom should I send it, and on which platform — WhatsApp or Telegram?').\n"
    "- Once a message returns `✅` in this turn, DO NOT call `send_message` again with the same text."
)

DEFAULT_WHATSAPP_ROUTING_OVERRIDE = (
    "- Map 'whatsapp', 'wazzap', 'wa', or 'whatsapp web' to `platform='whatsapp'`.\n"
    "- Pass contact names directly in `to` (e.g., `to='Rowena'`, `platform='whatsapp'`) — "
    "Messenger resolves phone numbers from Contacts automatically.\n"
    "- When the user asks to write in a WhatsApp group (e.g. 'sul gruppo WhatsApp di Hecos' / 'gruppo Famiglia su wazzap'), "
    "pass `to='group:<GroupName>'` and `platform='whatsapp'` — NEVER pass `to='admin'` when targeting a group!\n"
    "- Keep multi-line texts, lists, or poems inside a single `text` parameter rather than splitting into multiple calls."
)

DEFAULT_TELEGRAM_ROUTING_OVERRIDE = (
    "- Map 'telegram' or 'tg' to `platform='telegram'`.\n"
    "- Match `bot_name` to the active persona speaking (e.g. `bot_name='Urania'` when speaking as Urania, `bot_name='hecos'` when speaking as Hecos), "
    "or omit `bot_name` so Messenger automatically selects the bot matching your active persona.\n"
    "- When the user asks to write in a Telegram group or channel (e.g. 'sul gruppo di Hecos' / 'gruppo Ecos'), pass `to='group:<GroupName>'` "
    "(e.g. `to='group:Hecos'`, `platform='telegram'`) — NEVER pass `to='admin'` when targeting a group or channel!\n"
    "- To generate and send a selfie/photo on Telegram: first call `IMAGE_GEN__generate_image(prompt='...')`, then in the next step call "
    "`MESSENGER__send_photo(to=..., image_path='latest', platform='telegram', caption='...')` (or pass the `[[IMG:filename]]`).\n"
    "- Use `MESSENGER__send_document` to send PDFs, HTML documents, archives, or files."
)

DEFAULT_ANTI_HALLUCINATION_PROMPT = (
    "[SYSTEM GUARD — MESSENGER]: The user asked you to send a message, photo, or document via Messenger, "
    "but NO `MESSENGER` tool was invoked in this turn — so NOTHING was sent! "
    "Do NOT roleplay or pretend you sent it. If you need to generate a photo first, call `IMAGE_GEN__generate_image` now; "
    "if an image already exists, call `MESSENGER__send_photo(image_path='latest', ...)` now; "
    "for text, call `MESSENGER__send_message` now. If recipient or platform is genuinely unclear, ask the user explicitly."
)


def get_ui_defaults() -> dict[str, Any]:
    """Returns default strings and settings for UI 'Reset to Default' actions."""
    return {
        "remember_last_channel": True,
        "last_channel_ttl_minutes": 15,
        "general_override_enabled": True,
        "general_override": DEFAULT_GENERAL_ROUTING_OVERRIDE,
        "whatsapp_routing_override_enabled": True,
        "whatsapp_routing_override": DEFAULT_WHATSAPP_ROUTING_OVERRIDE,
        "telegram_routing_override_enabled": True,
        "telegram_routing_override": DEFAULT_TELEGRAM_ROUTING_OVERRIDE,
        "telegram_auto_match_persona_bot": True,
        "anti_hallucination_guard_enabled": True,
        "anti_hallucination_prompt": DEFAULT_ANTI_HALLUCINATION_PROMPT,
    }


def compose_routing_override(cfg: Any) -> tuple[bool, str]:
    """
    Composes active General + Platform-specific routing instructions (plus live enabled
    Telegram bots, Telegram groups, and WhatsApp groups) from MessengerConfig into `routing_override.yaml`.
    Returns `(enabled, instruction_text)`.
    """
    blocks: list[str] = []

    if getattr(cfg, "general_override_enabled", True):
        gen_txt = (getattr(cfg, "general_override", "") or "").strip()
        if gen_txt:
            blocks.append(f"[General & Follow-up Continuity]\n{gen_txt}")

    wa_cfg = getattr(cfg, "whatsapp", None)
    if wa_cfg and getattr(wa_cfg, "enabled", False) and getattr(wa_cfg, "routing_override_enabled", True):
        wa_txt = (getattr(wa_cfg, "routing_override", "") or "").strip()
        wa_groups = [
            g for g in (getattr(wa_cfg, "groups", None) or [])
            if getattr(g, "enabled", True) and (getattr(g, "name", "") or getattr(g, "group_title", ""))
        ]
        wa_group_roster = ""
        if wa_groups:
            wg_items = [
                f"'{g.name or g.group_title}' -> pass `to='group:{g.name or g.group_title}'`, `platform='whatsapp'`"
                + (f" (voice aliases: {g.aliases})" if getattr(g, "aliases", "") else "")
                for g in wa_groups
            ]
            wa_group_roster = f"\n- Configured WhatsApp Groups: {'; '.join(wg_items)}."
        if wa_txt or wa_group_roster:
            blocks.append(f"[WhatsApp]\n{wa_txt}{wa_group_roster}".strip())

    tg_cfg = getattr(cfg, "telegram", None)
    if tg_cfg and getattr(tg_cfg, "enabled", False) and getattr(tg_cfg, "routing_override_enabled", True):
        tg_txt = (getattr(tg_cfg, "routing_override", "") or "").strip()
        enabled_bots = [b for b in (getattr(tg_cfg, "bots", None) or []) if getattr(b, "enabled", False) and getattr(b, "name", "")]
        bot_roster = ""
        if enabled_bots:
            roster_items = [
                f"'{b.name}'" + (" [PRIMARY]" if getattr(b, "is_primary", False) else "")
                for b in enabled_bots
            ]
            bot_roster = f"\n- Active configured Telegram bot_name values: {', '.join(roster_items)} (use exact name or omit `bot_name`)."

        enabled_groups = [
            g for g in (getattr(tg_cfg, "groups", None) or [])
            if getattr(g, "enabled", True) and getattr(g, "name", "") and getattr(g, "chat_id", "")
        ]
        group_roster = ""
        if enabled_groups:
            g_items = [
                f"'{g.name}' -> pass `to='group:{g.name}'`, `platform='telegram'`"
                + (f" (voice aliases: {g.aliases})" if getattr(g, "aliases", "") else "")
                for g in enabled_groups
            ]
            group_roster = f"\n- Configured Telegram Groups/Channels: {'; '.join(g_items)}."

        if tg_txt or bot_roster or group_roster:
            blocks.append(f"[Telegram]\n{tg_txt}{bot_roster}{group_roster}".strip())

    if not blocks:
        return False, ""

    return True, "\n\n".join(blocks)
