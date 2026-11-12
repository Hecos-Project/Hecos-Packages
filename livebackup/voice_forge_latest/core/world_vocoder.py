"""
Voice Forge - WORLD Vocoder Engine
High-fidelity pitch, spectral envelope, and aperiodicity decomposition and resynthesis.
Includes an in-memory feature cache for near-instant slider responsiveness.
"""

import hashlib
import time
import threading
import numpy as np
import pyworld as pw
from typing import Tuple, Dict

from .sources_synthetic import _vf_log


class WorldVocoder:
    def __init__(self, cache_size: int = 32):
        self._cache: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]] = {}
        self._cache_keys = []
        self._cache_size = cache_size
        self._cache_lock = threading.Lock()

    def _hash_audio(self, audio: np.ndarray, fs: int) -> str:
        # Fast hash using sampling and shape
        h = hashlib.sha256()
        h.update(str(fs).encode('utf-8'))
        h.update(str(audio.shape).encode('utf-8'))
        # Sample bytes if audio is large
        if len(audio) > 8000:
            sample = np.concatenate([audio[:2000], audio[len(audio)//2 - 1000 : len(audio)//2 + 1000], audio[-2000:]])
            h.update(sample.tobytes())
        else:
            h.update(audio.tobytes())
        return h.hexdigest()

    def analyze(self, audio: np.ndarray, fs: int = 44100, use_cache: bool = True) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Decomposes audio waveform into F0, timeaxis, spectral envelope (sp), and aperiodicity (ap).
        Audio must be float64 1D array.
        """
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1) if audio.shape[1] <= 8 else audio.squeeze()
        min_samples = max(1024, int(fs * 0.08))
        if len(audio) < min_samples:
            _vf_log("debug", f"Padding ultra-short audio ({len(audio)} -> {min_samples} samples) for WORLD analysis")
            audio = np.pad(audio, (0, min_samples - len(audio)), mode="constant")
        audio = np.ascontiguousarray(audio, dtype=np.float64)

        cache_key = self._hash_audio(audio, fs) if use_cache else None
        if use_cache and cache_key:
            with self._cache_lock:
                if cache_key in self._cache:
                    f0, timeaxis, sp, ap, _ = self._cache[cache_key]
                    _vf_log("debug", f"WORLD feature cache HIT (key={cache_key[:10]}, frames={len(f0)})")
                    # Return deep copies so modifications don't corrupt the cache
                    return f0.copy(), timeaxis.copy(), sp.copy(), ap.copy()

        t0 = time.monotonic()
        # Harvest F0 extraction
        f0, timeaxis = pw.harvest(audio, fs)
        # Stonemask F0 refinement
        f0 = pw.stonemask(audio, f0, timeaxis, fs)
        # Cheaptrick spectral envelope
        sp = pw.cheaptrick(audio, f0, timeaxis, fs)
        # D4C aperiodicity
        ap = pw.d4c(audio, f0, timeaxis, fs)
        elapsed = time.monotonic() - t0
        _vf_log("debug", f"WORLD analyze complete in {elapsed:.2f}s (frames={len(f0)}, fs={fs}Hz)")

        if use_cache and cache_key:
            with self._cache_lock:
                if cache_key not in self._cache:
                    if len(self._cache_keys) >= self._cache_size:
                        oldest = self._cache_keys.pop(0)
                        self._cache.pop(oldest, None)
                    self._cache[cache_key] = (f0, timeaxis, sp, ap, fs)
                    self._cache_keys.append(cache_key)

        return f0.copy(), timeaxis.copy(), sp.copy(), ap.copy()

    def synthesize(self, f0: np.ndarray, sp: np.ndarray, ap: np.ndarray, fs: int = 44100) -> np.ndarray:
        """
        Synthesizes modified acoustic features back into a waveform.
        Ensures arrays are contiguous float64 and normalizes peak output.
        """
        t0 = time.monotonic()
        f0 = np.ascontiguousarray(f0, dtype=np.float64)
        sp = np.ascontiguousarray(sp, dtype=np.float64)
        ap = np.ascontiguousarray(ap, dtype=np.float64)

        y = pw.synthesize(f0, sp, ap, fs)

        # Soft peak limiter to avoid clipping
        max_val = np.max(np.abs(y)) if y.size > 0 else 0.0
        if max_val > 0.95:
            y = y * (0.95 / max_val)

        _vf_log("debug", f"WORLD synthesize complete in {time.monotonic() - t0:.2f}s (samples={len(y)}, fs={fs}Hz)")
        return y.astype(np.float32)

    def clear_cache(self):
        with self._cache_lock:
            self._cache.clear()
            self._cache_keys.clear()
        _vf_log("debug", "WORLD feature cache cleared")

# Global singleton instance for Voice Forge
vocoder = WorldVocoder()
