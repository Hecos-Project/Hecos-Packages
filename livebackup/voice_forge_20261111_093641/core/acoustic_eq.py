"""
Voice Forge - 4-Band Acoustic Equalizer
Professional biquad IIR filters based on Robert Bristow-Johnson's Audio EQ Cookbook.
Shapes chest body (150 Hz), vocal warmth (400 Hz), presence (3 kHz), and air (10 kHz).
"""

import numpy as np
from scipy.signal import sosfilt
from typing import Tuple

def _design_low_shelf(fc: float, gain_db: float, fs: float, q: float = 0.707) -> np.ndarray:
    """Calculates second-order SOS coefficients for a low-shelf filter."""
    if abs(gain_db) < 1e-3:
        return np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float64)

    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * fc / fs
    cos_w0 = np.cos(w0)
    sin_w0 = np.sin(w0)
    alpha = sin_w0 / (2.0 * q)
    two_sqrt_a_alpha = 2.0 * np.sqrt(A) * alpha

    b0 = A * ((A + 1.0) - (A - 1.0) * cos_w0 + two_sqrt_a_alpha)
    b1 = 2.0 * A * ((A - 1.0) - (A + 1.0) * cos_w0)
    b2 = A * ((A + 1.0) - (A - 1.0) * cos_w0 - two_sqrt_a_alpha)
    a0 = (A + 1.0) + (A - 1.0) * cos_w0 + two_sqrt_a_alpha
    a1 = -2.0 * ((A - 1.0) + (A + 1.0) * cos_w0)
    a2 = (A + 1.0) + (A - 1.0) * cos_w0 - two_sqrt_a_alpha

    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]], dtype=np.float64)

def _design_peaking(fc: float, gain_db: float, fs: float, q: float = 1.0) -> np.ndarray:
    """Calculates second-order SOS coefficients for a peaking EQ filter."""
    if abs(gain_db) < 1e-3:
        return np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float64)

    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * fc / fs
    cos_w0 = np.cos(w0)
    sin_w0 = np.sin(w0)
    alpha = sin_w0 / (2.0 * q)

    b0 = 1.0 + alpha * A
    b1 = -2.0 * cos_w0
    b2 = 1.0 - alpha * A
    a0 = 1.0 + alpha / A
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha / A

    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]], dtype=np.float64)

def _design_high_shelf(fc: float, gain_db: float, fs: float, q: float = 0.707) -> np.ndarray:
    """Calculates second-order SOS coefficients for a high-shelf filter."""
    if abs(gain_db) < 1e-3:
        return np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float64)

    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * fc / fs
    cos_w0 = np.cos(w0)
    sin_w0 = np.sin(w0)
    alpha = sin_w0 / (2.0 * q)
    two_sqrt_a_alpha = 2.0 * np.sqrt(A) * alpha

    b0 = A * ((A + 1.0) + (A - 1.0) * cos_w0 + two_sqrt_a_alpha)
    b1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cos_w0)
    b2 = A * ((A + 1.0) + (A - 1.0) * cos_w0 - two_sqrt_a_alpha)
    a0 = (A + 1.0) - (A - 1.0) * cos_w0 + two_sqrt_a_alpha
    a1 = 2.0 * ((A - 1.0) - (A + 1.0) * cos_w0)
    a2 = (A + 1.0) - (A - 1.0) * cos_w0 - two_sqrt_a_alpha

    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]], dtype=np.float64)

def apply_acoustic_eq(
    audio: np.ndarray,
    fs: int = 44100,
    body_db: float = 0.0,
    warmth_db: float = 0.0,
    presence_db: float = 0.0,
    air_db: float = 0.0
) -> np.ndarray:
    """
    Applies the 4-band acoustic equalizer to the synthesized audio:
    - Body: 150 Hz Low Shelf (Chest resonance)
    - Warmth: 400 Hz Peaking (Vocal thickness)
    - Presence: 3000 Hz Peaking (Clarity & intelligibility)
    - Air: 10000 Hz High Shelf (Airiness & breath sheen)
    """
    # If all gains are zero, return copy directly
    if (abs(body_db) < 1e-3 and abs(warmth_db) < 1e-3 and 
        abs(presence_db) < 1e-3 and abs(air_db) < 1e-3):
        return audio.copy()

    # Build cascaded SOS sections
    sos_sections = []
    
    if abs(body_db) >= 1e-3:
        sos_sections.append(_design_low_shelf(150.0, body_db, float(fs)))
    if abs(warmth_db) >= 1e-3:
        sos_sections.append(_design_peaking(400.0, warmth_db, float(fs)))
    if abs(presence_db) >= 1e-3:
        sos_sections.append(_design_peaking(3000.0, presence_db, float(fs)))
    if abs(air_db) >= 1e-3:
        # High shelf cutoff must be below Nyquist
        nyquist = fs / 2.0
        fc_air = min(10000.0, nyquist * 0.9)
        sos_sections.append(_design_high_shelf(fc_air, air_db, float(fs)))

    if not sos_sections:
        return audio.copy()

    sos = np.vstack(sos_sections)
    filtered = sosfilt(sos, audio.astype(np.float64))

    # Soft peak limiter to avoid clipping
    max_val = np.max(np.abs(filtered))
    if max_val > 0.95:
        filtered = filtered * (0.95 / max_val)

    return filtered.astype(np.float32)
