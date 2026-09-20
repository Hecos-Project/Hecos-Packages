"""
MODULE: Templates Store
DESCRIPTION: Persistent CRUD layer for message templates (email, whatsapp, telegram, discord).
             Templates are stored in hecos/data/templates.json.
             Each template keeps a full version history (last N snapshots).

Public API
──────────
  list_templates(channel)          → list[dict]
  get_template(template_id)        → dict | None
  save_template(data)              → dict          (upsert — creates or updates)
  delete_template(template_id)     → bool
  render_template(template_id, variables)  → dict  {subject, body_html, body_text}
  get_version_history(template_id) → list[dict]
  restore_version(template_id, version_index) → dict
  import_templates(templates, mode) → int
"""

from __future__ import annotations

import json
import os
import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional

# Optional: use cssutils or premailer for production-grade inlining.
# We ship a lightweight self-contained inliner so there are no extra deps.
try:
    import premailer as _premailer  # type: ignore
    _HAS_PREMAILER = True
except ImportError:
    _HAS_PREMAILER = False

from hecos.core.logging import logger

# ── Constants ──────────────────────────────────────────────────────────────────

# Path to the JSON store. Resolved at import time so it works from any CWD.
from hecos.core.system.module_state import _BASE_DIR
_DATA_DIR = os.path.join(_BASE_DIR, "data")
_STORE    = os.path.join(_DATA_DIR, "templates.json")

# How many past snapshots to keep per template
MAX_VERSIONS = 20

# Valid channel identifiers
VALID_CHANNELS = {"email", "whatsapp", "telegram", "discord", "document"}


# ── Internal helpers ───────────────────────────────────────────────────────────

def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict:
    """Load the full templates store from disk. Returns {} on missing/invalid file.
    
    On first run (no DB): seeds the DB from all JSON files in default_templates/.
    On subsequent runs: loads the DB and transparently merges any NEW default templates
    whose ID is not yet in the DB, so additions to default_templates/ are picked up
    automatically without wiping user-customized data.
    """
    import glob as _glob

    default_tpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "default_templates")

    def _load_defaults() -> dict:
        """Load all default template files from the directory."""
        defaults = {}
        if not os.path.exists(default_tpl_dir):
            return defaults
        for filepath in _glob.glob(os.path.join(default_tpl_dir, "*.json")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    tpl = json.load(f)
                if "id" in tpl:
                    defaults[tpl["id"]] = tpl
            except Exception as e:
                logger.warning(f"[TEMPLATES] Failed to load default {filepath}: {e}")
        return defaults

    if not os.path.exists(_STORE):
        # Fresh install: seed the DB from all default files
        data = _load_defaults()
        if data:
            _save(data)
        return data

    # DB exists: load it
    try:
        with open(_STORE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"[TEMPLATES] Could not read store: {e}")
        return {}

    # Merge any new default templates whose ID is not yet in the DB
    defaults = _load_defaults()
    added = [tpl_id for tpl_id, tpl in defaults.items() if tpl_id not in data]
    if added:
        for tpl_id in added:
            data[tpl_id] = defaults[tpl_id]
        logger.info(f"[TEMPLATES] Auto-merged {len(added)} new default template(s): {added}")
        _save(data)

    return data



def _save(data: dict) -> bool:
    """Persist the full templates store to disk."""
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_STORE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"[TEMPLATES] Could not write store: {e}")
        return False


def _snapshot(template: dict) -> dict:
    """Create a lightweight version snapshot from a template dict (excludes history)."""
    snap = {k: v for k, v in template.items() if k != "versions"}
    snap["snapshot_at"] = _now_iso()
    return snap


def _push_version(template: dict) -> None:
    """Append the current state of the template to its version history (in-place)."""
    if "versions" not in template:
        template["versions"] = []
    template["versions"].append(_snapshot(template))
    # Trim to MAX_VERSIONS, keeping the most recent ones
    if len(template["versions"]) > MAX_VERSIONS:
        template["versions"] = template["versions"][-MAX_VERSIONS:]


def _extract_variables(text: str) -> list[str]:
    """Extract all {{ var_name }} placeholders from a string, preserving order."""
    found = re.findall(r"\{\{\s*(\w+)\s*\}\}", text or "")
    seen: set[str] = set()
    result: list[str] = []
    for v in found:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


