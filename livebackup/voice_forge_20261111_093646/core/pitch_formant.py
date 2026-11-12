"""
Voice Forge - Pitch & Vocal Tract Sculpting
Accurately shifts musical pitch, intonation dynamics, and vocal tract length (formants).
"""

import numpy as np

def shift_pitch(f0: np.ndarray, semitones: float) -> np.ndarray:
    """
    Shifts fundamental frequency by musical semitones while preserving unvoiced regions.
    semitones: -12.0 to +12.0
    """
    if abs(semitones) < 1e-4:
        return f0.copy()
    factor = 2.0 ** (semitones / 12.0)
    shifted_f0 = np.where(f0 > 0, f0 * factor, 0.0)
    return shifted_f0

def adjust_dynamics(f0: np.ndarray, factor: float) -> np.ndarray:
    """
    Modulates pitch intonation range around the speaker's median log-F0.
    factor = 1.0: normal intonation
    factor = 0.0: flat robotic monotone
    factor > 1.0: expressive, dramatic, or theatric intonation
    """
    if abs(factor - 1.0) < 1e-4:
        return f0.copy()

    voiced = f0 > 0
    if not np.any(voiced):
        return f0.copy()

    res = f0.copy()
    log_f0 = np.log(f0[voiced])
    med_log = np.median(log_f0)
    
    # Expand or compress variations around the median
    mod_log = med_log + factor * (log_f0 - med_log)
    # Clip to physically plausible vocal pitch range (40 Hz to 1200 Hz)
    mod_f0 = np.clip(np.exp(mod_log), 40.0, 1200.0)
    res[voiced] = mod_f0
    return res

def warp_formants(sp: np.ndarray, ratio: float) -> np.ndarray:
    """
    Simulates changes in physical vocal tract length by stretching or compressing
    the spectral envelope frequency axis.
    ratio = 1.0: original vocal tract
    ratio < 1.0: longer vocal tract (giant, deep chest cavity, ogre)
    ratio > 1.0: shorter vocal tract (child, fairy, goblin, small cavity)
    """
    if abs(ratio - 1.0) < 1e-4:
        return sp.copy()

    num_frames, num_bins = sp.shape
    orig_freqs = np.linspace(0.0, 1.0, num_bins)
    warped_freqs = orig_freqs / ratio

    # Resample spectral envelope along the frequency axis
    warped_sp = np.zeros_like(sp)
    for t in range(num_frames):
        warped_sp[t] = np.interp(warped_freqs, orig_freqs, sp[t], right=sp[t, -1])

    return warped_sp
