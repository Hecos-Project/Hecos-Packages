"""
web/search_routes.py
Flask API and UI routes for Hecos Deep Search & Intelligence.
Provides dedicated /search page, SSE streaming query API, sessions, and component management.
"""
from __future__ import annotations

import os
import time
import json
import queue
import threading
import logging
from flask import Blueprint, request, jsonify, render_template, Response, stream_with_context
from flask_login import login_required

try:
    from hecos.modules.net_search.search.service import get_search_service
    from hecos.modules.net_search.search.models import SearchQuery
    from hecos.modules.net_search.search.sessions import get_session_store
    from hecos.modules.net_search.search.config import (
        get_search_config, update_search_config,
        get_endpoints, update_endpoints, reset_endpoints_to_defaults
    )
    from hecos.modules.net_search.search.components.catalog import get_component, get_all_statuses
    from hecos.modules.net_search.search.http_client import check_tor_connection, is_tor_online
    from hecos.modules.net_search.search.extract.fetcher import fetch_and_clean_page
except (ImportError, ValueError):
    from ..search.service import get_search_service
    from ..search.models import SearchQuery
    from ..search.sessions import get_session_store
    from ..search.config import (
        get_search_config, update_search_config,
        get_endpoints, update_endpoints, reset_endpoints_to_defaults
    )
    from ..search.components.catalog import get_component, get_all_statuses
    from ..search.http_client import check_tor_connection, is_tor_online
    from ..search.extract.fetcher import fetch_and_clean_page
try:
    from hecos.core.logging import logger as hecos_logger
except (ImportError, ValueError):
    hecos_logger = logging.getLogger("net_search.web")

logger = hecos_logger