def _interpolate(text: str, variables: dict) -> str:
    """Replace {{ key }} placeholders with values from the variables dict."""
    if not text:
        return text

    def _replace(match: re.Match) -> str:
        key = match.group(1).strip()
        return str(variables.get(key, match.group(0)))  # leave placeholder if key missing

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", _replace, text)


def _inline_css(html: str, css: str) -> str:
    """
    Inline CSS rules into HTML elements' style attributes.

    Strategy (two-pass):
    1. If premailer is available, use it (handles all CSS).
    2. Otherwise fall back to our own lightweight inliner that handles
       the most critical email-breaking property: img width/height.

    The fallback is intentionally narrow but solves the #1 problem reported:
    GrapeJS saves  `img.gjs-... { width: 100px; }` in body_text but email
    clients strip the <style> block, so the image reverts to natural size.
    We parse those img rules and add `width` / `height` as HTML attributes
    AND as inline style on every matching <img>.
    """
    if not html or not css:
        return html

    # ── Option A: premailer (full CSS inlining) ──────────────────────────────
    if _HAS_PREMAILER:
        try:
            full = f"<html><head><style>{css}</style></head><body>{html}</body></html>"
            inlined = _premailer.transform(full, remove_classes=False)
            # Extract just the <body> content
            m = re.search(r"<body[^>]*>(.*?)</body>", inlined, re.DOTALL | re.IGNORECASE)
            return m.group(1).strip() if m else html
        except Exception:
            pass  # fall through to Option B

    # ── Option B: lightweight inliner for img width / height ────────────────
    # Parse  img.classname { width: Xpx; height: Ypx; ... }  from GrapeJS CSS
    rule_pat = re.compile(
        r'img(?:\.[\w-]+)?\s*\{([^}]*)\}',
        re.DOTALL | re.IGNORECASE
    )
    # Also catch generic: .classname img { ... }  or just img { ... }
    generic_pat = re.compile(
        r'(?:\.[\w-]+\s+)?img\s*\{([^}]*)\}',
        re.DOTALL | re.IGNORECASE
    )

    def _extract_dim(declarations: str, prop: str) -> str | None:
        m = re.search(rf'\b{prop}\s*:\s*([^;]+);?', declarations, re.IGNORECASE)
        return m.group(1).strip() if m else None

    # Collect all img rules
    img_rules: list[str] = []
    for pat in (rule_pat, generic_pat):
        for m in pat.finditer(css):
            img_rules.append(m.group(1))

    if not img_rules:
        return html

    # Merge all declarations (last wins)
    merged: dict[str, str] = {}
    for decl_block in img_rules:
        for decl in decl_block.split(';'):
            decl = decl.strip()
            if ':' in decl:
                prop, val = decl.split(':', 1)
                merged[prop.strip().lower()] = val.strip()

    if not merged:
        return html

    # Build the extra inline style fragment we want to inject
    inline_extra = '; '.join(f"{p}: {v}" for p, v in merged.items())

    def _patch_img(m: re.Match) -> str:
        tag = m.group(0)
        # Merge into existing style="..."
        existing = re.search(r'style=["\']([^"\']*)["\']', tag)
        if existing:
            combined = existing.group(1).rstrip(';') + '; ' + inline_extra
            tag = tag[:existing.start()] + f'style="{combined}"' + tag[existing.end():]
        else:
            tag = tag.rstrip('>').rstrip('/') + f' style="{inline_extra}">'
        # Also set HTML width/height attributes for legacy clients
        if 'width' in merged:
            w = re.sub(r'[^\d]', '', merged['width'])  # extract digits
            if w and not re.search(r'\bwidth=', tag):
                tag = tag.rstrip('>').rstrip('/') + f' width="{w}">'
        if 'height' in merged:
            h = re.sub(r'[^\d]', '', merged['height'])
            if h and not re.search(r'\bheight=', tag):
                tag = tag.rstrip('>').rstrip('/') + f' height="{h}">'
        return tag

    return re.sub(r'<img\b[^>]*>', _patch_img, html)


# ── Public API ─────────────────────────────────────────────────────────────────


def list_templates(channel: Optional[str] = None) -> list[dict]:
    """
    Return all templates, optionally filtered by channel.

    :param channel: One of 'email', 'whatsapp', 'telegram', 'discord'.
                    If None, returns every template.
    :returns: List of template dicts, sorted by updated_at descending.
              Version history is excluded from list results (use get_template for full details).
    """
    store = _load()
    result = []
    for tpl in store.values():
        if channel and tpl.get("channel") != channel:
            continue
        # Strip version history from list payload (keep it lightweight)
        clean = {k: v for k, v in tpl.items() if k != "versions"}
        result.append(clean)
    result.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
    return result


