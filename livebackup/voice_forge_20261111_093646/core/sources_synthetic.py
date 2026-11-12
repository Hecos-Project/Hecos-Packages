"""
Voice Forge - Synthetic Voice Generators
Generates clean, synthetic audio references directly from Fish Speech S2-Pro (random seed)
or Kokoro TTS. These require zero external human voice files and ensure 100% original timbre foundation.
"""

import io
import gc
import time
import threading
import urllib.request
import urllib.error
import numpy as np
import soundfile as sf
from typing import Tuple, Optional, Callable

from .sources_audio import resample_audio

_kokoro_lock = threading.Lock()
_kokoro_cache = {"lang": None, "pipeline": None}


def _vf_log(level: str, msg: str) -> None:
    """Routes logs through hecos.core.logging.logger safely."""
    try:
        from hecos.core.logging import logger as hecos_logger
        fn = getattr(hecos_logger, level, hecos_logger.info)
        fn("VOICE_FORGE", msg)
    except Exception:
        print(f"[VOICE_FORGE] [{level.upper()}] {msg}")


def _emit_progress(
    progress_cb: Optional[Callable[[float, str], None]],
    fraction: float,
    message: str,
) -> None:
    if progress_cb is not None:
        try:
            progress_cb(max(0.0, min(1.0, float(fraction))), message)
        except Exception:
            pass


def _estimate_fish_max_tokens(text: str) -> int:
    """Scales max_new_tokens proportionally to text length to bound synthesis latency."""
    return max(160, min(512, int(len(text or "") * 4.0) + 64))


