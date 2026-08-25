"""
MODULE: Contacts API
DESCRIPTION: Flask REST endpoints for the Contacts plugin.
             Registered at boot via on_load() in main.py.

Endpoints:
    GET    /api/contacts                    list / search
    POST   /api/contacts                    create
    GET    /api/contacts/<id>               single contact + fields
    PUT    /api/contacts/<id>               update
    DELETE /api/contacts/<id>               delete
    POST   /api/contacts/<id>/fields        add multi-value field
    DELETE /api/contacts/<id>/fields/<fid>  remove field
    GET    /api/contacts/<id>/export.vcf    export vCard
    POST   /api/contacts/import             import .vcf
    GET    /api/contacts/birthdays          contacts with upcoming birthdays
"""

from flask import Blueprint, request, jsonify, Response, send_file
from hecos.core.logging import logger
import os, pathlib, uuid as _uuid

contacts_bp = Blueprint("contacts", __name__, url_prefix="/api/contacts")


# ── Contact CRUD ───────────────────────────────────────────────────────────────

@contacts_bp.route("", methods=["GET"])
def list_contacts():
    from hecos.hpm.contacts import store
    q     = request.args.get("q")
    tag   = request.args.get("tag")
    limit = int(request.args.get("limit", 100))
    try:
        if q:
            contacts = store.search(q)
        else:
            contacts = store.list_all(tag=tag, limit=limit)
        return jsonify({"ok": True, "contacts": contacts, "count": len(contacts)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@contacts_bp.route("", methods=["POST"])
def create_contact():
    from hecos.hpm.contacts import store
    data = request.get_json(force=True) or {}
    try:
        first = data.get("first_name", "")
        if not first:
            return jsonify({"ok": False, "error": "first_name is required"}), 400
        c = store.add(
            first_name=first,
            last_name=data.get("last_name"),
            display_name=data.get("display_name"),
            company=data.get("company"),
            role=data.get("role"),
            birthday=data.get("birthday"),
            address=data.get("address"),
            notes=data.get("notes"),
            label_color=data.get("label_color"),
            tags=data.get("tags"),
        )
        # Add phone/email fields if provided
        for ph in data.get("phones", []):
            store.add_field(c["id"], "phone", ph["value"], label=ph.get("label", "mobile"),
                            is_primary=ph.get("is_primary", False))
        for em in data.get("emails", []):
            store.add_field(c["id"], "email", em["value"], label=em.get("label", "personal"),
                            is_primary=em.get("is_primary", False))
        for cu in data.get("customs", []):
            store.add_field(c["id"], cu.get("field_type", "custom"), cu["value"], label=cu.get("label"))
        for addr in data.get("addresses", []):
            store.add_field(c["id"], "address", addr["value"], label=addr.get("label", "Main"),
                            is_primary=addr.get("is_primary", False))
        return jsonify({"ok": True, "contact": store.get_by_id(c["id"])}), 201
    except Exception as e:
        logger.debug("CONTACTS", f"POST /api/contacts error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@contacts_bp.route("/<contact_id>", methods=["GET"])
def get_contact(contact_id):
    from hecos.hpm.contacts import store
    c = store.get_by_id(contact_id)
    if not c:
        return jsonify({"ok": False, "error": "Contact not found"}), 404
    return jsonify({"ok": True, "contact": c})


@contacts_bp.route("/<contact_id>", methods=["PUT"])
def update_contact(contact_id):
    from hecos.hpm.contacts import store
    data = request.get_json(force=True) or {}
    allowed = {"display_name", "first_name", "last_name", "company", "role",
               "birthday", "address", "notes", "label_color", "tags", "photo_path"}
    fields = {k: v for k, v in data.items() if k in allowed}
    try:
        updated = store.update(contact_id, **fields)

        # Sync multi-value fields if present in payload
        if any(k in data for k in ["phones", "emails", "socials"]):
            c = store.get_by_id(contact_id)
            if c:
                # remove existing fields of these types
                for f in c.get("fields", []):
                    ft = f["field_type"]
                    if ("phones" in data and ft == "phone") or \
                       ("emails" in data and ft == "email") or \
                       ("addresses" in data and ft == "address") or \
                       ("customs" in data and ft not in ["phone", "email", "address", "photo"]):
                        store.remove_field(f["id"])
                
                # add new fields
                if "phones" in data:
                    for ph in data["phones"]:
                        if ph.get("value"):
                            store.add_field(contact_id, "phone", ph["value"], label=ph.get("label", "mobile"), is_primary=ph.get("is_primary", False))
                if "emails" in data:
                    for em in data["emails"]:
                        if em.get("value"):
                            store.add_field(contact_id, "email", em["value"], label=em.get("label", "personal"), is_primary=em.get("is_primary", False))
                if "customs" in data:
                    for cu in data["customs"]:
                        if cu.get("field_type") and cu.get("value"):
                            store.add_field(contact_id, cu["field_type"], cu["value"], label=cu.get("label"))
                if "addresses" in data:
                    for addr in data["addresses"]:
                        if addr.get("value"):
                            store.add_field(contact_id, "address", addr["value"], label=addr.get("label", "Main"), is_primary=addr.get("is_primary", False))
                            
            updated = True # Ensure we return success if only fields changed

        if updated:
            return jsonify({"ok": True, "contact": store.get_by_id(contact_id)})
        return jsonify({"ok": False, "error": "Contact not found or no changes"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@contacts_bp.route("/<contact_id>", methods=["DELETE"])
def delete_contact(contact_id):
    from hecos.hpm.contacts import store
    deleted = store.delete(contact_id)
    if deleted:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Contact not found"}), 404



# ── Photo Upload ───────────────────────────────────────────────────────────────

_PHOTOS_DIR = pathlib.Path(__file__).parent.parent.parent / "memory" / "contact_photos"
_ALLOWED_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif'}


@contacts_bp.route("/<contact_id>/photo", methods=["POST"])
def upload_photo(contact_id):
    from hecos.hpm.contacts import store
    c = store.get_by_id(contact_id)
    if not c:
        return jsonify({"ok": False, "error": "Contact not found"}), 404

    if "photo" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded (field: 'photo')"}), 400

    f   = request.files["photo"]
    ext = pathlib.Path(f.filename).suffix.lower()
    if ext not in _ALLOWED_EXT:
        return jsonify({"ok": False, "error": f"Unsupported image format: {ext}"}), 400

    _PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    # Remove old photo if present
    old = c.get("photo_path")
    if old:
        old_path = _PHOTOS_DIR / pathlib.Path(old).name
        try:
            old_path.unlink(missing_ok=True)
        except Exception:
            pass

    filename = f"{contact_id}{ext}"
    dest     = _PHOTOS_DIR / filename
    f.save(str(dest))

    photo_url = f"/api/contacts/{contact_id}/photo"
    store.update(contact_id, photo_path=filename, photo_url=photo_url)
    return jsonify({"ok": True, "photo_url": photo_url})


@contacts_bp.route("/<contact_id>/photo", methods=["GET"])
def get_photo(contact_id):
    from hecos.hpm.contacts import store
    c = store.get_by_id(contact_id)
    if not c or not c.get("photo_path"):
        return jsonify({"ok": False, "error": "No photo"}), 404
    path = _PHOTOS_DIR / pathlib.Path(c["photo_path"]).name
    if not path.exists():
        return jsonify({"ok": False, "error": "File missing"}), 404
    return send_file(str(path))


# ── Gallery ────────────────────────────────────────────────────────────────────

@contacts_bp.route("/<contact_id>/gallery", methods=["POST"])
def upload_gallery_photo(contact_id):
    import uuid
    from hecos.hpm.contacts import store
    c = store.get_by_id(contact_id)
    if not c:
        return jsonify({"ok": False, "error": "Contact not found"}), 404

    if "photo" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded (field: 'photo')"}), 400

    f = request.files["photo"]
    ext = pathlib.Path(f.filename).suffix.lower()
    if ext not in _ALLOWED_EXT:
        return jsonify({"ok": False, "error": f"Unsupported image format: {ext}"}), 400

    _PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{contact_id}_gal_{uuid.uuid4().hex[:8]}{ext}"
    dest = _PHOTOS_DIR / filename
    f.save(str(dest))

    field = store.add_field(contact_id, "photo", filename, label="gallery")
    return jsonify({"ok": True, "field": field})


@contacts_bp.route("/<contact_id>/gallery/<filename>", methods=["GET"])
def get_gallery_photo(contact_id, filename):
    import re
    # Basic security check
    if not re.match(r'^[\w\-\.]+$', filename):
        return jsonify({"ok": False, "error": "Invalid filename"}), 400
        
    path = _PHOTOS_DIR / filename
    if not path.exists():
        return jsonify({"ok": False, "error": "File missing"}), 404
    return send_file(str(path))


@contacts_bp.route("/<contact_id>/gallery/<field_id>", methods=["DELETE"])
def delete_gallery_photo(contact_id, field_id):
    from hecos.hpm.contacts import store
    c = store.get_by_id(contact_id)
    if not c:
        return jsonify({"ok": False, "error": "Contact not found"}), 404

    fields = c.get("fields", [])
    target = next((f for f in fields if f["id"] == field_id and f["field_type"] == "photo"), None)
    
    if not target:
        return jsonify({"ok": False, "error": "Photo not found in gallery"}), 404

    # Remove the physical file
    path = _PHOTOS_DIR / target["value"]
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass

    # Remove the field entry
    store.remove_field(field_id)
    return jsonify({"ok": True})


# ── Multi-value Fields ─────────────────────────────────────────────────────────

@contacts_bp.route("/<contact_id>/fields", methods=["POST"])
def add_field(contact_id):
    from hecos.hpm.contacts import store
    data = request.get_json(force=True) or {}
    ft  = data.get("field_type")
    val = data.get("value")
    if not ft or not val:
        return jsonify({"ok": False, "error": "field_type and value are required"}), 400
    try:
        f = store.add_field(contact_id, ft, val,
                            label=data.get("label"),
                            is_primary=data.get("is_primary", False))
        return jsonify({"ok": True, "field": f}), 201
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@contacts_bp.route("/<contact_id>/fields/<field_id>", methods=["DELETE"])
def remove_field(contact_id, field_id):
    from hecos.hpm.contacts import store
    removed = store.remove_field(field_id)
    if removed:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Field not found"}), 404


# ── vCard ──────────────────────────────────────────────────────────────────────

@contacts_bp.route("/<contact_id>/export.vcf", methods=["GET"])
def export_vcard(contact_id):
    from hecos.hpm.contacts import store
    vcf = store.export_vcard(contact_id)
    if not vcf:
        return jsonify({"ok": False, "error": "Contact not found"}), 404
    c = store.get_by_id(contact_id)
    filename = f"{c.get('display_name','contact').replace(' ','_')}.vcf"
    return Response(
        vcf,
        mimetype="text/vcard",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@contacts_bp.route("/import", methods=["POST"])
def import_contacts():
    """
    Universal import endpoint. Accepts:
    - vCard (.vcf) file upload  →  field 'file' with content-type text/vcard
    - CSV file upload           →  field 'file' with .csv extension
    - JSON body                 →  { "contacts": [...] } or raw list
    - Raw vcf text body
    Query params:
      ?mode=duplicate (default) | replace
    """
    from hecos.hpm.contacts import store
    mode = request.args.get("mode", "duplicate")
    try:
        raw_bytes = None
        filename = ""

        if "file" in request.files:
            f = request.files["file"]
            filename = (f.filename or "").lower()
            raw_bytes = f.read()
        
        # --- CSV import ---
        if filename.endswith(".csv") or request.content_type == "text/csv":
            import csv, io
            text = raw_bytes.decode("utf-8-sig", errors="replace") if raw_bytes else request.get_data(as_text=True)
            reader = csv.DictReader(io.StringIO(text))
            # Auto-detect column names case-insensitively
            imported = []
            for row in reader:
                row_low = {k.lower().strip(): v.strip() for k, v in row.items() if v}
                # Find email column
                email_val = (row_low.get("email") or row_low.get("e-mail") or
                             row_low.get("email address") or row_low.get("mail") or "")
                first = (row_low.get("first name") or row_low.get("first_name") or
                         row_low.get("nome") or row_low.get("name") or
                         row_low.get("display_name") or row_low.get("full name") or
                         email_val.split("@")[0] or "Contact")
                last  = (row_low.get("last name") or row_low.get("last_name") or
                         row_low.get("cognome") or "")
                c = store.add(
                    first_name=first, last_name=last or None,
                    company=row_low.get("company") or row_low.get("azienda") or None,
                    role=row_low.get("role") or row_low.get("title") or None,
                    notes=row_low.get("notes") or row_low.get("note") or None,
                    tags=row_low.get("tags") or row_low.get("tag") or None,
                    label_color=row_low.get("color") or row_low.get("label_color") or None,
                )
                if email_val:
                    store.add_field(c["id"], "email", email_val, label="work", is_primary=True)
                phone_val = row_low.get("phone") or row_low.get("telefono") or row_low.get("mobile") or ""
                if phone_val:
                    store.add_field(c["id"], "phone", phone_val, label="mobile", is_primary=True)
                imported.append(c)
            return jsonify({"ok": True, "imported": len(imported), "contacts": imported}), 201

        # --- JSON import ---
        json_data = None
        if raw_bytes and (filename.endswith(".json") or request.content_type == "application/json"):
            import json as _json
            json_data = _json.loads(raw_bytes.decode("utf-8", errors="replace"))
        elif not raw_bytes:
            json_data = request.get_json(force=True, silent=True)
        
        if json_data is not None:
            contacts_list = json_data if isinstance(json_data, list) else json_data.get("contacts", [])
            count = store.import_full_backup(contacts_list, mode=mode)
            return jsonify({"ok": True, "imported": count}), 201

        # --- vCard fallback ---
        raw = raw_bytes.decode("utf-8", errors="replace") if raw_bytes else request.get_data(as_text=True)
        if not raw:
            return jsonify({"ok": False, "error": "No data provided. Send a CSV/JSON/vCard file."}), 400
        created = store.import_vcard(raw)
        return jsonify({"ok": True, "imported": len(created), "contacts": created}), 201

    except Exception as e:
        logger.debug("CONTACTS", f"POST /api/contacts/import error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@contacts_bp.route("/export", methods=["GET"])
def export_contacts():
    """
    Export all contacts.
    ?format=json (default) | csv
    ?tag=... (filter by tag)
    """
    from hecos.hpm.contacts import store
    fmt = request.args.get("format", "json").lower()
    tag = request.args.get("tag")
    try:
        contacts = store.list_all(tag=tag, limit=1_000_000)
        if fmt == "csv":
            import csv, io
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["display_name", "first_name", "last_name", "company", "role",
                             "email", "phone", "tags", "notes", "birthday"])
            for c in contacts:
                email = next((f["value"] for f in c.get("fields", []) if f["field_type"] == "email"), "")
                phone = next((f["value"] for f in c.get("fields", []) if f["field_type"] == "phone"), "")
                writer.writerow([c.get("display_name",""), c.get("first_name",""), c.get("last_name",""),
                                 c.get("company",""), c.get("role",""), email, phone,
                                 c.get("tags",""), c.get("notes",""), c.get("birthday","")])
            return Response(buf.getvalue(), mimetype="text/csv",
                            headers={"Content-Disposition": "attachment; filename=contacts.csv"})
        else:
            import json as _json
            return Response(_json.dumps({"contacts": contacts, "count": len(contacts)}, ensure_ascii=False, indent=2),
                            mimetype="application/json",
                            headers={"Content-Disposition": "attachment; filename=contacts.json"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@contacts_bp.route("/emails", methods=["GET"])
def get_emails():
    """
    Fast endpoint for Mail autocomplete and group-send.
    Returns a flat list of {display_name, email} for all contacts with an email field.
    ?q=...  full-text filter
    ?tag=...  filter by tag
    """
    from hecos.hpm.contacts import store
    q   = request.args.get("q", "")
    tag = request.args.get("tag", "")
    try:
        contacts = store.search(q) if q else store.list_all(tag=tag or None, limit=1_000_000)
        result = []
        for c in contacts:
            for f in c.get("fields", []):
                if f["field_type"] == "email":
                    result.append({
                        "id": c["id"],
                        "display_name": c.get("display_name", ""),
                        "email": f["value"],
                        "tags": c.get("tags", ""),
                    })
        return jsonify({"ok": True, "emails": result, "count": len(result)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@contacts_bp.route("/tags", methods=["GET"])
def get_tags():
    """Return all distinct tags used across contacts."""
    from hecos.hpm.contacts import store
    try:
        contacts = store.list_all(limit=1_000_000)
        tags = set()
        for c in contacts:
            for t in (c.get("tags") or "").split(","):
                t = t.strip()
                if t:
                    tags.add(t)
        return jsonify({"ok": True, "tags": sorted(tags)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Birthday helper ────────────────────────────────────────────────────────────

@contacts_bp.route("/birthdays", methods=["GET"])
def birthdays():
    from hecos.hpm.contacts import store
    days = int(request.args.get("days", 7))
    try:
        today  = store.get_birthdays_today()
        upcoming = store.get_birthdays_upcoming(days)
        return jsonify({"ok": True, "today": today, "upcoming": upcoming})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Full Backup/Restore ─────────────────────────────────────────────────────────

@contacts_bp.route("/backup", methods=["GET"])
def contacts_backup():
    """Exports all contacts (with fields) to a JSON backup."""
    from hecos.hpm.contacts import store
    try:
        contacts = store.list_all(limit=1000000)  # get practically all
        return jsonify({
            "ok": True,
            "contacts": contacts,
            "count": len(contacts)
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@contacts_bp.route("/restore", methods=["POST"])
def contacts_restore():
    """
    Restores contacts from a JSON backup.
    Body: { contacts: [...], mode: 'duplicate' | 'replace' }
    """
    from hecos.hpm.contacts import store
    try:
        data = request.get_json(force=True) or {}
        contacts = data.get("contacts", [])
        mode = data.get("mode", "duplicate")

        if not isinstance(contacts, list):
            return jsonify({"ok": False, "error": "Invalid format, expected list of contacts"}), 400

        count = store.import_full_backup(contacts, mode=mode)
        return jsonify({"ok": True, "imported": count}), 201
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
