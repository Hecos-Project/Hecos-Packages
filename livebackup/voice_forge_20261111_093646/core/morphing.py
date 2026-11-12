"""
Voice Forge - Spectral Morphing & Blending
Performs acoustic timbre interpolation between two voice sources in the WORLD vocoder domain.
"""

import numpy as np
from typing import Tuple

def _resample_features(
    f0: np.ndarray,
    sp: np.ndarray,
    ap: np.ndarray,
    target_len: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Resamples feature frames along the temporal axis to match target_len."""
    curr_len = len(f0)
    if curr_len == target_len:
        return f0, sp, ap

    orig_t = np.linspace(0.0, 1.0, curr_len)
    new_t = np.linspace(0.0, 1.0, target_len)

    # Resample F0
    res_f0 = np.interp(new_t, orig_t, f0)
    # Resample SP (frame by frame across frequency bins)
    num_bins = sp.shape[1]
    res_sp = np.zeros((target_len, num_bins), dtype=sp.dtype)
    for b in range(num_bins):
        res_sp[:, b] = np.interp(new_t, orig_t, sp[:, b])
    # Resample AP
    res_ap = np.zeros((target_len, num_bins), dtype=ap.dtype)
    for b in range(num_bins):
        res_ap[:, b] = np.interp(new_t, orig_t, ap[:, b])

    return res_f0, res_sp, res_ap

def blend_acoustic_features(
    f0_a: np.ndarray, sp_a: np.ndarray, ap_a: np.ndarray,
    f0_b: np.ndarray, sp_b: np.ndarray, ap_b: np.ndarray,
    blend_ratio: float = 0.5
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Interpolates acoustic features between source A and source B.
    blend_ratio = 0.0: 100% source A
    blend_ratio = 1.0: 100% source B
    Uses log-spectral interpolation for natural formant transition.
    """
    alpha = np.clip(blend_ratio, 0.0, 1.0)
    if alpha < 1e-4:
        return f0_a.copy(), sp_a.copy(), ap_a.copy()
    if alpha > 0.9999:
        return f0_b.copy(), sp_b.copy(), ap_b.copy()

    # Align length to source A
    target_len = len(f0_a)
    f0_b_aligned, sp_b_aligned, ap_b_aligned = _resample_features(f0_b, sp_b, ap_b, target_len)

    # 1. Pitch Blend
    voiced_a = f0_a > 0
    voiced_b = f0_b_aligned > 0
    f0_blend = np.zeros_like(f0_a)

    both_voiced = voiced_a & voiced_b
    if np.any(both_voiced):
        log_f0_a = np.log(f0_a[both_voiced])
        log_f0_b = np.log(f0_b_aligned[both_voiced])
        f0_blend[both_voiced] = np.exp((1.0 - alpha) * log_f0_a + alpha * log_f0_b)

    only_a = voiced_a & (~voiced_b)
    if np.any(only_a):
        f0_blend[only_a] = f0_a[only_a]

    only_b = (~voiced_a) & voiced_b
    if np.any(only_b):
        f0_blend[only_b] = f0_b_aligned[only_b]

    # 2. Spectral Envelope Blend in Log-Domain
    log_sp_a = np.log(np.maximum(sp_a, 1e-12))
    log_sp_b = np.log(np.maximum(sp_b_aligned, 1e-12))
    sp_blend = np.exp((1.0 - alpha) * log_sp_a + alpha * log_sp_b)

    # 3. Aperiodicity Blend
    ap_blend = np.clip((1.0 - alpha) * ap_a + alpha * ap_b_aligned, 0.0, 1.0)

    return f0_blend, sp_blend, ap_blend
