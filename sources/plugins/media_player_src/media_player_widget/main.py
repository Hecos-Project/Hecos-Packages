"""
Hecos Media Player Widget — Extension Entry Point
Registers static file routes for the media player widget.
"""
import os
from flask import send_from_directory
try:
    from hecos.core.logging import logger
except ImportError:
    class _L:
        def info(self, *a): print("[MEDIA_PLAYER_WIDGET]", *a)
        def warning(self, *a): print("[MEDIA_PLAYER_WIDGET WARN]", *a)
        def debug(self, *a, **kw): pass
    logger = _L()

_STATIC_DIR    = os.path.join(os.path.dirname(__file__), "static")
_TEMPLATE_DIR  = os.path.join(os.path.dirname(__file__), "templates")


def init_routes(app, root_dir: str = None):
    """Register widget static-file routes."""

    if os.path.isdir(_STATIC_DIR):
        @app.route("/media_player_widget_static/<path:filename>")
        def media_player_widget_static(filename):
            return send_from_directory(_STATIC_DIR, filename)

    logger.debug("MediaPlayerWidget", "Media Player Widget routes registered.")
