"""
search/stream_hunter/routes.py
Modular Flask routes for NetSearch Stream Hunter (Live TV/IPTV, Radio, Webcams, Raw M3U8/RTSP,
Liveness Prober, Anti-CORS HLS/Audio/MJPEG Proxy, and VLC Desktop / LibVLC Bridge).
"""
from __future__ import annotations

import logging
import urllib.parse
from flask import Response, jsonify, render_template, request, stream_with_context
from flask_login import login_required
import requests

from hecos.modules.net_search.search.config import get_stream_preset_settings

from .service import get_stream_hunter_service
from .stream_prober import probe_single_stream, probe_streams_batch
from .providers_tv import fetch_and_parse_m3u, parse_m3u_content
from .preview_engine import get_or_capture_stream_snapshot
from .stream_store import get_stream_summary, set_stream_source_role
from .remote_bus import get_remote_bus
from .vlc_bridge import (
    control_libvlc_bg,
    generate_m3u_playlist_text,
    get_vlc_capabilities,
    launch_in_vlc_desktop,
    launch_playlist_in_vlc,
)

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("net_search.stream_hunter.routes")


def _rewrite_m3u8_for_proxy(m3u8_text: str, base_url: str) -> str:
    """Rewrites relative or cross-origin URLs inside an HLS .m3u8 playlist to go through our anti-CORS proxy."""
    out_lines = []
    for raw_line in m3u8_text.splitlines():
        line = raw_line.strip()
        if not line:
            out_lines.append("")
            continue
        if line.startswith("#"):
            # Also rewrite URI="..." inside #EXT-X-KEY or #EXT-X-MAP or #EXT-X-MEDIA
            if 'URI="' in line:
                import re
                def _repl_uri(m):
                    inner = m.group(1)
                    abs_u = urllib.parse.urljoin(base_url, inner)
                    proxied = f"/api/hsearch/streams/proxy?url={urllib.parse.quote(abs_u, safe='')}"
                    return f'URI="{proxied}"'
                line = re.sub(r'URI="([^"]+)"', _repl_uri, line)
            out_lines.append(line)
        else:
            abs_u = urllib.parse.urljoin(base_url, line)
            proxied = f"/api/hsearch/streams/proxy?url={urllib.parse.quote(abs_u, safe='')}"
            out_lines.append(proxied)
    return "\n".join(out_lines) + "\n"


