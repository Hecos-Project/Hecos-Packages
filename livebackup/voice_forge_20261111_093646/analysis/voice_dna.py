"""
Voice Forge - Voice DNA Radar Metrics
Computes a normalized 6-dimensional acoustic fingerprint (0 to 100) for radar chart visualization:
1. Pitch (f0 median)
2. Dynamics (f0 variance & expression)
3. Vocal Tract (effective acoustic length / cavity size)
4. Brightness (spectral centroid)
5. Breath (aperiodicity / whisper energy)
6. Roughness (jitter, rasp, subharmonic fry)
"""

from typing import Dict, Any
import numpy as np

def compute_voice_dna(
    f0_stats: Dict[str, float],
    formants: list,
    spectral_centroid_hz: float,
    hnr_db: float,
    recipe_params: Dict[str, Any]
) -> Dict[str, int]:
    """
    Computes 6 normalized scores (0 - 100) combining measured acoustic features
    and applied recipe parameters.
    """
    med_f0 = f0_stats.get("median_hz", 150.0)
    std_f0 = f0_stats.get("std_hz", 25.0)

    # 1. Pitch Axis (60 Hz = 5, 120 Hz = 35, 220 Hz = 65, 380 Hz = 100)
    if med_f0 <= 50.0:
        pitch_score = 5
    elif med_f0 >= 380.0:
        pitch_score = 100
    else:
        pitch_score = int(np.clip(5 + (med_f0 - 50.0) * (95.0 / 330.0), 0, 100))

    # 2. Dynamics Axis (std F0 + recipe pitch_dynamics)
    dyn_param = float(recipe_params.get("pitch_dynamics", 1.0))
    measured_dyn = np.clip((std_f0 / 50.0) * 50.0, 5, 80)
    dynamics_score = int(np.clip(measured_dyn * (dyn_param ** 0.8), 0, 100))

    # 3. Vocal Tract (Cavity Size: 0 = small/child, 50 = average adult, 100 = massive giant)
    tract_ratio = float(recipe_params.get("vocal_tract_ratio", 1.0))
    # ratio 1.4 -> score 10 (child)
    # ratio 1.0 -> score 50 (normal)
    # ratio 0.7 -> score 95 (giant)
    # Linear mapping: score = 50 + (1.0 - ratio) * 150
    tract_score = int(np.clip(50.0 + (1.0 - tract_ratio) * 150.0, 5, 100))

    # 4. Brightness Axis (Spectral Centroid + Presence/Air EQ)
    air_db = float(recipe_params.get("air_gain_db", 0.0))
    presence_db = float(recipe_params.get("presence_gain_db", 0.0))
    # 800 Hz centroid = 10, 3500 Hz centroid = 90
    base_bright = np.clip((spectral_centroid_hz - 600.0) / 3200.0 * 80.0 + 10.0, 10, 85)
    eq_shift = (air_db + presence_db) * 1.5
    brightness_score = int(np.clip(base_bright + eq_shift, 5, 100))

    # 5. Breath Axis (HNR & breathiness parameter)
    breath_param = float(recipe_params.get("breathiness", 0.0))
    # High HNR (25 dB) -> low breath (10). Low HNR (0 dB) -> high breath (90)
    hnr_breath = np.clip((25.0 - hnr_db) / 25.0 * 70.0 + 10.0, 5, 90)
    breath_score = int(np.clip(max(hnr_breath, breath_param * 95.0), 5, 100))

    # 6. Roughness Axis (roughness parameter + micro jitter)
    rough_param = float(recipe_params.get("roughness", 0.0))
    roughness_score = int(np.clip(rough_param * 92.0 + 5.0, 5, 100))

    return {
        "pitch": pitch_score,
        "dynamics": dynamics_score,
        "vocal_tract": tract_score,
        "brightness": brightness_score,
        "breath": breath_score,
        "roughness": roughness_score
    }
