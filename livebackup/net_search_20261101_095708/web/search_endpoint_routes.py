"""
web/search_endpoint_routes.py
Dedicated Flask API routes for Deep Search endpoints configuration, onion proxying, and Tor Browser integration.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
from flask import request, jsonify, Response
from flask_login import login_required

try:
    from hecos.modules.net_search.search.config import (
        get_search_config,
        update_search_config,
        get_endpoints,
        update_endpoints,
        reset_endpoints_to_defaults,
        launch_tor_browser,
        detect_tor_browser_path,
    )
    from hecos.modules.net_search.search import http_client
except (ImportError, ValueError):
    from ..search.config import (
        get_search_config,
        update_search_config,
        get_endpoints,
        update_endpoints,
        reset_endpoints_to_defaults,
        launch_tor_browser,
        detect_tor_browser_path,
    )
    from ..search import http_client

try:
    from hecos.core.logging import logger as hecos_logger
except (ImportError, ValueError):
    hecos_logger = logging.getLogger("net_search.web.endpoints")


def register_endpoint_routes(app, logger=None):
    """Registers endpoints configuration, onion proxy, and Tor Browser routes on the Flask application."""
    if "api_search_config_get" in app.view_functions:
        return
    log = logger or hecos_logger
    log.info("[DeepSearch] Registering endpoint and Tor Browser routes...")

    # ── Configuration API ─────────────────────────────────────────────────────
    @app.route("/api/hsearch/config", methods=["GET"])
    @login_required
    def api_search_config_get():
        return jsonify({"ok": True, "config": get_search_config()})

    @app.route("/api/hsearch/config", methods=["POST"])
    @login_required
    def api_search_config_post():
        data = request.get_json(force=True) or {}
        ok = update_search_config(data)
        return jsonify({"ok": ok, "config": get_search_config()})

    # ── Search Endpoints & Fallbacks Management API ───────────────────────────
    @app.route("/api/hsearch/endpoints", methods=["GET"])
    @login_required
    def api_search_endpoints_get():
        return jsonify({"ok": True, "endpoints": get_endpoints()})

    @app.route("/api/hsearch/endpoints", methods=["POST"])
    @login_required
    def api_search_endpoints_post():
        data = request.get_json(force=True) or {}
        ok = update_endpoints(data)
        return jsonify({"ok": ok, "endpoints": get_endpoints()})

    @app.route("/api/hsearch/endpoints/reset", methods=["POST"])
    @login_required
    def api_search_endpoints_reset():
        ok = reset_endpoints_to_defaults()
        return jsonify({"ok": ok, "endpoints": get_endpoints()})

    # ── Tor Live Proxy Streamer ───────────────────────────────────────────────
    @app.route("/api/hsearch/onion_proxy", methods=["GET"])
    @login_required
    def api_onion_proxy():
        target_url = request.args.get("url", "").strip()
        if not target_url:
            return jsonify({"ok": False, "error": "Missing URL"}), 400
        if not target_url.startswith("http://") and not target_url.startswith("https://"):
            target_url = "http://" + target_url

        try:
            resp = None
            last_err = None
            # Hidden services require onion descriptor lookup & rendezvous circuit setup.
            # If the first attempt times out, a second attempt usually succeeds as the circuit completes.
            for attempt in (1, 2):
                try:
                    timeout_val = 35.0 if attempt == 1 else 45.0
                    resp = http_client.get(target_url, network="tor", timeout=timeout_val, allow_redirects=True)
                    break
                except Exception as ex:
                    last_err = ex
                    err_str = str(ex).lower()
                    is_timeout = "timeout" in err_str or "timed out" in err_str
                    if is_timeout and attempt == 1:
                        log.info(f"[ONION_PROXY] Circuit creation timed out on attempt 1 for {target_url}. Retrying with 45s...")
                        time.sleep(1.0)
                        continue
                    break

            if resp is None:
                raise last_err or RuntimeError("Failed to connect to hidden service.")

            content_type = resp.headers.get("Content-Type", "text/html; charset=utf-8")

            if "text/html" in content_type.lower():
                raw_html = resp.text
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(raw_html, "html.parser")

                base_target = resp.url or target_url

                # Rewrite sub-resources (img, link, script, source) so Chrome requests them via our proxy
                for tag in soup.find_all(["img", "script", "link", "source", "video", "audio"]):
                    for attr in ["src", "href"]:
                        if tag.has_attr(attr):
                            val = tag[attr].strip()
                            if val and not val.startswith("data:") and not val.startswith("javascript:"):
                                abs_url = urllib.parse.urljoin(base_target, val)
                                tag[attr] = f"/api/hsearch/onion_proxy?url={urllib.parse.quote(abs_url)}"

                # Rewrite <a> tags so clicking navigation stays inside Hecos Tor Viewer
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if href.startswith("javascript:") or href.startswith("#") or href.startswith("mailto:"):
                        continue
                    abs_url = urllib.parse.urljoin(base_target, href)
                    if ".onion" in abs_url:
                        a["href"] = f"/search/viewer?url={urllib.parse.quote(abs_url)}"
                        a["target"] = "_top"

                flask_resp = Response(str(soup), status=resp.status_code, content_type="text/html; charset=utf-8")
                flask_resp.headers["X-Frame-Options"] = "SAMEORIGIN"
                flask_resp.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
                return flask_resp
            else:
                flask_resp = Response(resp.content, status=resp.status_code, content_type=content_type)
                flask_resp.headers["X-Frame-Options"] = "SAMEORIGIN"
                return flask_resp
        except Exception as e:
            log.warning(f"[ONION_PROXY] Failed to proxy {target_url}: {e}")
            target_json = json.dumps(target_url)
            err_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    body {{ background: #0f1017; color: #cad3f5; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
    .err-card {{ max-width: 540px; background: #181926; border: 1px solid rgba(244, 63, 94, 0.35); border-radius: 12px; padding: 26px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }}
    h3 {{ color: #f43f5e; margin-top: 0; font-size: 18px; display: flex; align-items: center; justify-content: center; gap: 8px; }}
    p {{ color: #a5adcb; font-size: 13px; line-height: 1.6; margin: 8px 0; }}
    code {{ background: #11121d; color: #06b6d4; padding: 4px 8px; border-radius: 4px; font-size: 12px; word-break: break-all; display: inline-block; }}
    .btn-group {{ display: flex; justify-content: center; gap: 10px; margin-top: 20px; flex-wrap: wrap; }}
    .btn-action {{ padding: 9px 18px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; border: none; display: inline-flex; align-items: center; gap: 6px; transition: transform 0.15s, opacity 0.15s; }}
    .btn-action:hover {{ opacity: 0.9; transform: translateY(-1px); }}
    .btn-retry {{ background: #3b82f6; color: #fff; }}
    .btn-newnym {{ background: #10b981; color: #fff; }}
    .btn-tb {{ background: #8b5cf6; color: #fff; }}
  </style>
</head>
<body>
  <div class="err-card">
    <h3><i class="fas fa-exclamation-triangle"></i> Dark Web Connection Error</h3>
    <p>Failed to establish SOCKS5h Tor circuit to hidden service:</p>
    <p><code>{target_url}</code></p>
    <p style="font-size:12px; color:#f87171; max-height:80px; overflow-y:auto; background:rgba(248,113,113,0.08); padding:8px; border-radius:6px;">{str(e)}</p>
    <p style="font-size:11px; color:#6e738d; margin-top:12px;">The hidden service may be slow to respond, offline, or Tor is establishing a new rendezvous circuit.</p>
    <div class="btn-group">
      <button class="btn-action btn-retry" onclick="location.reload()"><i class="fas fa-redo"></i> Retry Connection</button>
      <button class="btn-action btn-newnym" onclick="newCircuitAndReload()"><i class="fas fa-sync-alt"></i> New Tor Circuit</button>
      <button class="btn-action btn-tb" onclick="launchInTorBrowser()"><i class="fas fa-shield-alt"></i> Open in Tor Browser</button>
    </div>
    <div id="action-msg" style="margin-top:12px; font-size:11px; color:#a5adcb; min-height:16px;"></div>
  </div>
  <script>
    const targetUrl = {target_json};
    function showMsg(text, isErr) {{
      const el = document.getElementById('action-msg');
      if (el) {{
        el.style.color = isErr ? '#f87171' : '#34d399';
        el.textContent = text;
      }}
    }}
    function newCircuitAndReload() {{
      showMsg('Requesting new Tor circuit (NEWNYM)...', false);
      fetch('/api/hsearch/tor_newnym', {{method: 'POST'}})
        .then(r => r.json())
        .then(() => {{
          showMsg('New circuit established. Reloading...', false);
          setTimeout(() => location.reload(), 1500);
        }})
        .catch(() => location.reload());
    }}
    function launchInTorBrowser() {{
      showMsg('Launching Desktop Tor Browser...', false);
      fetch('/api/hsearch/open_tor_browser', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{url: targetUrl}})
      }})
      .then(r => r.json())
      .then(d => {{
        if (d.ok) {{
          showMsg('Opened in Desktop Tor Browser (' + (d.path || 'launched') + ')', false);
        }} else {{
          showMsg('Error: ' + (d.message || d.error || 'Failed to open Tor Browser'), true);
        }}
      }})
      .catch(err => showMsg('Failed to launch: ' + err, true));
    }}
  </script>
</body>
</html>"""
            return Response(err_html, status=502, content_type="text/html; charset=utf-8")

    # ── Tor Browser Launcher API ──────────────────────────────────────────────
    @app.route("/api/hsearch/open_tor_browser", methods=["POST"])
    @login_required
    def api_open_tor_browser():
        data = request.get_json(force=True) or {}
        url = data.get("url", "").strip()
        if not url:
            return jsonify({"ok": False, "error": "Missing URL"}), 400

        ok, msg, path = launch_tor_browser(url)
        return jsonify({"ok": ok, "message": msg, "path": path})

    @app.route("/api/hsearch/detect_tor_browser", methods=["GET"])
    @login_required
    def api_detect_tor_browser():
        path = detect_tor_browser_path()
        return jsonify({"ok": bool(path), "path": path or ""})
