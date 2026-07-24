"""
Hecos Media Player — Routes (routes.py)
Flask Blueprint for media streaming, Drive playlist building, and playlist CRUD.

Routes:
  GET  /api/media_player/view?path=          — Stream a media file (Drive)
  GET  /api/media_player/list?path=          — List media in a dir (Drive)
  GET  /api/media_player/playlists           — List all saved playlists
  GET  /api/media_player/playlists/<name>    — Get playlist contents
  POST /api/media_player/playlists           — Create/replace a playlist
  POST /api/media_player/playlists/<name>/add — Add track to playlist
  DELETE /api/media_player/playlists/<name>  — Delete a playlist
  POST /api/media_player/control             — Playback control
  GET  /api/media_player/status              — Current playback status
"""

import os
from flask import request, jsonify, send_file, abort, Blueprint
from flask_login import login_required

try:
    from hecos.core.logging import logger
except ImportError:
    class _L:
        def info(self, *a): print("[MEDIA_PLAYER]", *a)
        def error(self, *a): print("[MEDIA_PLAYER ERR]", *a)
        def debug(self, *a, **kw): pass
        def warning(self, *a): print("[MEDIA_PLAYER WARN]", *a)
    logger = _L()

# ─── Media Type Registry ────────────────────────────────────────────────────────
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif", ".ico"}
VIDEO_EXTS = {".mp4", ".webm", ".ogg", ".ogv", ".mov", ".m4v", ".mkv", ".avi"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".oga", ".flac", ".aac", ".m4a", ".opus", ".wma"}
DOC_EXTS   = {".pdf"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS | DOC_EXTS

# ─── Blueprint ─────────────────────────────────────────────────────────────────
media_player_bp = Blueprint(
    "hecos_media_player",
    __name__,
    static_folder="static",
    static_url_path="/media_player_static"
)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _media_type(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext in IMAGE_EXTS: return "image"
    if ext in VIDEO_EXTS: return "video"
    if ext in AUDIO_EXTS: return "audio"
    if ext in DOC_EXTS:   return "document"
    return "unknown"


def _safe_path(root: str, rel_path: str) -> str | None:
    import sys
    if os.path.isabs(rel_path) or (sys.platform == "win32" and ":" in rel_path):
        candidate = os.path.abspath(os.path.normpath(rel_path))
        drive_letter = os.path.splitdrive(candidate)[0] + os.sep
        if not candidate.startswith(drive_letter):
            return None
        return candidate
    candidate = os.path.normpath(os.path.join(root, rel_path.lstrip("/\\")))
    candidate = os.path.abspath(candidate)
    root_abs = os.path.abspath(root)
    if not candidate.startswith(root_abs):
        return None
    return candidate


def _get_drive_root() -> str:
    try:
        from hecos.app.config import ConfigManager
        cfg = ConfigManager()
        root = cfg.config.get("plugins", {}).get("DRIVE", {}).get("root_dir", "")
    except Exception:
        root = ""
    if not root:
        import sys
        root = "C:\\" if sys.platform == "win32" else "/"
    return os.path.abspath(root)


def _get_tools():
    """Returns the media player tools singleton.
    
    Uses the Hecos lazy-loader (module_state.get_plugin_module) so the plugin
    is properly initialized with on_load() and VLC engine setup, exactly like
    the Brain process does it. Falls back to direct import if the system is
    not available (e.g. standalone testing).
    """
    import sys
    # Primary: use the Hecos official lazy-loader — triggers on_load/VLC init
    try:
        from hecos.core.system.module_state import get_plugin_module
        mod = get_plugin_module("MEDIA_PLAYER")
        if mod is not None:
            t = getattr(mod, "tools", None)
            if t is not None:
                return t
    except Exception:
        pass

    # Secondary: the global singleton set by MediaPlayerTools.__new__
    inst = getattr(sys, "_hecos_mp_tools", None)
    if inst is not None:
        return inst

    # Last resort: raw import (works if we inject the package into sys.path)
    try:
        from .main import tools
        return tools
    except ImportError:
        try:
            import os
            _pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if _pkg_root not in sys.path:
                sys.path.insert(0, _pkg_root)
            import media_player.main as _mp_main
            return getattr(_mp_main, "tools", None)
        except Exception:
            return None


def _get_store():
    """Returns the playlist_store module, loaded robustly regardless of import context."""
    try:
        from . import playlist_store as _ps
        return _ps
    except ImportError:
        import sys, os
        _pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _pkg_root not in sys.path:
            sys.path.insert(0, _pkg_root)
        import media_player.playlist_store as _ps
        return _ps


# ─── Media streaming ────────────────────────────────────────────────────────────

@media_player_bp.route("/api/media_player/view")
@login_required
def media_player_view():
    """GET /api/media_player/view?path=<rel_or_abs> — Stream a media file."""
    root   = _get_drive_root()
    rel    = request.args.get("path", "")
    target = _safe_path(root, rel)

    if target is None: abort(403)
    if not os.path.isfile(target): abort(404)
    if os.path.splitext(target)[1].lower() not in MEDIA_EXTS: abort(415)

    return send_file(target, as_attachment=False)


@media_player_bp.route("/api/media_player/list")
@login_required
def media_player_list():
    """GET /api/media_player/list?path=<rel_or_abs_dir> — List media in directory."""
    root    = _get_drive_root()
    rel_dir = request.args.get("path", "")
    target  = _safe_path(root, rel_dir)

    if target is None:
        return jsonify({"ok": False, "error": "Forbidden path."}), 403
    if not os.path.isdir(target):
        return jsonify({"ok": False, "error": "Directory not found."}), 404

    try:
        entries = []
        for name in sorted(os.listdir(target), key=lambda n: n.lower()):
            if os.path.splitext(name)[1].lower() not in MEDIA_EXTS:
                continue
            full = os.path.join(target, name)
            if not os.path.isfile(full):
                continue
            try:
                rel_entry = os.path.relpath(full, root).replace("\\", "/")
            except ValueError:
                rel_entry = full.replace("\\", "/")
            entries.append({
                "name": name,
                "path": rel_entry,
                "type": _media_type(name),
                "size": os.path.getsize(full),
            })
        return jsonify({"ok": True, "entries": entries})
    except Exception as e:
        logger.error(f"[MediaPlayer] list error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── Playlist API ──────────────────────────────────────────────────────────────

@media_player_bp.route("/api/media_player/playlists", methods=["GET"])
@login_required
def playlists_list():
    playlist_store = _get_store()
    return jsonify({"ok": True, "playlists": playlist_store.list_playlists()})


@media_player_bp.route("/api/media_player/playlists/<name>", methods=["GET"])
@login_required
def playlist_get(name: str):
    playlist_store = _get_store()
    pl = playlist_store.get_playlist(name)
    if not pl:
        return jsonify({"ok": False, "error": f"Playlist '{name}' not found."}), 404
    return jsonify({"ok": True, "playlist": pl})


@media_player_bp.route("/api/media_player/playlists", methods=["POST"])
@login_required
def playlist_create():
    """Body: { "name": str, "items": [str, ...] }"""
    playlist_store = _get_store()
    data  = request.get_json(force=True) or {}
    name  = data.get("name", "").strip()
    items = data.get("items", [])
    if not name:
        return jsonify({"ok": False, "error": "Playlist name required."}), 400
    pl = playlist_store.create_playlist(name, items)
    return jsonify({"ok": True, "playlist": pl})


@media_player_bp.route("/api/media_player/playlists/<name>/add", methods=["POST"])
@login_required
def playlist_add(name: str):
    """Body: { "path": str }"""
    playlist_store = _get_store()
    data = request.get_json(force=True) or {}
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"ok": False, "error": "path required."}), 400
    ok = playlist_store.add_to_playlist(name, path)
    return jsonify({"ok": ok})


@media_player_bp.route("/api/media_player/playlists/<name>", methods=["DELETE"])
@login_required
def playlist_delete(name: str):
    playlist_store = _get_store()
    ok = playlist_store.delete_playlist(name)
    return jsonify({"ok": ok, "error": "" if ok else f"Playlist '{name}' not found."})


@media_player_bp.route("/api/media_player/playlists/<name>/items/<int:index>", methods=["DELETE"])
@login_required
def playlist_remove_item(name: str, index: int):
    playlist_store = _get_store()
    ok = playlist_store.remove_from_playlist(name, index)
    return jsonify({"ok": ok})


# ─── Playback control ──────────────────────────────────────────────────────────

@media_player_bp.route("/api/media_player/control", methods=["POST"])
@login_required
def player_control():
    """
    POST /api/media_player/control
    Body: { "action": "play|pause|stop|next|prev|volume|play_playlist|scan_folder",
            "path": str?, "name": str?, "volume": int?, "shuffle": bool?,
            "save_as": str?, "recursive": bool? }
    """
    t = _get_tools()
    if not t:
        return jsonify({"ok": False, "error": "Media player not loaded."}), 503

    data   = request.get_json(force=True) or {}
    action = data.get("action", "")
    result = ""

    try:
        if action == "play":
            result = t.play(data.get("path", ""), data.get("playlist_name"))
        elif action == "pause":
            result = t.pause()
        elif action == "stop":
            result = t.stop()
        elif action == "next":
            result = t.next_track()
        elif action == "prev":
            result = t.prev_track()
        elif action == "volume":
            result = t.set_volume(int(data.get("volume", 80)))
        elif action == "play_playlist":
            result = t.play_playlist(data.get("name", ""), data.get("shuffle", False), int(data.get("index", 0)))
        elif action == "scan_folder":
            result = t.scan_folder(
                data.get("path", ""),
                save_as=data.get("save_as", ""),
                recursive=bool(data.get("recursive", True))
            )
        elif action == "play_at":
            idx = int(data.get("index", 0))
            result = t.play_by_index(idx)
        elif action == "shuffle":
            with t._lock:
                t._shuffle = bool(data.get("shuffle", not t._shuffle))
            result = f"🔀 Shuffle {'on' if t._shuffle else 'off'}"
        elif action == "repeat":
            with t._lock:
                t._repeat = bool(data.get("repeat", not t._repeat))
            result = f"🔁 Repeat {'on' if t._repeat else 'off'}"
        elif action == "seek":
            # Only supported on VLC backend
            try:
                t._get_engine().seek(float(data.get("seconds", 0)))
                result = "Seeked"
            except Exception:
                result = "Seek not supported on this backend."
        else:
            return jsonify({"ok": False, "error": f"Unknown action: {action}"}), 400
    except Exception as e:
        logger.error(f"[MediaPlayer] Control error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True, "message": result})


@media_player_bp.route("/api/media_player/status", methods=["GET"])
@login_required
def player_status():
    """GET /api/media_player/status — Get current playback state as JSON."""
    t = _get_tools()
    if not t:
        return jsonify({"ok": False, "playing": False, "track": None})
    try:
        engine = t._get_engine()
        with t._lock:
            track     = t._queue[t._queue_index] if t._queue else None
            queue_len = len(t._queue)
            queue_idx = t._queue_index
        return jsonify({
            "ok":        True,
            "playing":   engine.is_playing(),
            "track":     track["path"] if track else None,
            "position":  engine.get_position(),
            "length":    engine.get_length(),
            "volume":    engine.get_volume(),
            "queue_len": queue_len,
            "queue_idx": queue_idx,
            "shuffle":   t._shuffle,
            "repeat":    t._repeat,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@media_player_bp.route("/api/media_player/queue", methods=["GET"])
@login_required
def player_queue():
    """GET /api/media_player/queue — Return the full current play queue."""
    t = _get_tools()
    if not t:
        return jsonify({"ok": False, "queue": [], "current": -1, "playlist": ""})
    with t._lock:
        queue         = list(t._queue)
        queue_idx     = t._queue_index
        playlist_name = getattr(t, "_playlist_name", "")
    return jsonify({
        "ok":      True,
        "queue":   queue,
        "current": queue_idx,
        "playlist": playlist_name,
    })


# ─── Media Vault ───────────────────────────────────────────────────────────────

@media_player_bp.route("/hecos/api/media/open", methods=["POST"])
@login_required
def media_vault_open():
    """POST /hecos/api/media/open — Open the media folder in the OS file explorer."""
    import subprocess, sys
    from hecos.core.constants import MEDIA_DIR
    try:
        os.makedirs(MEDIA_DIR, exist_ok=True)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", os.path.normpath(MEDIA_DIR)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", MEDIA_DIR])
        else:
            subprocess.Popen(["xdg-open", MEDIA_DIR])
        return jsonify({"ok": True, "path": MEDIA_DIR})
    except Exception as e:
        logger.error(f"[MediaPlayer] vault open error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@media_player_bp.route("/hecos/api/media/clear", methods=["POST"])
@login_required
def media_vault_clear():
    """POST /hecos/api/media/clear — Delete all files in media/ (images, audio, video, screenshots)."""
    import shutil
    from hecos.core.constants import MEDIA_DIR, IMAGES_DIR, AUDIO_DIR, SNAPSHOTS_DIR, VIDEO_DIR
    deleted = 0
    errors = []
    # Wipe sub-directories contents but keep the directories themselves
    for subdir in [IMAGES_DIR, AUDIO_DIR, SNAPSHOTS_DIR, VIDEO_DIR]:
        if not os.path.isdir(subdir):
            continue
        for filename in os.listdir(subdir):
            fpath = os.path.join(subdir, filename)
            try:
                if os.path.isfile(fpath) or os.path.islink(fpath):
                    os.remove(fpath)
                    deleted += 1
                elif os.path.isdir(fpath):
                    shutil.rmtree(fpath)
                    deleted += 1
            except Exception as e:
                errors.append(str(e))
    logger.info(f"[MediaPlayer] Media Vault cleared: {deleted} items removed.")
    return jsonify({"ok": True, "deleted": deleted, "errors": errors})


# ─── Plugin config endpoints ───────────────────────────────────────────────────

@media_player_bp.route("/hecos/api/plugins/media_player/config", methods=["GET"])
@login_required
def get_media_player_config():
    try:
        from media_player_config.config_manager import get_config
        return jsonify(get_config())
    except Exception as e:
        logger.error(f"[MediaPlayer] Error reading config: {e}")
        return jsonify({}), 500

@media_player_bp.route("/hecos/api/plugins/media_player/config", methods=["POST"])
@login_required
def save_media_player_config():
    try:
        from media_player_config.config_manager import save_config
        data = request.json
        if save_config(data):
            # Try to push default volume to active player
            vol = data.get("default_volume")
            if vol is not None:
                try:
                    from media_player.main import tools
                    tools._get_engine().set_volume(int(vol))
                except Exception:
                    pass
            return jsonify({"ok": True})
        return jsonify({"ok": False}), 500
    except Exception as e:
        logger.error(f"[MediaPlayer] Error saving config: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── Plugin entry point ────────────────────────────────────────────────────────

def init_plugin_routes(app, cfg_mgr, root_dir, _logger):
    """Called by HPM when registering the plugin."""
    global logger
    logger = _logger
    
    # We must register the blueprint if not already registered
    if "hecos_media_player" not in app.blueprints:
        app.register_blueprint(media_player_bp)
        logger.info("[MediaPlayer] Blueprint 'hecos_media_player' registered.")
    else:
        logger.debug("[MediaPlayer] Blueprint already registered, skipping.")

