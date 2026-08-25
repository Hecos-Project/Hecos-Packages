from pathlib import Path
from flask import Blueprint, send_from_directory
from hecos.hpm.contacts.api import contacts_bp

_STATIC_DIR = Path(__file__).parent / "static"

# Static assets blueprint (serves /ext/contacts/static/*)
contacts_static_bp = Blueprint("contacts_static", __name__)

@contacts_static_bp.route("/ext/contacts/static/<path:filename>")
def contacts_static(filename):
    return send_from_directory(_STATIC_DIR, filename)


def init_plugin_routes(app, cfg_mgr, hecos_root, log):
    if "contacts" not in app.blueprints:
        app.register_blueprint(contacts_bp)
        log.debug("CONTACTS", "API blueprint registered at /api/contacts")
    if "contacts_static" not in app.blueprints:
        app.register_blueprint(contacts_static_bp)
        log.debug("CONTACTS", "Static assets registered at /ext/contacts/static/")
