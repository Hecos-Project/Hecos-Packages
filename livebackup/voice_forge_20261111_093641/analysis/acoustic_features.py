"""
Voice Forge - Acoustic Features Extraction
Extracts F0 statistics, formant frequencies (F1-F4), spectral centroid, and HNR.
"""

from typing import Dict, Any, List, Tuple
import numpy as np
from scipy.signal import find_peaks

def extract_f0_stats(f0: np.ndarray) -> Dict[str, float]:
    """Calculates fundamental frequency statistics from voiced frames."""
    voiced = f0[f0 > 0]
    if len(voiced) == 0:
        return {
            "median_hz": 0.0,
            "mean_hz": 0.0,
            "min_hz": 0.0,
            "max_hz": 0.0,
            "std_hz": 0.0
        }

    return {
        "median_hz": round(float(np.median(voiced)), 1),
        "mean_hz": round(float(np.mean(voiced)), 1),
        "min_hz": round(float(np.min(voiced)), 1),
        "max_hz": round(float(np.max(voiced)), 1),
        "std_hz": round(float(np.std(voiced)), 1)
    }

def estimate_formants(sp: np.ndarray, fs: int = 44100) -> List[float]:
    """
    Estimates the dominant vocal tract formants (F1, F2, F3, F4) in Hz
    from the average spectral envelope of voiced frames.
    """
    num_frames, num_bins = sp.shape
    avg_sp = np.mean(sp, axis=0)
    # Convert to log magnitude (dB)
    log_sp = 10.0 * np.log10(np.maximum(avg_sp, 1e-12))
    
    # Smooth slightly to find true vocal tract resonance peaks
    window_len = max(5, num_bins // 64)
    kernel = np.ones(window_len) / window_len
    smoothed = np.convolve(log_sp, kernel, mode="same")

    # Find peaks
    peaks, properties = find_peaks(smoothed, distance=num_bins // 32, prominence=1.5)
    
    # Map peak bin indices to frequency in Hz (0 to Nyquist)
    freqs = peaks * (fs / 2.0) / (num_bins - 1)
    
    # Filter to typical human speech formant range (200 Hz to 4500 Hz)
    vocal_formants = [round(float(f), 1) for f in freqs if 200.0 <= f <= 4500.0]
    
    # Default fallbacks if fewer than 4 formants are detected
    defaults = [500.0, 1500.0, 2500.0, 3500.0]
    while len(vocal_formants) < 4:
        vocal_formants.append(defaults[len(vocal_formants)])

    return vocal_formants[:4]

def calculate_spectral_centroid(audio: np.ndarray, fs: int = 44100) -> float:
    """Calculates the spectral centroid (center of mass of the spectrum) in Hz."""
    if audio is None or len(audio) == 0:
        return 0.0

    n_fft = 2048
    if len(audio) < n_fft:
        audio = np.pad(audio, (0, n_fft - len(audio)), mode="constant")
    hop = 512
    # Compute power spectrum
    num_frames = max(1, (len(audio) - n_fft) // hop)
    centroids = []
    
    freqs = np.linspace(0.0, fs / 2.0, n_fft // 2 + 1)
    win = np.hanning(n_fft)
    
    for i in range(num_frames):
        start = i * hop
        frame = audio[start : start + n_fft]
        if len(frame) < n_fft:
            frame = np.pad(frame, (0, n_fft - len(frame)), mode="constant")
        frame = frame * win
        mag = np.abs(np.fft.rfft(frame))
        sum_mag = np.sum(mag)
        if sum_mag > 1e-6:
            centroids.append(np.sum(freqs * mag) / sum_mag)

    if not centroids:
        return 0.0

    return round(float(np.mean(centroids)), 1)

def calculate_hnr(ap: np.ndarray) -> float:
    """
    Estimates average Harmonics-to-Noise Ratio (HNR in dB) from WORLD aperiodicity.
    ap close to 0 -> high HNR (> 25 dB)
    ap close to 1 -> low HNR (< 5 dB)
    """
    if ap is None or getattr(ap, "size", 0) == 0:
        return 0.0
    mean_ap = np.mean(ap)
    clamped_ap = np.clip(mean_ap, 1e-4, 0.9999)
    # HNR = 10 * log10((1 - AP) / AP)
    hnr_db = 10.0 * np.log10((1.0 - clamped_ap) / clamped_ap)
    return round(float(hnr_db), 1)
