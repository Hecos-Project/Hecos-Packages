"""
search/stream_hunter/preview_engine.py
Live Preview Frame Capture & Dynamic Telemetry Snapshot Engine for Stream Hunter.
- Captures real live video frames from HLS (.m3u8), RTSP, RTMP, and MJPEG streams using FFmpeg / HTTP byte boundaries.
- Renders dynamic 480x270 cyber-HUD preview cards via Pillow (PIL) for Radio/Icecast audio streams and while video frames are warming up.
- Uses an asynchronous background worker pool + disk cache so the UI never blocks and previews refresh periodically.
"""
from __future__ import annotations

import hashlib
import io
import logging
import math
import os
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Set

import requests

try:
    from hecos.core.logging import logger as hecos_logger
except ImportError:
    hecos_logger = logging.getLogger("net_search.stream_preview")

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


_CAPTURE_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sh_preview")
_IN_FLIGHT_LOCK = threading.Lock()
_IN_FLIGHT_KEYS: Set[str] = set()
_FAILED_BACKOFF_UNTIL: Dict[str, float] = {}
_FAILED_BACKOFF_TTL_SEC = 180.0
_LOGO_MEM_CACHE: Dict[str, bytes] = {}


def _get_snapshot_dir() -> str:
    base = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "stream_hunter_cache", "snapshots")
    )
    os.makedirs(base, exist_ok=True)
    return base


def _find_ffmpeg() -> Optional[str]:
    w = shutil.which("ffmpeg")
    if w:
        return w
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


_FFMPEG_EXE = _find_ffmpeg()


def _stream_key(stream_url: str) -> str:
    return hashlib.sha1((stream_url or "").strip().encode("utf-8", errors="ignore")).hexdigest()[:16]


