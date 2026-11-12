"""
Voice Forge Core Package
"""
from .recipe import VoiceRecipe
from .multilang_corpus import get_corpus_languages, get_calibration_sample, get_all_samples_for_language
from .world_vocoder import WorldVocoder, vocoder
from .pitch_formant import shift_pitch, adjust_dynamics, warp_formants
from .texture import apply_breathiness, apply_roughness, apply_tremolo
from .acoustic_eq import apply_acoustic_eq
from .morphing import blend_acoustic_features
from .sources_synthetic import generate_fish_seed, generate_kokoro_voice
from .sources_audio import load_audio_file, save_audio_file, trim_silence
from .pipeline import ForgePipeline, forge_pipeline

__all__ = [
    "VoiceRecipe",
    "WorldVocoder",
    "vocoder",
    "shift_pitch",
    "adjust_dynamics",
    "warp_formants",
    "apply_breathiness",
    "apply_roughness",
    "apply_tremolo",
    "apply_acoustic_eq",
    "blend_acoustic_features",
    "generate_fish_seed",
    "generate_kokoro_voice",
    "load_audio_file",
    "save_audio_file",
    "trim_silence",
    "ForgePipeline",
    "forge_pipeline",
    "get_corpus_languages",
    "get_calibration_sample",
    "get_all_samples_for_language",
]
