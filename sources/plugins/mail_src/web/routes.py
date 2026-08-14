from pathlib import Path
from flask import Blueprint, send_from_directory
from hecos.hpm.mail.api import mail_bp

_STATIC_DIR = Path(__file__).parent / "static"

# Static assets blueprint (serves /ext/mail/static/*)
mail_static_bp = Blueprint("mail_static", __name__)

@mail_static_bp.route("/ext/mail/static/<path:filename>")
def mail_static(filename):
    return send_from_directory(_STATIC_DIR, filename)


def init_plugin_routes(app, cfg_mgr, root_dir, logger, get_sm=None):
    if "mail" not in app.blueprints:
        app.register_blueprint(mail_bp)
        logger.info("[MAIL] API blueprint registered at /api/mail via HPM loader")
    if "mail_static" not in app.blueprints:
        app.register_blueprint(mail_static_bp)
        logger.info("[MAIL] Static assets registered at /ext/mail/static/")