def get_template(template_id: str) -> Optional[dict]:
    """
    Return a single template by ID (full record including version history).

    :param template_id: The template UUID string.
    :returns: Template dict or None if not found.
    """
    store = _load()
    return store.get(template_id)


def save_template(data: dict) -> dict:
    """
    Create or update a template (upsert).

    If *data* contains an 'id' that matches an existing template, the existing
    record is updated and the old state is pushed to version history.
    If there is no 'id' (or the id doesn't match), a new template is created.

    Required fields: name, channel.
    Optional fields: subject (email only), body_html (email only), body_text,
                     description, tags.

    :param data: Template data dict.
    :returns: The saved template dict (without version history for brevity).
    :raises ValueError: If channel is invalid.
    """
    channel = data.get("channel", "")
    if channel not in VALID_CHANNELS:
        raise ValueError(f"Invalid channel '{channel}'. Must be one of: {', '.join(sorted(VALID_CHANNELS))}")

    if not data.get("name", "").strip():
        raise ValueError("Template 'name' is required.")

    store = _load()
    existing_id = data.get("id", "").strip()
    is_default = bool(data.get("is_default", False))

    # Enforce uniqueness per channel if this one is default
    if is_default:
        for tpl in store.values():
            if tpl.get("channel") == channel and tpl.get("id") != existing_id:
                tpl["is_default"] = False

    if existing_id and existing_id in store:
        # ── Update existing ──────────────────────────────────────────────────
        existing = store[existing_id]
        _push_version(existing)                          # snapshot before overwrite

        existing["name"]        = data.get("name",        existing["name"])
        existing["channel"]     = channel
        existing["description"] = data.get("description", existing.get("description", ""))
        existing["subject"]     = data.get("subject",     existing.get("subject", ""))
        existing["body_html"]   = data.get("body_html",   existing.get("body_html", ""))
        existing["body_text"]   = data.get("body_text",   existing.get("body_text", ""))
        existing["header"]      = data.get("header",      existing.get("header", ""))
        existing["footer"]      = data.get("footer",      existing.get("footer", ""))
        existing["tags"]        = data.get("tags",        existing.get("tags", []))
        existing["is_default"]  = is_default
        existing["updated_at"]  = _now_iso()

        # Re-derive variable list from current body fields
        all_text = " ".join([
            existing.get("subject", ""),
            existing.get("body_html", ""),
            existing.get("body_text", ""),
        ])
        existing["variables"] = _extract_variables(all_text)

        _save(store)
        logger.info(f"[TEMPLATES] Updated template '{existing_id}' (v{len(existing.get('versions', []))})")
        return {k: v for k, v in existing.items() if k != "versions"}

    else:
        # ── Create new ───────────────────────────────────────────────────────
        new_id = str(uuid.uuid4())
        now    = _now_iso()

        all_text = " ".join([
            data.get("subject", ""),
            data.get("body_html", ""),
            data.get("body_text", ""),
        ])

        template: dict = {
            "id":          new_id,
            "name":        data["name"].strip(),
            "channel":     channel,
            "description": data.get("description", ""),
            "subject":     data.get("subject", ""),
            "body_html":   data.get("body_html", ""),
            "body_text":   data.get("body_text", ""),
            "header":      data.get("header", ""),
            "footer":      data.get("footer", ""),
            "tags":        data.get("tags", []),
            "is_default":  is_default,
            "variables":   _extract_variables(all_text),
            "created_at":  now,
            "updated_at":  now,
            "versions":    [],
        }
        store[new_id] = template
        _save(store)
        logger.info(f"[TEMPLATES] Created template '{new_id}' ({channel})")
        return {k: v for k, v in template.items() if k != "versions"}


def import_templates(templates: list[dict], mode: str = "restore") -> int:
    """
    Import a list of templates.
    mode="restore": Keeps the original UUID. Overwrites existing templates with the same UUID.
                    Ideal for automated backups.
    mode="duplicate": Generates new UUIDs and appends " (Imported)" to the name.
                      Ideal for sharing templates manually without risking overwrites.
    
    :param templates: List of template dictionaries.
    :param mode: 'restore' or 'duplicate'
    :returns: Number of templates successfully imported.
    """
    if not templates:
        return 0

    count = 0
    for data in templates:
        tpl_data = deepcopy(data)
        
        if mode == "duplicate":
            # Remove ID to force creation of a new UUID
            tpl_data.pop("id", None)
            
            # Append suffix if not already present
            name = tpl_data.get("name", "Imported Template").strip()
            if not name.endswith("(Imported)"):
                tpl_data["name"] = f"{name} (Imported)"
                
            # Prevent changing the default template unintentionally
            tpl_data["is_default"] = False
            
        try:
            save_template(tpl_data)
            count += 1
        except Exception as e:
            logger.error(f"[TEMPLATES] Failed to import template '{tpl_data.get('name', 'Unknown')}': {e}")
            
    return count