def _ensure_fish_ready(
    host: str,
    port: int,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> None:
    """Ensures a local Fish Speech daemon is listening/healthy before issuing /v1/tts."""
    is_local = host in ("127.0.0.1", "localhost", "::1")
    if not is_local:
        return
    try:
        from hecos.core.audio.tts.fish_speech_daemon import FishSpeechDaemon
        daemon = FishSpeechDaemon.get_instance()
        if daemon.is_healthy(host, port, timeout=1.5):
            _vf_log("debug", f"Fish Speech server healthy at {host}:{port}")
            return
        if daemon.is_port_listening(host, port):
            _vf_log("debug", f"Fish Speech port listening at {host}:{port}; proceeding with request")
            return

        _vf_log("info", f"Local Fish Speech server offline at {host}:{port}; calling ensure_running(timeout=90s)")
        _emit_progress(progress_cb, 0.12, f"Starting Fish Speech daemon on {host}:{port}...")
        ok, err_msg = daemon.ensure_running(timeout=90.0)
        if not ok:
            raise RuntimeError(f"Fish Speech daemon did not become ready on {host}:{port}: {err_msg}")
        _vf_log("info", f"Local Fish Speech daemon became ready at {host}:{port}")
    except ImportError:
        _vf_log("debug", "FishSpeechDaemon helper unavailable; assuming external Fish Speech server")


def generate_fish_seed(
    text: str,
    seed: int = 42,
    host: str = "127.0.0.1",
    port: Optional[int] = None,
    timeout: int = 240,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> Tuple[np.ndarray, int]:
    """
    Generates a 100% synthetic voice sample using Fish Speech S2-Pro with an empty reference
    list and a specific random seed.
    """
    if port is None:
        try:
            from hecos.core.audio.tts.fish_speech_daemon import FishSpeechDaemon
            resolved_host, port = FishSpeechDaemon.get_instance()._resolve_target()
            if resolved_host:
                host = "127.0.0.1" if resolved_host == "0.0.0.0" else resolved_host
        except Exception:
            port = 18480
    elif host == "0.0.0.0":
        host = "127.0.0.1"

    try:
        import ormsgpack
    except ImportError:
        raise RuntimeError("ormsgpack is required to communicate with Fish Speech server")

    _ensure_fish_ready(host, port, progress_cb=progress_cb)

    max_new_tokens = _estimate_fish_max_tokens(text)
    payload = {
        "text": text,
        "references": [],
        "seed": int(seed),
        "temperature": 0.7,
        "top_p": 0.8,
        "repetition_penalty": 1.2,
        "max_new_tokens": max_new_tokens,
        "chunk_length": 200,
        "streaming": False,
        "format": "wav",
        "normalize": True
    }

    packed = ormsgpack.packb(payload, option=ormsgpack.OPT_SERIALIZE_NUMPY)
    url = f"http://{host}:{port}/v1/tts"
    req = urllib.request.Request(
        url,
        data=packed,
        headers={"Content-Type": "application/msgpack"},
        method="POST"
    )

    _vf_log(
        "info",
        f"Fish Speech seed synthesis start: seed={seed}, text_len={len(text)}, "
        f"max_new_tokens={max_new_tokens}, url={url}, timeout={timeout}s"
    )
    _emit_progress(progress_cb, 0.18, f"Synthesizing Fish Speech seed (seed={seed}, max {max_new_tokens} tokens)...")

    t0 = time.monotonic()
    stop_heartbeat = threading.Event()

    def _heartbeat_loop():
        while not stop_heartbeat.wait(1.0):
            elapsed = time.monotonic() - t0
            est_frac = min(0.92, 0.20 + (elapsed / 80.0) * 0.72)
            _emit_progress(
                progress_cb,
                est_frac,
                f"Synthesizing Fish Speech seed... ({int(elapsed)}s elapsed)"
            )

    hb_thread = None
    if progress_cb is not None:
        hb_thread = threading.Thread(target=_heartbeat_loop, daemon=True, name="vf-fish-heartbeat")
        hb_thread.start()

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            wav_bytes = resp.read()
        elapsed = time.monotonic() - t0
        with io.BytesIO(wav_bytes) as bio:
            audio, fs = sf.read(bio)
            if audio.ndim > 1:
                audio = np.mean(audio, axis=1)
        audio_out = audio.astype(np.float64)
        dur = len(audio_out) / float(fs) if fs > 0 else 0.0
        _vf_log(
            "info",
            f"Fish Speech seed synthesis OK in {elapsed:.2f}s "
            f"(bytes={len(wav_bytes)}, fs={fs}Hz, duration={dur:.2f}s)"
        )
        _emit_progress(progress_cb, 1.0, f"Fish Speech seed ready ({dur:.1f}s @ {fs}Hz)")
        return audio_out, fs
    except urllib.error.HTTPError as e:
        elapsed = time.monotonic() - t0
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        msg = f"Fish Speech HTTP {e.code} after {elapsed:.1f}s at {url}: {detail or e.reason}"
        _vf_log("error", msg)
        raise RuntimeError(msg)
    except urllib.error.URLError as e:
        elapsed = time.monotonic() - t0
        msg = f"Failed to connect to Fish Speech server at {url} after {elapsed:.1f}s: {e}"
        _vf_log("error", msg)
        raise RuntimeError(msg)
    except Exception as e:
        elapsed = time.monotonic() - t0
        msg = f"Fish Speech seed generation error after {elapsed:.1f}s: {type(e).__name__}: {e}"
        _vf_log("error", msg)
        raise RuntimeError(msg)
    finally:
        stop_heartbeat.set()
        if hb_thread is not None:
            hb_thread.join(timeout=0.5)


def _get_kokoro_pipeline(k_lang: str):
    """Returns a cached Kokoro KPipeline, evicting any previous language pipeline to save VRAM."""
    with _kokoro_lock:
        if _kokoro_cache["pipeline"] is not None and _kokoro_cache["lang"] == k_lang:
            _vf_log("debug", f"Kokoro KPipeline cache HIT for lang='{k_lang}'")
            return _kokoro_cache["pipeline"]

        try:
            from hecos.core.audio.tts.kokoro_engine import _patch_espeak_path, _ensure_kokoro_compat
            _patch_espeak_path()
            _ensure_kokoro_compat()
        except Exception as e:
            _vf_log("warning", f"Could not apply Kokoro compat patches before load: {e}")

        if _kokoro_cache["pipeline"] is not None:
            old_lang = _kokoro_cache["lang"]
            _vf_log("debug", f"Evicting cached Kokoro KPipeline (lang='{old_lang}') before loading '{k_lang}'")
            _kokoro_cache["pipeline"] = None
            _kokoro_cache["lang"] = None
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

        from kokoro import KPipeline
        _vf_log("info", f"Loading Kokoro KPipeline for lang='{k_lang}'...")
        pipeline = KPipeline(lang_code=k_lang)
        _kokoro_cache["lang"] = k_lang
        _kokoro_cache["pipeline"] = pipeline
        return pipeline


def generate_kokoro_voice(
    text: str,
    voice: str = "af_heart",
    lang_code: str = "it",
    speed: float = 1.0,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> Tuple[np.ndarray, int]:
    """
    Generates synthetic speech using Kokoro TTS and resamples it cleanly to 44.1kHz.
    """
    try:
        import kokoro  # noqa: F401
    except ImportError:
        raise RuntimeError("Kokoro package is not installed.")

    # Map language code if necessary (Kokoro uses 'a' for American English, 'b' for British English, 'i' for Italian, etc.)
    kokoro_lang_map = {
        "en": "a",
        "it": "i",
        "es": "e",
        "fr": "f",
        "de": "d",
        "ja": "j",
        "zh": "z"
    }
    k_lang = kokoro_lang_map.get(lang_code.lower(), lang_code.lower()[:1] or "a")

    _vf_log(
        "info",
        f"Kokoro seed synthesis start: voice={voice}, lang={lang_code}->{k_lang}, "
        f"speed={speed}, text_len={len(text)}"
    )
    _emit_progress(progress_cb, 0.15, f"Initializing Kokoro pipeline ({k_lang})...")

    t0 = time.monotonic()
    try:
        pipeline = _get_kokoro_pipeline(k_lang)
        _emit_progress(progress_cb, 0.45, f"Synthesizing Kokoro voice '{voice}'...")
        generator = pipeline(text, voice=voice, speed=speed, split_pattern=r'\n+')
        chunks = []
        for _, _, audio in generator:
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            arr = np.asarray(audio, dtype=np.float64)
            if arr.size > 0:
                chunks.append(arr)
        if not chunks:
            raise RuntimeError("Kokoro did not yield any audio chunks.")

        full_audio = np.concatenate(chunks)
        _emit_progress(progress_cb, 0.85, "Resampling Kokoro output (24kHz -> 44.1kHz)...")
        target_fs = 44100
        resampled = resample_audio(full_audio, 24000, target_fs).astype(np.float64)
        elapsed = time.monotonic() - t0
        dur = len(resampled) / float(target_fs)
        _vf_log(
            "info",
            f"Kokoro seed synthesis OK in {elapsed:.2f}s (voice={voice}, fs={target_fs}Hz, duration={dur:.2f}s)"
        )
        _emit_progress(progress_cb, 1.0, f"Kokoro seed ready ({dur:.1f}s @ {target_fs}Hz)")
        return resampled, target_fs
    except Exception as e:
        elapsed = time.monotonic() - t0
        msg = f"Kokoro generation error after {elapsed:.1f}s: {type(e).__name__}: {e}"
        _vf_log("error", msg)
        raise RuntimeError(msg)
