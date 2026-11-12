"""
Voice Forge - Full DSP Pipeline Orchestrator
Coordinates source generation, WORLD decomposition, physical vocal tract sculpting,
texture modulation, acoustic equalization, and resynthesis.
"""

import os
import time
import threading
from collections import OrderedDict
from typing import Tuple, Optional, Callable
import numpy as np

from .recipe import VoiceRecipe
from .world_vocoder import vocoder
from .pitch_formant import shift_pitch, adjust_dynamics, warp_formants
from .texture import apply_breathiness, apply_roughness, apply_tremolo
from .acoustic_eq import apply_acoustic_eq
from .morphing import blend_acoustic_features
from .sources_synthetic import generate_fish_seed, generate_kokoro_voice, _vf_log
from .sources_audio import load_audio_file
from .multilang_corpus import get_calibration_sample


class ForgePipeline:
    def __init__(self, source_cache_size: int = 12):
        self.vocoder = vocoder
        self._source_cache: OrderedDict = OrderedDict()
        self._source_cache_size = max(1, int(source_cache_size))
        self._source_cache_lock = threading.Lock()

    def _emit(
        self,
        progress_cb: Optional[Callable[[str, float, str], None]],
        phase: str,
        fraction: float,
        message: str,
    ) -> None:
        if progress_cb is not None:
            try:
                progress_cb(phase, max(0.0, min(1.0, float(fraction))), message)
            except Exception:
                pass

    def _build_source_cache_key(self, recipe: VoiceRecipe, ref_text: str) -> Optional[Tuple]:
        if recipe.source_type == "synthetic_fish":
            seed = int(recipe.source_seed if recipe.source_seed is not None else 42)
            return ("synthetic_fish", ref_text, seed)
        if recipe.source_type == "synthetic_kokoro":
            voice = recipe.source_speaker or "af_heart"
            return ("synthetic_kokoro", ref_text, voice, (recipe.language or "en").lower())
        if recipe.source_type == "file" and recipe.source_file:
            try:
                abs_path = os.path.abspath(recipe.source_file)
                mtime = os.path.getmtime(abs_path)
                return ("file", abs_path, mtime)
            except OSError:
                return None
        return None

    def clear_source_cache(self) -> None:
        with self._source_cache_lock:
            self._source_cache.clear()
        _vf_log("debug", "ForgePipeline source audio cache cleared")

    def resolve_source(
        self,
        recipe: VoiceRecipe,
        custom_audio: Optional[np.ndarray] = None,
        fs: int = 44100,
        progress_cb: Optional[Callable[[str, float, str], None]] = None,
    ) -> Tuple[np.ndarray, int]:
        """Resolves the raw source audio based on recipe configuration (with LRU cache)."""
        if custom_audio is not None:
            self._emit(progress_cb, "source", 1.0, "Using provided custom source buffer")
            return custom_audio, fs

        # Check reference text; fallback to multilingual corpus if empty
        ref_text = recipe.reference_text.strip()
        if not ref_text:
            corpus_sample = get_calibration_sample(recipe.language, "narrative")
            ref_text = corpus_sample["text"]
            recipe.reference_text = ref_text

        cache_key = self._build_source_cache_key(recipe, ref_text)
        if cache_key is not None:
            with self._source_cache_lock:
                if cache_key in self._source_cache:
                    self._source_cache.move_to_end(cache_key)
                    cached_audio, cached_fs = self._source_cache[cache_key]
                    _vf_log("info", f"Source audio cache HIT for {recipe.source_type}")
                    self._emit(progress_cb, "source", 1.0, f"Loaded cached {recipe.source_type} source")
                    return cached_audio.copy(), cached_fs

        self._emit(progress_cb, "source", 0.05, f"Generating source audio ({recipe.source_type})...")
        inner_cb = (
            (lambda frac, msg: self._emit(progress_cb, "source", frac, msg))
            if progress_cb is not None else None
        )

        if recipe.source_type == "synthetic_fish":
            seed = recipe.source_seed if recipe.source_seed is not None else 42
            audio, out_fs = generate_fish_seed(ref_text, seed=seed, progress_cb=inner_cb)

        elif recipe.source_type == "synthetic_kokoro":
            voice = recipe.source_speaker or "af_heart"
            audio, out_fs = generate_kokoro_voice(
                ref_text,
                voice=voice,
                lang_code=recipe.language,
                progress_cb=inner_cb,
            )

        elif recipe.source_type == "file":
            if not recipe.source_file:
                raise ValueError("Source type is 'file' but source_file path is not specified.")
            self._emit(progress_cb, "source", 0.4, f"Loading source file {os.path.basename(recipe.source_file)}...")
            audio, out_fs = load_audio_file(recipe.source_file, target_sr=44100)
            self._emit(progress_cb, "source", 1.0, "Source audio file loaded")

        else:
            raise ValueError(f"Unknown source_type: {recipe.source_type}")

        if cache_key is not None and audio is not None and len(audio) > 0:
            with self._source_cache_lock:
                self._source_cache[cache_key] = (audio.copy(), out_fs)
                self._source_cache.move_to_end(cache_key)
                while len(self._source_cache) > self._source_cache_size:
                    self._source_cache.popitem(last=False)

        return audio, out_fs

    def process(
        self,
        recipe: VoiceRecipe,
        base_audio: Optional[np.ndarray] = None,
        fs: int = 44100,
        progress_cb: Optional[Callable[[str, float, str], None]] = None,
    ) -> Tuple[np.ndarray, int]:
        """
        Executes the full Voice Forge sculpting pipeline on the input recipe.
        Returns the finalized reference audio waveform and sample rate.
        """
        t_start = time.monotonic()
        _vf_log(
            "info",
            f"Pipeline start: recipe='{recipe.name}' (id={recipe.id}), "
            f"source={recipe.source_type}, lang={recipe.language}"
        )

        # 1. Resolve source audio
        audio, sample_rate = self.resolve_source(
            recipe,
            custom_audio=base_audio,
            fs=fs,
            progress_cb=progress_cb,
        )

        # 2. Decompose into acoustic features via WORLD Vocoder
        self._emit(progress_cb, "analyze", 0.15, "Decomposing F0, spectral envelope & aperiodicity (WORLD)...")
        f0, timeaxis, sp, ap = self.vocoder.analyze(audio, fs=sample_rate, use_cache=True)
        self._emit(progress_cb, "analyze", 1.0, "WORLD vocal tract decomposition complete")

        # 3. Optional Spectral Morphing with Source B
        self._emit(progress_cb, "sculpt", 0.1, "Applying vocal tract sculpting & modulation...")
        if recipe.blend_source_file and recipe.blend_ratio > 0.001:
            try:
                audio_b, sr_b = load_audio_file(recipe.blend_source_file, target_sr=sample_rate)
                f0_b, _, sp_b, ap_b = self.vocoder.analyze(audio_b, fs=sr_b, use_cache=True)
                f0, sp, ap = blend_acoustic_features(f0, sp, ap, f0_b, sp_b, ap_b, recipe.blend_ratio)
                _vf_log("debug", f"Applied spectral morph ratio={recipe.blend_ratio:.2f} with '{recipe.blend_source_file}'")
            except Exception as e:
                _vf_log("warning", f"Spectral morph with '{recipe.blend_source_file}' failed, continuing with primary source: {e}")

        # 4. Pitch & Intonation Dynamics
        if abs(recipe.pitch_semitones) > 1e-4:
            f0 = shift_pitch(f0, recipe.pitch_semitones)

        if abs(recipe.pitch_dynamics - 1.0) > 1e-4:
            f0 = adjust_dynamics(f0, recipe.pitch_dynamics)

        self._emit(progress_cb, "sculpt", 0.55, "Warping vocal tract formants & laryngeal texture...")

        # 5. Vocal Tract Length / Formant Warping
        if abs(recipe.vocal_tract_ratio - 1.0) > 1e-4:
            sp = warp_formants(sp, recipe.vocal_tract_ratio)

        # 6. Physical Texture (Breath, Roughness, Tremolo)
        if recipe.breathiness > 1e-4:
            ap = apply_breathiness(ap, recipe.breathiness)

        if recipe.roughness > 1e-4:
            f0, ap = apply_roughness(f0, ap, recipe.roughness)

        if recipe.tremolo > 1e-4:
            f0 = apply_tremolo(f0, timeaxis, recipe.tremolo)

        self._emit(progress_cb, "sculpt", 1.0, "Vocal tract & texture sculpting complete")

        # 7. Resynthesis via WORLD Vocoder
        self._emit(progress_cb, "synth", 0.25, "Resynthesizing waveform via WORLD vocoder...")
        resynth = self.vocoder.synthesize(f0, sp, ap, fs=sample_rate)

        # 8. 4-Band Acoustic Equalization (Body, Warmth, Presence, Air)
        self._emit(progress_cb, "synth", 0.75, "Applying 4-band acoustic equalization...")
        final_audio = apply_acoustic_eq(
            resynth,
            fs=sample_rate,
            body_db=recipe.body_gain_db,
            warmth_db=recipe.warmth_gain_db,
            presence_db=recipe.presence_gain_db,
            air_db=recipe.air_gain_db
        )
        elapsed = time.monotonic() - t_start
        dur = len(final_audio) / float(sample_rate) if sample_rate > 0 else 0.0
        _vf_log("info", f"Pipeline complete in {elapsed:.2f}s (output={dur:.2f}s @ {sample_rate}Hz)")
        self._emit(progress_cb, "synth", 1.0, f"Synthesis complete ({dur:.1f}s @ {sample_rate}Hz)")

        return final_audio, sample_rate


# Global pipeline instance
forge_pipeline = ForgePipeline()
