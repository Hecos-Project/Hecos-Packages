"""
Voice Forge - Audio File Source & Processing
Loads, trims silence, resamples to 44.1kHz, and normalizes audio files.
"""

import os
from pathlib import Path
from typing import Tuple, Optional
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
import math

def trim_silence(audio: np.ndarray, fs: int, threshold_db: float = -45.0, pad_ms: int = 50) -> np.ndarray:
    """Trims leading and trailing silence based on energy threshold."""
    if len(audio) == 0:
        return audio

    threshold_amp = 10.0 ** (threshold_db / 20.0)
    frame_len = int(fs * 0.02) # 20ms frame
    hop = frame_len // 2

    # Calculate frame RMS
    num_frames = (len(audio) - frame_len) // hop
    if num_frames <= 0:
        return audio

    energies = []
    for i in range(num_frames):
        start = i * hop
        frame = audio[start : start + frame_len]
        rms = np.sqrt(np.mean(frame ** 2))
        energies.append(rms)

    energies = np.array(energies)
    active = np.where(energies > threshold_amp)[0]
    if len(active) == 0:
        return audio

    start_frame = max(0, active[0])
    end_frame = min(num_frames, active[-1] + 1)

    pad_samples = int(fs * (pad_ms / 1000.0))
    start_sample = max(0, start_frame * hop - pad_samples)
    end_sample = min(len(audio), end_frame * hop + frame_len + pad_samples)

    return audio[start_sample:end_sample]

def resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """High quality polyphase resampling."""
    if orig_sr == target_sr:
        return audio
    gcd = math.gcd(orig_sr, target_sr)
    up = target_sr // gcd
    down = orig_sr // gcd
    return resample_poly(audio, up, down)

def load_audio_file(file_path: str, target_sr: int = 44100, trim: bool = True) -> Tuple[np.ndarray, int]:
    """
    Loads an audio file (WAV, MP3, FLAC, OGG), converts to mono float64,
    resamples to target_sr, and normalizes.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    audio, sr = sf.read(str(path))
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    audio = audio.astype(np.float64)

    if trim:
        audio = trim_silence(audio, sr)

    if sr != target_sr:
        audio = resample_audio(audio, sr, target_sr)
        sr = target_sr

    # RMS normalization to -20 dBFS
    rms = np.sqrt(np.mean(audio ** 2))
    if rms > 1e-5:
        target_rms = 10.0 ** (-20.0 / 20.0)
        audio = audio * (target_rms / rms)

    # Peak limit
    max_peak = np.max(np.abs(audio))
    if max_peak > 0.95:
        audio = audio * (0.95 / max_peak)

    return audio, sr

def save_audio_file(audio: np.ndarray, file_path: str, fs: int = 44100, subtype: str = "PCM_16"):
    """Saves audio array to WAV."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio.astype(np.float32), fs, subtype=subtype)