def delete_template(template_id: str) -> bool:
    """
    Permanently delete a template.

    :param template_id: The template UUID string.
    :returns: True if deleted, False if not found.
    """
    store = _load()
    if template_id not in store:
        return False
    name = store[template_id].get("name", template_id)
    del store[template_id]
    _save(store)
    logger.info(f"[TEMPLATES] Deleted template '{template_id}' ({name})")
    return True


def render_template(template_id: str, variables: dict) -> dict:
    """
    Interpolate variables into a template and return the ready-to-send content.

    :param template_id: The template UUID string.
    :param variables:   Dict of variable values, e.g. {"nome": "Mario", "prodotto": "Hecos"}.
    :returns: Dict with keys: subject, body_html, body_text.
    :raises KeyError: If template_id is not found.
    """
    tpl = get_template(template_id)
    if tpl is None:
        raise KeyError(f"Template '{template_id}' not found.")

    body_html = _interpolate(tpl.get("body_html", ""), variables)
    body_text = _interpolate(tpl.get("body_text", ""), variables)

    # For email templates, GrapeJS stores pure CSS in body_text.
    # STEP 1: Inline critical CSS properties (especially img size) directly
    #         into element style="" attributes so Gmail/Outlook can't strip them.
    if tpl.get("channel") == "email" and body_html and body_text:
        body_html = _inline_css(body_html, body_text)

    # STEP 2: Wrap in a full HTML document (keeps <style> as fallback for
    #         clients that DO support it, and ensures correct rendering overall).
    if tpl.get("channel") == "email" and body_html:
        style_block = f"<style>\n{body_text}\n</style>" if body_text else ""
        body_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{style_block}
</head>
<body style="margin: 0; padding: 0;">
{body_html}
</body>
</html>"""

    return {
        "subject":   _interpolate(tpl.get("subject",   ""), variables),
        "body_html": body_html,
        "body_text": body_text,
        # Header and footer are static: NOT interpolated — intentional feature
        "header":    tpl.get("header", ""),
        "footer":    tpl.get("footer", ""),
    }


def get_version_history(template_id: str) -> list[dict]:
    """
    Return the version history (snapshots) of a template, most-recent first.

    :param template_id: The template UUID string.
    :returns: List of version snapshot dicts.
    :raises KeyError: If template_id is not found.
    """
    tpl = get_template(template_id)
    if tpl is None:
        raise KeyError(f"Template '{template_id}' not found.")
    history = tpl.get("versions", [])
    return list(reversed(history))  # most recent first


def restore_version(template_id: str, version_index: int) -> dict:
    """
    Restore a template to a specific version (by position in history, 0 = most recent).

    The current state is pushed to history before restoring, so nothing is lost.

    :param template_id:    The template UUID string.
    :param version_index:  0-based index into get_version_history() result.
    :returns: The newly restored template dict (without version history).
    :raises KeyError:   If template_id is not found.
    :raises IndexError: If version_index is out of range.
    """
    store = _load()
    if template_id not in store:
        raise KeyError(f"Template '{template_id}' not found.")

    existing = store[template_id]
    history  = list(reversed(existing.get("versions", [])))  # most recent first

    if version_index < 0 or version_index >= len(history):
        raise IndexError(f"Version index {version_index} out of range (0–{len(history)-1}).")

    target_snapshot = history[version_index]

    # Push current state before overwriting
    _push_version(existing)

    # Restore snapshot fields
    for field in ("name", "channel", "description", "subject",
                  "body_html", "body_text", "header", "footer", "tags", "is_default", "variables"):
        if field in target_snapshot:
            existing[field] = target_snapshot[field]

    existing["updated_at"] = _now_iso()
    _save(store)

    logger.info(f"[TEMPLATES] Restored template '{template_id}' to version #{version_index}")
    return {k: v for k, v in existing.items() if k != "versions"}
