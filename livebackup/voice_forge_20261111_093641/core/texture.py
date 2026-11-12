"""
Voice Forge - Texture & Physicality Sculpting
Controls breathiness/whisper, vocal roughness/fry/rasp, and physiological vocal tremor.
"""

import numpy as np
from typing import Tuple

def apply_breathiness(ap: np.ndarray, amount: float) -> np.ndarray:
    """
    Increases aperiodic energy in the spectral decomposition.
    Higher amounts turn normal phonation into intimate breathy or whispered speech.
    amount: 0.0 (unmodified) to 1.0 (fully aspirated/whispered)
    """
    if amount <= 1e-4:
        return ap.copy()

    num_frames, num_bins = ap.shape
    # High frequencies naturally exhibit more aperiodicity; create a smooth weighting curve
    freq_weights = np.linspace(0.4, 1.0, num_bins)[None, :]
    
    # Scale aperiodicity towards 1.0 (pure noise)
    mod_ap = ap + (amount * freq_weights * (1.0 - ap))
    return np.clip(mod_ap, 0.0, 1.0)

def apply_roughness(f0: np.ndarray, ap: np.ndarray, amount: float, seed: int = 42) -> Tuple[np.ndarray, np.ndarray]:
    """
    Adds micro-jitter (pitch perturbation) and subharmonic modulation (diplophonia / vocal fry).
    Produces a gritty, raspy, or gravelly vocal texture (demon, witch, aged warrior).
    amount: 0.0 (smooth) to 1.0 (heavy gravel/fry)
    """
    if amount <= 1e-4:
        return f0.copy(), ap.copy()

    rng = np.random.RandomState(seed)
    voiced = f0 > 0
    mod_f0 = f0.copy()
    mod_ap = ap.copy()

    if np.any(voiced):
        # 1. Random micro-jitter on voiced frames (up to +/- 6% at amount=1.0)
        jitter = rng.normal(0.0, 0.05 * amount, size=len(f0))
        # 2. Subharmonic modulation (alternating frames simulating irregular glottal pulse period doubling)
        alt_pulse = np.sin(np.pi * np.arange(len(f0))) * (0.04 * amount)
        
        mod_f0[voiced] = np.maximum(40.0, f0[voiced] * (1.0 + jitter[voiced] + alt_pulse[voiced]))

    # Roughness also introduces slight turbulent aperiodicity in the mid-range
    if amount > 0.05:
        mod_ap = np.clip(mod_ap + (amount * 0.22 * (1.0 - mod_ap)), 0.0, 1.0)

    return mod_f0, mod_ap

def apply_tremolo(f0: np.ndarray, timeaxis: np.ndarray, amount: float, rate_hz: float = 5.5) -> np.ndarray:
    """
    Applies low-frequency physiological pitch tremor (typically 5 to 6 Hz).
    Simulates the involuntary vocal quiver of elderly, frail, or deeply emotional speakers.
    amount: 0.0 (steady) to 1.0 (pronounced tremor)
    """
    if amount <= 1e-4:
        return f0.copy()

    voiced = f0 > 0
    if not np.any(voiced):
        return f0.copy()

    # Modulate F0 with 5.5 Hz sine wave, up to +/- 5% pitch swing
    lfo = np.sin(2.0 * np.pi * rate_hz * timeaxis)
    swing = 0.05 * amount
    mod_f0 = f0.copy()
    mod_f0[voiced] = f0[voiced] * (1.0 + swing * lfo[voiced])
    return mod_f0