def register_stream_hunter_routes(app, logger=None):
    """Registers Stream Hunter API endpoints safely without double registration."""
    if "api_stream_hunter_search" in app.view_functions:
        return

    log = logger or hecos_logger
    log.info("[StreamHunter] Registering modular Live Stream Discovery & VLC routes...")

    @app.route("/api/hsearch/streams/capabilities", methods=["GET"])
    @login_required
    def api_stream_hunter_capabilities():
        try:
            return jsonify({
                "ok": True,
                "stream_summary": get_stream_summary(),
                "preset_settings": get_stream_preset_settings(),
                **get_vlc_capabilities(),
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/hsearch/streams/summary", methods=["GET"])
    @login_required
    def api_stream_hunter_summary():
        try:
            return jsonify({"ok": True, "stream_summary": get_stream_summary()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/hsearch/streams/role", methods=["POST"])
    @login_required
    def api_stream_hunter_role():
        """1-Click Role Switcher for SQLite Stream Compilations (TV / Radio / Webcam / Raw)."""
        try:
            data = request.get_json(force=True, silent=True) or {}
            source_id = str(data.get("source_id") or "").strip()
            role = str(data.get("role") or "tv").strip().lower()
            if not source_id:
                return jsonify({"ok": False, "error": "Missing source_id"}), 400
            if role not in ("tv", "radio", "webcam", "raw"):
                role = "tv"
            count = set_stream_source_role(source_id, role)
            hecos_logger.info(f"[StreamHunter] Role updated for source '{source_id}' -> {role} ({count} streams)")
            try:
                from ..sources.registry import update_source_status
                update_source_status(source_id, {"target_pool": f"stream_{role}"})
            except Exception:
                pass
            return jsonify({
                "ok": True,
                "source_id": source_id,
                "role": role,
                "count": count,
                "stream_summary": get_stream_summary(),
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/hsearch/streams/snapshot", methods=["GET"])
    @login_required
    def api_stream_hunter_snapshot():
        """
        Returns a live 480x270 JPEG preview frame for a stream card.
        Supports periodic refresh via ?force=1 or ?t=<timestamp>.
        """
        stream_url = (request.args.get("url") or "").strip()
        title = (request.args.get("title") or "Live Stream").strip()
        category = (request.args.get("category") or "tv").strip().lower()
        protocol = (request.args.get("protocol") or "HLS").strip().upper()
        country = (request.args.get("country") or "INT").strip().upper()
        force = str(request.args.get("force") or "0").lower() in ("1", "true", "yes")
        try:
            jpeg_bytes = get_or_capture_stream_snapshot(
                stream_url=stream_url,
                title=title,
                category=category,
                protocol=protocol,
                country=country,
                force_refresh=force,
                wait_for_video=False,
            )
            return Response(
                jpeg_bytes,
                status=200,
                mimetype="image/jpeg",
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache",
                },
            )
        except Exception as e:
            log.warning(f"[StreamHunter] snapshot error for '{title}' ({stream_url}): {e}")
            return f"Snapshot error: {e}", 500

    @app.route("/api/hsearch/streams/search", methods=["GET", "POST"])
    @login_required
    def api_stream_hunter_search():
        try:
            if request.method == "POST":
                data = request.get_json(force=True, silent=True) or {}
            else:
                data = request.args.to_dict()

            query = (data.get("query") or data.get("q") or "").strip()
            subfilter = (data.get("subfilter") or data.get("category") or "all").strip()
            country = (data.get("country") or "").strip()
            limit = min(200, max(10, int(data.get("limit") or 80)))
            auto_probe = str(data.get("auto_probe") or "false").lower() in ("1", "true", "yes")
            local_only_raw = data.get("local_only")
            local_only = None if local_only_raw is None else str(local_only_raw).lower() in ("1", "true", "yes")

            svc = get_stream_hunter_service()
            res = svc.search(
                query=query,
                subfilter=subfilter,
                country=country,
                limit=limit,
                local_only=local_only,
                auto_probe=auto_probe,
            )
            return jsonify(res)
        except Exception as e:
            log.warning(f"[StreamHunter] search error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/hsearch/streams/probe", methods=["POST"])
    @login_required
    def api_stream_hunter_probe():
        try:
            data = request.get_json(force=True, silent=True) or {}
            single_url = (data.get("url") or "").strip()
            urls = data.get("urls") or ([] if not single_url else [single_url])
            timeout = min(6.0, max(1.0, float(data.get("timeout") or 3.0)))

            if len(urls) == 1:
                info = probe_single_stream(urls[0], timeout=timeout)
                log.info(
                    f"[StreamHunter] Single probe {urls[0]} -> live={info.get('is_live')} "
                    f"status={info.get('status_code')} proto={info.get('protocol')}"
                )
                return jsonify({"ok": True, "probe": info, "probes": {urls[0]: info}})

            batch = probe_streams_batch(urls, timeout=timeout)
            live_n = sum(1 for v in batch.values() if v.get("is_live"))
            log.info(f"[StreamHunter] Batch probe complete: {live_n}/{len(urls)} live")
            return jsonify({"ok": True, "probes": batch})
        except Exception as e:
            log.warning(f"[StreamHunter] probe error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/hsearch/streams/play_vlc", methods=["POST"])
    @login_required
    def api_stream_hunter_play_vlc():
        try:
            data = request.get_json(force=True, silent=True) or {}
            mode = (data.get("mode") or "single").strip().lower()
            log.debug(f"[StreamVLC] Request /play_vlc mode={mode} title={data.get('title')!r}")

            if mode == "playlist":
                streams = data.get("streams") or []
                res = launch_playlist_in_vlc(streams)
                if not res.get("ok"):
                    log.warning(f"[StreamVLC] Playlist launch rejected: {res.get('error')}")
                return jsonify(res), (200 if res.get("ok") else 400)

            if mode == "libvlc_bg":
                action = data.get("action") or "play"
                url = (data.get("stream_url") or data.get("url") or "").strip()
                title = (data.get("title") or "").strip()
                volume = int(data.get("volume") or 85)
                res = control_libvlc_bg(action=action, url=url, title=title, volume=volume)
                return jsonify(res)

            stream_url = (data.get("stream_url") or data.get("url") or "").strip()
            title = (data.get("title") or "Hecos Live Stream").strip()
            res = launch_in_vlc_desktop(stream_url=stream_url, title=title)
            if not res.get("ok"):
                log.warning(f"[StreamVLC] Desktop launch failed for {stream_url!r}: {res.get('error')}")
            return jsonify(res), (200 if res.get("ok") else 400)
        except Exception as e:
            log.warning(f"[StreamHunter] play_vlc error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/hsearch/streams/parse_m3u", methods=["POST"])
    @login_required
    def api_stream_hunter_parse_m3u():
        try:
            data = request.get_json(force=True, silent=True) or {}
            url = (data.get("url") or "").strip()
            raw_text = data.get("content") or ""
            if raw_text:
                items = parse_m3u_content(raw_text, source_url=url or "")
            elif url:
                items = fetch_and_parse_m3u(url)
            else:
                return jsonify({"ok": False, "error": "Provide url or content"}), 400
            return jsonify({
                "ok": True,
                "count": len(items),
                "streams": [it.to_dict() for it in items],
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/hsearch/streams/playlist.m3u", methods=["GET", "POST"])
    @login_required
    def api_stream_hunter_playlist_m3u():
        try:
            if request.method == "POST":
                data = request.get_json(force=True, silent=True) or {}
                streams = data.get("streams") or []
            else:
                q = (request.args.get("q") or "").strip()
                sub = (request.args.get("subfilter") or "all").strip()
                country = (request.args.get("country") or "").strip()
                res = get_stream_hunter_service().search(query=q, subfilter=sub, country=country, limit=80)
                streams = res.get("streams") or []

            m3u_text = generate_m3u_playlist_text(streams)
            return Response(
                m3u_text,
                mimetype="audio/x-mpegurl",
                headers={"Content-Disposition": 'attachment; filename="hecos_netsearch_streams.m3u8"'},
            )
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/hsearch/streams/proxy", methods=["GET"])
    @login_required
    def api_stream_hunter_proxy():
        """
        Anti-CORS streaming proxy for in-browser playback of HLS (.m3u8 / .ts),
        Icecast/Shoutcast audio (.mp3 / .aac / .ogg), and MJPEG camera feeds.
        """
        target_url = (request.args.get("url") or "").strip()
        if not target_url or not target_url.startswith(("http://", "https://")):
            return "Invalid or unsupported stream URL for web proxy", 400

        headers = {
            "User-Agent": "VLC/3.0.20 LibVLC/3.0.20",
            "Accept": "*/*",
        }
        try:
            upstream = requests.get(
                target_url,
                headers=headers,
                stream=True,
                timeout=8.0,
                allow_redirects=True,
            )
            content_type = upstream.headers.get("Content-Type") or "application/octet-stream"
            ct_lower = content_type.lower()
            final_url = upstream.url or target_url

            # If this is an HLS playlist (.m3u8), rewrite child segment/variant URLs so they also proxy
            if ".m3u8" in final_url.lower() or "mpegurl" in ct_lower:
                raw_bytes = upstream.content
                upstream.close()
                text = raw_bytes.decode("utf-8", errors="ignore")
                if "#EXTM3U" in text:
                    rewritten = _rewrite_m3u8_for_proxy(text, final_url)
                    log.debug(
                        f"[StreamProxy] Rewrote HLS playlist status={upstream.status_code} "
                        f"bytes={len(raw_bytes)} url={final_url}"
                    )
                    return Response(
                        rewritten,
                        status=200,
                        mimetype="application/vnd.apple.mpegurl",
                        headers={
                            "Access-Control-Allow-Origin": "*",
                            "Cache-Control": "no-cache, no-store",
                        },
                    )
                return Response(raw_bytes, status=upstream.status_code, content_type=content_type)

            log.info(
                f"[StreamProxy] Streaming passthrough status={upstream.status_code} "
                f"ct={content_type} url={final_url}"
            )
            # Otherwise stream chunks directly (TS segments, MP3/AAC Icecast, MJPEG camera stream)
            def _generate():
                try:
                    for chunk in upstream.iter_content(chunk_size=16384):
                        if chunk:
                            yield chunk
                finally:
                    upstream.close()

            resp_headers = {
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache",
            }
            return Response(
                stream_with_context(_generate()),
                status=upstream.status_code,
                content_type=content_type,
                headers=resp_headers,
            )
        except Exception as e:
            log.warning(f"[StreamProxy] Upstream error for {target_url}: {e}")
            return f"Stream proxy error: {e}", 502

    # ── TV Remote Command Bus & Extractable Pop-out Window ──────────────
    @app.route("/api/hsearch/streams/preset_settings", methods=["GET"])
    @login_required
    def api_stream_hunter_preset_settings():
        try:
            return jsonify({"ok": True, "preset_settings": get_stream_preset_settings()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/hsearch/streams/remote/state", methods=["GET", "POST"])
    @login_required
    def api_stream_remote_state():
        bus = get_remote_bus()
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            return jsonify(bus.sync_state(data))
        try:
            since_seq = int(request.args.get("since_seq", 0) or 0)
        except (TypeError, ValueError):
            since_seq = 0
        return jsonify(bus.get_state(since_seq=since_seq))

    @app.route("/api/hsearch/streams/remote/command", methods=["POST"])
    @login_required
    def api_stream_remote_command():
        data = request.get_json(silent=True) or {}
        cmd = str(data.get("command") or "").strip()
        if not cmd:
            return jsonify({"ok": False, "error": "command required"}), 400
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else data
        source = str(data.get("source") or "remote")
        res = get_remote_bus().dispatch_command(cmd, payload, source=source)
        status = 200 if res.get("ok") else 400
        return jsonify(res), status

    @app.route("/search/stream_remote", methods=["GET"])
    @login_required
    def search_stream_remote_popout():
        bus_state = get_remote_bus().get_state()
        return render_template(
            "stream_hunter/stream_remote_popout.html",
            initial_state=bus_state,
        )