def _capture_mjpeg_frame(url: str, timeout: float = 3.5) -> Optional[bytes]:
    """Extracts a single JPEG frame (FFD8 ... FFD9) from an MJPEG stream."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "VLC/3.0.20 LibVLC/3.0.20"},
            stream=True,
            timeout=timeout,
        )
        buf = b""
        for chunk in resp.iter_content(chunk_size=8192):
            buf += chunk
            start = buf.find(b"\xff\xd8")
            if start != -1:
                end = buf.find(b"\xff\xd9", start + 2)
                if end != -1:
                    frame = buf[start : end + 2]
                    resp.close()
                    hecos_logger.info(f"[StreamPreview] MJPEG frame captured ({len(frame)} bytes) from {url}")
                    return frame
            if len(buf) > 512 * 1024:
                break
        resp.close()
        hecos_logger.debug(f"[StreamPreview] MJPEG boundary not found in {len(buf)} bytes for {url}")
    except Exception as e:
        hecos_logger.debug(f"[StreamPreview] MJPEG capture failed for {url}: {e}")
    return None


def _capture_ffmpeg_frame(url: str, timeout: float = 4.2) -> Optional[bytes]:
    """Captures a single 480x270 JPEG frame from an HLS/RTSP/HTTP video stream using ffmpeg."""
    if not _FFMPEG_EXE or not url:
        if not _FFMPEG_EXE:
            hecos_logger.debug("[StreamPreview] FFmpeg binary unavailable for video snapshot capture")
        return None
    cmd = [
        _FFMPEG_EXE,
        "-y",
        "-loglevel", "error",
        "-user_agent", "VLC/3.0.20 LibVLC/3.0.20",
        "-rw_timeout", "3500000",
        "-i", url,
        "-frames:v", "1",
        "-vf", "scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "-q:v", "5",
        "-",
    ]
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            creationflags=creationflags,
        )
        if proc.returncode == 0 and proc.stdout and len(proc.stdout) > 800:
            hecos_logger.info(f"[StreamPreview] FFmpeg live frame captured ({len(proc.stdout)} bytes) from {url}")
            return proc.stdout
        err_msg = (proc.stderr or b"").decode("utf-8", errors="ignore").strip()[:160]
        hecos_logger.debug(
            f"[StreamPreview] FFmpeg capture empty/failed rc={proc.returncode} url={url} err={err_msg!r}"
        )
    except subprocess.TimeoutExpired:
        hecos_logger.debug(f"[StreamPreview] FFmpeg capture timed out ({timeout}s) for {url}")
    except Exception as e:
        hecos_logger.debug(f"[StreamPreview] FFmpeg capture exception for {url}: {e}")
    return None


def _stamp_live_frame(jpeg_bytes: bytes, title: str = "", protocol: str = "HLS", country: str = "") -> bytes:
    """Stamps a clean cyber HUD timestamp & protocol bar onto a captured live video frame."""
    if not HAS_PIL:
        return jpeg_bytes
    try:
        img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
        if img.size != (480, 270):
            img = img.resize((480, 270), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(img, "RGBA")
        # Semi-transparent bottom telemetry strip
        draw.rectangle([(0, 240), (480, 270)], fill=(6, 11, 25, 195))
        draw.line([(0, 240), (480, 240)], fill=(34, 211, 238, 130), width=1)
        # Green live indicator dot
        draw.ellipse([(10, 250), (18, 258)], fill=(16, 185, 129, 255))
        ts_str = time.strftime("%H:%M:%S")
        left_txt = f"LIVE FRAME  •  {protocol.upper()}  {('•  ' + country.upper()) if country else ''}"
        right_txt = f"UPD {ts_str}"
        draw.text((24, 248), left_txt[:42], fill=(226, 232, 240, 255))
        draw.text((385, 248), right_txt, fill=(103, 232, 249, 255))

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=84)
        return out.getvalue()
    except Exception:
        return jpeg_bytes


def _fetch_logo_bytes(logo_url: str) -> Optional[bytes]:
    if not logo_url or not logo_url.startswith(("http://", "https://")):
        return None
    if logo_url in _LOGO_MEM_CACHE:
        return _LOGO_MEM_CACHE[logo_url]
    try:
        r = requests.get(logo_url, timeout=2.0, headers={"User-Agent": "HecosNetSearch/1.1"})
        if r.status_code == 200 and len(r.content) < 300_000:
            _LOGO_MEM_CACHE[logo_url] = r.content
            return r.content
    except Exception:
        pass
    return None


def render_telemetry_preview_jpeg(
    title: str = "Live Stream",
    category: str = "tv",
    protocol: str = "HLS",
    country: str = "INT",
    logo_url: str = "",
    now_playing: str = "",
    stream_url: str = "",
) -> bytes:
    """
    Renders a 480x270 cyber-HUD preview card in JPEG format using Pillow.
    Used for Radio/Audio streams (with dynamic live spectrum waveform) and as an instant
    preview while live video frames are being captured in the background.
    """
    if not HAS_PIL:
        return b""

    w, h = 480, 270
    img = Image.new("RGB", (w, h), (9, 14, 28))
    draw = ImageDraw.Draw(img, "RGBA")

    # Subtle cyber grid lines
    for gx in range(0, w, 32):
        draw.line([(gx, 0), (gx, h)], fill=(30, 41, 59, 90), width=1)
    for gy in range(0, h, 32):
        draw.line([(0, gy), (w, gy)], fill=(30, 41, 59, 90), width=1)

    cat_lower = (category or "tv").lower()
    if cat_lower == "radio":
        accent = (34, 211, 238)       # Cyan
        cat_label = "RADIO / ICECAST AUDIO"
    elif cat_lower == "webcam":
        accent = (16, 185, 129)       # Emerald
        cat_label = "LIVE WEBCAM FEED"
    elif cat_lower == "tv":
        accent = (56, 189, 248)       # Sky Blue
        cat_label = "LIVE TV / IPTV"
    else:
        accent = (168, 85, 247)       # Purple
        cat_label = "RAW NETWORK STREAM"

    # Top header strip
    draw.rectangle([(0, 0), (w, 34)], fill=(15, 23, 42, 220))
    draw.line([(0, 34), (w, 34)], fill=(accent[0], accent[1], accent[2], 140), width=1)
    draw.text((12, 10), f"{cat_label}  •  {protocol.upper()}  •  {country.upper()}", fill=(148, 163, 184, 255))

    # Dynamic waveform / equalizer bars in the center-bottom area (changes on every refresh!)
    seed_val = int(hashlib.md5(f"{stream_url}|{int(time.time() // 8)}".encode()).hexdigest()[:8], 16)
    num_bars = 36
    bar_w = 8
    gap = 4
    start_x = (w - (num_bars * (bar_w + gap))) // 2
    base_y = 218

    for i in range(num_bars):
        phase = (seed_val + i * 37) % 100
        wave = abs(math.sin((i * 0.35) + (seed_val % 17)))
        bar_h = int(12 + (wave * 52) + ((phase % 18)))
        x0 = start_x + i * (bar_w + gap)
        y0 = base_y - bar_h
        draw.rectangle(
            [(x0, y0), (x0 + bar_w, base_y)],
            fill=(accent[0], accent[1], accent[2], 175),
        )

    # Optional Logo in center-left if available
    text_x = 24
    logo_bytes = _fetch_logo_bytes(logo_url)
    if logo_bytes:
        try:
            l_img = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
            l_img.thumbnail((64, 64), Image.Resampling.LANCZOS)
            draw.rounded_rectangle([(20, 56), (92, 128)], radius=8, fill=(15, 23, 42, 230), outline=(accent[0], accent[1], accent[2], 140))
            lx = 20 + (72 - l_img.width) // 2
            ly = 56 + (72 - l_img.height) // 2
            img.paste(l_img, (lx, ly), l_img)
            text_x = 106
        except Exception:
            pass

    # Title & Host/NowPlaying
    clean_title = (title or "Live Stream").strip()
    draw.text((text_x, 66), clean_title[:42], fill=(248, 250, 252, 255))
    if len(clean_title) > 42:
        draw.text((text_x, 84), clean_title[42:84], fill=(203, 213, 225, 255))

    sub_line = now_playing or stream_url.split("://")[-1].split("/")[0]
    if sub_line:
        draw.text((text_x, 106), f"Signal: {sub_line[:46]}", fill=(accent[0], accent[1], accent[2], 240))

    # Bottom HUD bar with timestamp
    draw.rectangle([(0, 240), (w, 270)], fill=(6, 11, 25, 230))
    draw.line([(0, 240), (w, 240)], fill=(accent[0], accent[1], accent[2], 120), width=1)
    draw.ellipse([(10, 250), (18, 258)], fill=(16, 185, 129, 255))
    ts_str = time.strftime("%H:%M:%S")
    mode_lbl = "LIVE AUDIO SPECTRUM" if cat_lower == "radio" else "LIVE STREAM MONITOR"
    draw.text((24, 248), mode_lbl, fill=(226, 232, 240, 255))
    draw.text((385, 248), f"UPD {ts_str}", fill=(103, 232, 249, 255))

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=84)
    return out.getvalue()


def _bg_capture_worker(key: str, stream_url: str, title: str, protocol: str, country: str, cache_path: str) -> None:
    try:
        p_upper = (protocol or "").upper()
        frame: Optional[bytes] = None
        if p_upper == "MJPEG" or "mjpg" in stream_url.lower():
            frame = _capture_mjpeg_frame(stream_url, timeout=3.5)
        else:
            frame = _capture_ffmpeg_frame(stream_url, timeout=4.2)

        if frame:
            stamped = _stamp_live_frame(frame, title=title, protocol=protocol, country=country)
            tmp_path = cache_path + ".tmp"
            with open(tmp_path, "wb") as f:
                f.write(stamped)
            os.replace(tmp_path, cache_path)
            with _IN_FLIGHT_LOCK:
                _FAILED_BACKOFF_UNTIL.pop(key, None)
            hecos_logger.info(
                f"[StreamPreview] Cached live snapshot key={key} ({len(stamped)} bytes) for '{title}' [{p_upper}]"
            )
        else:
            with _IN_FLIGHT_LOCK:
                _FAILED_BACKOFF_UNTIL[key] = time.time() + _FAILED_BACKOFF_TTL_SEC
            hecos_logger.debug(
                f"[StreamPreview] Capture unavailable key={key} (cooldown {int(_FAILED_BACKOFF_TTL_SEC)}s) for '{title}' ({stream_url})"
            )
    except Exception as e:
        with _IN_FLIGHT_LOCK:
            _FAILED_BACKOFF_UNTIL[key] = time.time() + _FAILED_BACKOFF_TTL_SEC
        hecos_logger.warning(f"[StreamPreview] Background worker error key={key} ({stream_url}): {e}")
    finally:
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT_KEYS.discard(key)


def get_or_capture_stream_snapshot(
    stream_url: str,
    title: str = "",
    category: str = "tv",
    protocol: str = "HLS",
    country: str = "INT",
    logo_url: str = "",
    now_playing: str = "",
    force_refresh: bool = False,
    wait_for_video: bool = False,
) -> bytes:
    """
    Returns a 480x270 JPEG preview for any stream.
    - For video/TV/webcam streams: serves cached live frame if fresh (<25s), triggers background
      FFmpeg/MJPEG capture when stale or forced, and optionally waits up to 2.8s if requested.
    - For radio/audio streams (or while video capture is warming up): returns a dynamic Pillow HUD snapshot.
    """
    cat_lower = (category or "tv").lower()
    proto_upper = (protocol or "HLS").upper()

    # Audio-only streams always get the dynamic live spectrum preview
    is_video_candidate = (
        cat_lower in ("tv", "webcam", "raw")
        and proto_upper not in ("ICECAST", "PLS")
        and not stream_url.lower().endswith((".mp3", ".aac", ".ogg", ".opus", ".pls"))
    )

    if is_video_candidate and stream_url:
        key = _stream_key(stream_url)
        cache_path = os.path.join(_get_snapshot_dir(), f"{key}.jpg")
        now = time.time()

        has_cached = os.path.isfile(cache_path)
        cache_age = (now - os.path.getmtime(cache_path)) if has_cached else 999999.0

        # If cache is fresh (< 22s) and not forced, return immediately
        if has_cached and cache_age < 22.0 and not force_refresh:
            try:
                with open(cache_path, "rb") as f:
                    hecos_logger.debug(f"[StreamPreview] Cache hit key={key} age={cache_age:.1f}s '{title}'")
                    return f.read()
            except Exception as e:
                hecos_logger.debug(f"[StreamPreview] Cache read error key={key}: {e}")

        # Schedule background capture if not already running and not in failure cooldown
        should_spawn = False
        with _IN_FLIGHT_LOCK:
            backoff_until = _FAILED_BACKOFF_UNTIL.get(key, 0.0)
            in_cooldown = now < backoff_until
            if key not in _IN_FLIGHT_KEYS and not in_cooldown:
                _IN_FLIGHT_KEYS.add(key)
                should_spawn = True

        if should_spawn:
            hecos_logger.debug(
                f"[StreamPreview] Spawning capture key={key} force={force_refresh} '{title}' [{proto_upper}]"
            )
            fut = _CAPTURE_POOL.submit(
                _bg_capture_worker, key, stream_url, title, proto_upper, country, cache_path
            )
            if wait_for_video:
                try:
                    fut.result(timeout=2.6)
                except Exception:
                    pass

        # Re-check if cached file now exists (either freshly written or slightly older while refreshing)
        if os.path.isfile(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    return f.read()
            except Exception as e:
                hecos_logger.debug(f"[StreamPreview] Stale cache read error key={key}: {e}")

    hecos_logger.debug(f"[StreamPreview] Rendering HUD telemetry snapshot for '{title}' cat={cat_lower} proto={proto_upper}")
    return render_telemetry_preview_jpeg(
        title=title,
        category=category,
        protocol=protocol,
        country=country,
        logo_url=logo_url,
        now_playing=now_playing,
        stream_url=stream_url,
    )
