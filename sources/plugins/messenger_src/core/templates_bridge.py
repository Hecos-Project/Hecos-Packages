"""
Bridge between Hecos Messenger and the HPM Templates library (`hecos.hpm.libraries.templates`).
Supports:
  1. Explicit `template_id` rendering (with `{{ var }}` interpolation)
  2. Provider-specific selected template (`use_template=True` + `template_id`)
  3. Channel Default template (`is_default=True` on `channel == platform` in Templates Manager)
Fails open cleanly if the Templates library is not installed.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from hecos.core.logging import logger


_MSG_PLACEHOLDER_RE = re.compile(r"\{\{\s*(?:message|text|body|content|messaggio|testo)\s*\}\}", re.IGNORECASE)


def _load_templates_store() -> Any:
    """Resolves the Templates store module across HPM library and legacy paths."""
    for mod_path in ("hecos.hpm.libraries.templates.store", "hecos.hpm.templates.store"):
        try:
            import importlib
            return importlib.import_module(mod_path)
        except ImportError:
            continue
    return None


def _interpolate_basic_vars(segment: str, extra_vars: Optional[dict[str, Any]] = None) -> str:
    if not segment or "{{" not in segment:
        return segment
    now = datetime.now()
    ctx: dict[str, Any] = {
        "date": now.strftime("%d/%m/%Y"),
        "time": now.strftime("%H:%M"),
    }
    if extra_vars:
        ctx.update(extra_vars)

    def _repl(m: re.Match) -> str:
        k = m.group(1).strip()
        return str(ctx[k]) if k in ctx and ctx[k] is not None else m.group(0)

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", _repl, segment)


def apply_message_template(
    platform: str,
    text: str,
    provider_cfg: Any = None,
    skip_default_template: bool = False,
    explicit_template_id: str = "",
    template_vars: Optional[dict[str, Any]] = None,
) -> str:
    """
    Applies a Messenger header/footer wrapper (or placeholder body) from the Hecos Templates library:
      - If `explicit_template_id` is passed, uses that template.
      - Else if `provider_cfg.use_template` is True and `provider_cfg.template_id` is set, uses that template.
      - Else if `not skip_default_template`, checks `list_templates(channel=platform)` for `is_default=True`!
    """
    if not text:
        return text

    tpl_store = _load_templates_store()
    if tpl_store is None:
        return text

    if explicit_template_id:
        try:
            rendered = tpl_store.render_template(explicit_template_id, template_vars or {})
            if rendered:
                header = (rendered.get("header") or "").strip()
                footer = (rendered.get("footer") or "").strip()
                body = (rendered.get("body_text") or rendered.get("body_html") or text).strip()
                parts = [p for p in (header, body, footer) if p]
                return "\n\n".join(parts) if parts else text
        except Exception as exc:
            logger.warning("MESSENGER", f"Explicit template render skipped ({explicit_template_id}): {exc}")

    if skip_default_template:
        return text

    cfg_template_id = ""
    if provider_cfg is not None and getattr(provider_cfg, "use_template", False):
        cfg_template_id = (getattr(provider_cfg, "template_id", "") or "").strip()

    try:
        template_to_apply: Optional[dict[str, Any]] = None
        if cfg_template_id:
            template_to_apply = tpl_store.get_template(cfg_template_id)

        # Fall back to the channel's Default template (`is_default=True` in Templates Manager)
        if template_to_apply is None:
            for item in tpl_store.list_templates(channel=platform):
                if item.get("is_default"):
                    template_to_apply = item
                    break

        if not template_to_apply:
            return text

        header = _interpolate_basic_vars((template_to_apply.get("header") or "").strip(), template_vars)
        footer = _interpolate_basic_vars((template_to_apply.get("footer") or "").strip(), template_vars)
        tpl_body = (template_to_apply.get("body_text") or "").strip()

        # Avoid double-wrapping if header/footer is already present in text
        if header and header in text and (not footer or footer in text):
            return text

        core_text = text
        if tpl_body and _MSG_PLACEHOLDER_RE.search(tpl_body):
            core_text = _interpolate_basic_vars(_MSG_PLACEHOLDER_RE.sub(text, tpl_body), template_vars)

        parts = [p for p in (header, core_text, footer) if p]
        if len(parts) > 1 or core_text != text:
            logger.info(
                "MESSENGER",
                f"Applied template '{template_to_apply.get('name', cfg_template_id)}' ({platform}).",
            )
            return "\n\n".join(parts)
    except Exception as exc:
        logger.warning("MESSENGER", f"Error applying message template: {exc}")

    return text
