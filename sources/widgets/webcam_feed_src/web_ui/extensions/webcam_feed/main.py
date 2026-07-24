"""
webcam_feed/main.py
─────────────────────────────────────────────────────────────────
Hecos Widget — Webcam Feed
Exposes a static file route for the widget's CSS/JS assets.
The webcam streaming itself is handled entirely in the browser
via the HTML5 WebRTC API (navigator.mediaDevices.getUserMedia).
─────────────────────────────────────────────────────────────────
"""
import os
from flask import send_from_directory


def init_routes(app):
    _static_dir = os.path.join(os.path.dirname(__file__), "static")

    @app.route("/ext/webcam_feed/<path:filename>")
    def webcam_feed_static(filename):
        return send_from_directory(_static_dir, filename)
