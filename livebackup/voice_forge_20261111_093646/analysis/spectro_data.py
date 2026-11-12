"""
Voice Forge - Spectrogram & Visualization Data Generator
Produces downsampled Mel-spectrograms, pitch contours, and spectral envelopes
formatted for HTML5 Canvas rendering.
"""

from typing import Dict, Any, List
import numpy as np

def _hz_to_mel(hz: float) -> float:
    return 2595.0 * np.log10(1.0 + hz / 700.0)

def _mel_to_hz(mel: float) -> float:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

def _get_mel_filterbank(n_mels: int, n_fft: int, fs: int) -> np.ndarray:
    """Builds a simple triangular Mel filterbank matrix."""
    low_mel = _hz_to_mel(50.0)
    high_mel = _hz_to_mel(fs / 2.0)
    mel_points = np.linspace(low_mel, high_mel, n_mels + 2)
    hz_points = _mel_to_hz(mel_points)
    bin_points = np.floor((n_fft + 1) * hz_points / fs).astype(int)

    filters = np.zeros((n_mels, n_fft // 2 + 1))
    for m in range(1, n_mels + 1):
        f_m_minus = bin_points[m - 1]
        f_m = bin_points[m]
        f_m_plus = bin_points[m + 1]

        for k in range(f_m_minus, f_m):
            if f_m != f_m_minus:
                filters[m - 1, k] = (k - bin_points[m - 1]) / (f_m - f_m_minus)
        for k in range(f_m, f_m_plus):
            if f_m_plus != f_m:
                filters[m - 1, k] = (bin_points[m + 1] - k) / (f_m_plus - f_m)

    return filters

def generate_spectrogram_data(
    audio: np.ndarray,
    fs: int = 44100,
    f0: np.ndarray = None,
    sp: np.ndarray = None,
    n_mels: int = 48,
    target_time_steps: int = 120
) -> Dict[str, Any]:
    """
    Computes a normalized Mel-spectrogram matrix, pitch contour, and spectral envelope
    optimized for fast JSON transfer and smooth Canvas rendering.
    """
    if len(audio) == 0:
        return {"mel_matrix": [], "pitch_contour": [], "spectral_curve": []}

    n_fft = 1024
    hop_len = max(256, len(audio) // target_time_steps)
    mel_filters = _get_mel_filterbank(n_mels, n_fft, fs)

    # Compute STFT
    num_frames = (len(audio) - n_fft) // hop_len
    if num_frames <= 0:
        return {"mel_matrix": [], "pitch_contour": [], "spectral_curve": []}

    frames = []
    window = np.hanning(n_fft)
    for i in range(num_frames):
        start = i * hop_len
        chunk = audio[start : start + n_fft] * window
        mag = np.abs(np.fft.rfft(chunk))
        mel_energy = np.dot(mel_filters, mag)
        frames.append(mel_energy)

    mel_matrix = np.array(frames) # (num_frames, n_mels)
    # Convert to log scale (dB)
    log_mel = 10.0 * np.log10(np.maximum(mel_matrix, 1e-8))
    # Normalize 0.0 to 1.0 for web UI canvas
    min_db = np.min(log_mel)
    max_db = np.max(log_mel)
    if max_db > min_db:
        norm_mel = (log_mel - min_db) / (max_db - min_db)
    else:
        norm_mel = np.zeros_like(log_mel)

    # Resample or downsample pitch contour to match spectrogram frames
    pitch_contour = []
    if f0 is not None and len(f0) > 0:
        orig_indices = np.linspace(0, len(f0) - 1, num_frames)
        sampled_f0 = np.interp(orig_indices, np.arange(len(f0)), f0)
        pitch_contour = [round(float(v), 1) if v > 0 else 0.0 for v in sampled_f0]

    # Spectral envelope curve (frequency slice)
    spectral_curve = []
    if sp is not None and len(sp) > 0:
        avg_sp = np.mean(sp, axis=0)
        # Downsample to 64 points for compact display
        num_sp_bins = len(avg_sp)
        downsample_bins = np.linspace(0, num_sp_bins - 1, 64).astype(int)
        curve_db = 10.0 * np.log10(np.maximum(avg_sp[downsample_bins], 1e-10))
        # Normalize curve
        c_min = np.min(curve_db)
        c_max = np.max(curve_db)
        if c_max > c_min:
            norm_curve = (curve_db - c_min) / (c_max - c_min)
        else:
            norm_curve = np.zeros_like(curve_db)
        spectral_curve = [round(float(val), 3) for val in norm_curve]

    # Transpose mel_matrix so rows = frequency bins (bottom to top), cols = time
    # Round to 2 decimal places to minimize JSON size
    compact_mel = [[round(float(norm_mel[t, m]), 2) for t in range(num_frames)] for m in range(n_mels)]

    return {
        "mel_matrix": compact_mel,
        "num_frames": int(num_frames),
        "num_mels": int(n_mels),
        "pitch_contour": pitch_contour,
        "spectral_curve": spectral_curve
    }