def register_search_routes(app, cfg_mgr, root_dir, logger=None):
    """Registers all Deep Search routes on the Flask app."""
    log = logger or logging.getLogger("browser.web.search")
    log.info("[DeepSearch] Registering search routes and /search page...")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tpl_dir = os.path.join(base_dir, "web", "templates")
    stc_dir = os.path.join(base_dir, "web", "static")

    service = get_search_service()
    session_store = get_session_store()

    # Register bookmarks API
    try:
        from .search_bookmarks_routes import register_bookmarks_routes
        register_bookmarks_routes(app, logger=log)
    except Exception as e:
        log.warning(f"[DeepSearch] Could not register bookmarks routes: {e}")

    # ── Main Search Page ──────────────────────────────────────────────────────
    @app.route("/search", methods=["GET"])
    @login_required
    def search_page():
        """Renders the dedicated Hecos Deep Search & Media Discovery interface."""
        initial_q = request.args.get("q", "")
        initial_mode = request.args.get("mode", "clear")
        initial_session = request.args.get("session", "")
        return render_template(
            "search.html",
            initial_q=initial_q,
            initial_mode=initial_mode,
            initial_session=initial_session,
            tor_online=is_tor_online(),
            version=int(time.time())
        )

    # ── Tor Live Web Viewer Page ──────────────────────────────────────────────
    @app.route("/search/viewer", methods=["GET"])
    @login_required
    def search_viewer_page():
        """Renders the in-app Cross-Browser Tor Live Viewer."""
        target_url = request.args.get("url", "").strip()
        if not target_url:
            return "Missing url parameter", 400
        if not target_url.startswith("http://") and not target_url.startswith("https://"):
            target_url = "http://" + target_url

        import urllib.parse
        target_encoded = urllib.parse.quote(target_url)
        return render_template(
            "search_viewer.html",
            target_url=target_url,
            target_url_encoded=target_encoded,
            tor_online=is_tor_online(),
            version=int(time.time())
        )

    # ── Search API (Standard JSON) ────────────────────────────────────────────
    @app.route("/api/hsearch/query", methods=["POST"])
    @login_required
    def api_search_query():
        try:
            data = request.get_json(force=True) or {}
            query_str = data.get("query", "").strip()
            if not query_str:
                return jsonify({"ok": False, "error": "Query cannot be empty"}), 400

            sq = SearchQuery(
                query=query_str,
                mode=data.get("mode", "clear"),
                engines=data.get("engines", []),
                limit=int(data.get("limit", 50)),
                safe_search=bool(data.get("safe_search", False)),
                dark_bypass=bool(data.get("dark_bypass", True)),
                time_range=data.get("time_range"),
                file_types=data.get("file_types", []),
                auto_fallback_tor=bool(data.get("auto_fallback_tor", True)),
                target_username=data.get("target_username")
            )

            session = service.search(sq)
            return jsonify({
                "ok": True,
                "session": session.to_dict()
            })
        except Exception as e:
            log.error(f"Search API error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    # ── Streaming Search API (Server-Sent Events) ─────────────────────────────
    @app.route("/api/hsearch/query_stream", methods=["GET"])
    @login_required
    def api_search_stream():
        query_str = request.args.get("q", "").strip()
        if not query_str:
            return jsonify({"ok": False, "error": "Query cannot be empty"}), 400

        mode = request.args.get("mode", "clear")
        limit = int(request.args.get("limit", 50))
        safe_search = request.args.get("safe_search", "false").lower() == "true"
        dark_bypass = request.args.get("dark_bypass", "true").lower() == "true"
        file_types_raw = request.args.get("file_types", "")
        file_types = [f.strip() for f in file_types_raw.split(",") if f.strip()]
        engines_raw = request.args.get("engines", "")
        engines = [e.strip() for e in engines_raw.split(",") if e.strip()]

        hecos_logger.info(f"[SEARCH:STREAM] Client connected: query='{query_str}' [mode={mode}, limit={limit}, safe_search={safe_search}, dark_bypass={dark_bypass}]")

        sq = SearchQuery(
            query=query_str,
            mode=mode,
            engines=engines,
            limit=limit,
            safe_search=safe_search,
            dark_bypass=dark_bypass,
            file_types=file_types
        )

        event_queue = queue.Queue()

        def _stream_callback(event_dict):
            event_queue.put(event_dict)

        def _worker():
            try:
                service.search(sq, stream_cb=_stream_callback)
            except Exception as e:
                hecos_logger.error(f"[SEARCH:STREAM] Execution failed: {e}")
                event_queue.put({"type": "error", "error": str(e)})
            finally:
                event_queue.put(None)  # Sentinel

        threading.Thread(target=_worker, daemon=True).start()

        def _generate():
            while True:
                evt = event_queue.get()
                if evt is None:
                    break
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

        return Response(stream_with_context(_generate()), mimetype="text/event-stream")

    # ── Sessions API ──────────────────────────────────────────────────────────
    @app.route("/api/hsearch/sessions", methods=["GET"])
    @login_required
    def api_search_sessions():
        limit = int(request.args.get("limit", 40))
        fav_only = request.args.get("favorites", "false").lower() == "true"
        sessions = session_store.list_sessions(limit=limit, favorite_only=fav_only)
        return jsonify({"ok": True, "sessions": sessions})

    @app.route("/api/hsearch/sessions/<session_id>", methods=["GET"])
    @login_required
    def api_search_session_detail(session_id):
        session = session_store.get_session(session_id)
        if not session:
            return jsonify({"ok": False, "error": "Session not found"}), 404
        return jsonify({"ok": True, "session": session.to_dict()})

    @app.route("/api/hsearch/sessions/<session_id>", methods=["DELETE"])
    @login_required
    def api_search_session_delete(session_id):
        ok = session_store.delete_session(session_id)
        return jsonify({"ok": ok})

    @app.route("/api/hsearch/sessions/clear", methods=["POST"])
    @login_required
    def api_search_sessions_clear():
        ok = session_store.clear_all()
        return jsonify({"ok": ok})

    @app.route("/api/hsearch/sessions/<session_id>/favorite", methods=["POST"])
    @login_required
    def api_search_session_favorite(session_id):
        ok = session_store.toggle_favorite(session_id)
        return jsonify({"ok": ok})

    # ── Fetch & Clean Page API ────────────────────────────────────────────────
    @app.route("/api/hsearch/fetch", methods=["POST"])
    @login_required
    def api_search_fetch():
        data = request.get_json(force=True) or {}
        url = data.get("url", "").strip()
        max_chars = int(data.get("max_chars", 5000))
        if not url:
            return jsonify({"ok": False, "error": "Missing URL"}), 400

        res = fetch_and_clean_page(url=url, max_chars=max_chars)
        return jsonify(res)

    # ── Components Management API ─────────────────────────────────────────────
    @app.route("/api/hsearch/components", methods=["GET"])
    @login_required
    def api_search_components():
        return jsonify({"ok": True, "components": get_all_statuses()})

    @app.route("/api/hsearch/components/<component_id>/install", methods=["POST"])
    @login_required
    def api_search_component_install(component_id):
        comp = get_component(component_id)
        if not comp:
            return jsonify({"ok": False, "error": f"Unknown component {component_id}"}), 404

        # Run install synchronously or emit status
        ok, msg = comp.install()
        return jsonify({"ok": ok, "message": msg, "status": comp.get_status().to_dict()})

    @app.route("/api/hsearch/components/<component_id>/uninstall", methods=["POST"])
    @login_required
    def api_search_component_uninstall(component_id):
        comp = get_component(component_id)
        if not comp:
            return jsonify({"ok": False, "error": f"Unknown component {component_id}"}), 404
        ok, msg = comp.uninstall()
        return jsonify({"ok": ok, "message": msg, "status": comp.get_status().to_dict()})

    @app.route("/api/hsearch/components/<component_id>/start", methods=["POST"])
    @login_required
    def api_search_component_start(component_id):
        comp = get_component(component_id)
        if not comp:
            return jsonify({"ok": False, "error": f"Unknown component {component_id}"}), 404
        ok, msg = comp.start()
        return jsonify({"ok": ok, "message": msg, "status": comp.get_status().to_dict()})

    @app.route("/api/hsearch/components/<component_id>/stop", methods=["POST"])
    @login_required
    def api_search_component_stop(component_id):
        comp = get_component(component_id)
        if not comp:
            return jsonify({"ok": False, "error": f"Unknown component {component_id}"}), 404
        ok, msg = comp.stop()
        return jsonify({"ok": ok, "message": msg, "status": comp.get_status().to_dict()})

    # ── Tor Diagnostics & Control ─────────────────────────────────────────────
    @app.route("/api/hsearch/tor_status", methods=["GET"])
    @login_required
    def api_search_tor_status():
        info = check_tor_connection()
        return jsonify(info)

    @app.route("/api/hsearch/tor_newnym", methods=["POST"])
    @login_required
    def api_search_tor_newnym():
        tor_comp = get_component("tor_daemon")
        if not tor_comp:
            return jsonify({"ok": False, "error": "Tor component not found"}), 404
        ok, msg = tor_comp.new_circuit()
        return jsonify({"ok": ok, "message": msg})

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

        import urllib.parse
        import time
        import json
        try:
            from hecos.modules.browser_automation.search import http_client
        except (ImportError, ValueError):
            from ..search import http_client

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

        try:
            from hecos.modules.net_search.search.config import launch_tor_browser
        except (ImportError, ValueError):
            from ..search.config import launch_tor_browser

        ok, msg, path = launch_tor_browser(url)
        return jsonify({"ok": ok, "message": msg, "path": path})

    @app.route("/api/hsearch/detect_tor_browser", methods=["GET"])
    @login_required
    def api_detect_tor_browser():
        try:
            from hecos.modules.net_search.search.config import detect_tor_browser_path
        except (ImportError, ValueError):
            from ..search.config import detect_tor_browser_path

        path = detect_tor_browser_path()
        return jsonify({"ok": bool(path), "path": path or ""})


