"""
Voice Forge - Presets Manager & Voice Profile Baker
Coordinates loading built-in/custom presets and baking recipes into finalized voice references.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np

try:
    from ..core.recipe import VoiceRecipe
    from ..core.pipeline import forge_pipeline
    from ..core.sources_audio import save_audio_file
    from ..core.sources_synthetic import _vf_log
    from ..analysis.acoustic_features import extract_f0_stats, estimate_formants, calculate_spectral_centroid, calculate_hnr
    from ..analysis.spectro_data import generate_spectrogram_data
    from ..analysis.voice_dna import compute_voice_dna
    from .storage import (
        PACKAGE_ROOT, BAKED_DIR, RECIPES_DIR, HECOS_VOICE_CLONES_DIR,
        save_recipe, load_recipe, rename_recipe, delete_recipe,
        list_user_recipes, sanitize_recipe_id, generate_custom_recipe_id
    )
    from .fish_registry import register_fish_preset, rename_fish_preset
except (ImportError, ValueError):
    from core.recipe import VoiceRecipe
    from core.pipeline import forge_pipeline
    from core.sources_audio import save_audio_file
    from core.sources_synthetic import _vf_log
    from analysis.acoustic_features import extract_f0_stats, estimate_formants, calculate_spectral_centroid, calculate_hnr
    from analysis.spectro_data import generate_spectrogram_data
    from analysis.voice_dna import compute_voice_dna
    from library.storage import (
        PACKAGE_ROOT, BAKED_DIR, RECIPES_DIR, HECOS_VOICE_CLONES_DIR,
        save_recipe, load_recipe, rename_recipe, delete_recipe,
        list_user_recipes, sanitize_recipe_id, generate_custom_recipe_id
    )
    from library.fish_registry import register_fish_preset, rename_fish_preset

PRESETS_DIR = PACKAGE_ROOT / "presets"
BASE_PRESETS_DIR = PRESETS_DIR / "base"
CINEMATIC_PRESETS_DIR = PRESETS_DIR / "cinematic"

def is_builtin_preset(recipe_id: str) -> bool:
    """Returns True if recipe_id corresponds to a bundled Base or Cinematic preset."""
    clean_id = sanitize_recipe_id(recipe_id)
    if not clean_id:
        return False
    return (
        (BASE_PRESETS_DIR / f"{clean_id}.json").is_file()
        or (CINEMATIC_PRESETS_DIR / f"{clean_id}.json").is_file()
    )


def _load_dir_recipes(directory: Path, default_category: str) -> List[Dict[str, Any]]:
    results = []
    if not directory.exists():
        return results
    for p in directory.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
                results.append({
                    "id": d.get("id", p.stem),
                    "name": d.get("name", p.stem),
                    "description": d.get("description", ""),
                    "category": d.get("category", default_category),
                    "language": d.get("language", "en"),
                    "tags": d.get("tags", []),
                    "is_builtin": True,
                    "file_path": str(p)
                })
        except Exception:
            continue
    results.sort(key=lambda x: x.get("name", "").lower())
    return results

def get_all_presets_meta() -> Dict[str, List[Dict[str, Any]]]:
    """Returns metadata for all available presets categorized."""
    return {
        "base": _load_dir_recipes(BASE_PRESETS_DIR, "base"),
        "cinematic": _load_dir_recipes(CINEMATIC_PRESETS_DIR, "cinematic"),
        "custom": list_user_recipes()
    }

def get_recipe_by_id(recipe_id: str, prefer_custom: bool = False) -> Optional[VoiceRecipe]:
    """Finds and loads a recipe by ID across built-in and custom user presets."""
    clean_id = sanitize_recipe_id(recipe_id)
    if not clean_id:
        return None

    if prefer_custom:
        user_recipe = load_recipe(clean_id)
        if user_recipe:
            return user_recipe

    # Built-in Base presets (immutable canonical defaults)
    base_file = BASE_PRESETS_DIR / f"{clean_id}.json"
    if base_file.is_file():
        try:
            with open(base_file, "r", encoding="utf-8") as f:
                return VoiceRecipe(**json.load(f))
        except Exception:
            pass

    # Built-in Cinematic presets (immutable canonical defaults)
    cine_file = CINEMATIC_PRESETS_DIR / f"{clean_id}.json"
    if cine_file.is_file():
        try:
            with open(cine_file, "r", encoding="utf-8") as f:
                return VoiceRecipe(**json.load(f))
        except Exception:
            pass

    # Custom user recipes
    return load_recipe(clean_id)


def save_custom_recipe(recipe: VoiceRecipe, save_as_new: bool = False):
    """Persists a user custom preset, generating a new custom ID if needed to protect built-ins."""
    if save_as_new or not recipe.id or is_builtin_preset(recipe.id):
        recipe.id = generate_custom_recipe_id(recipe.name)
        recipe.created_at = None
    recipe.category = "custom"
    file_path = save_recipe(recipe)
    _vf_log("info", f"Saved custom preset '{recipe.name}' (id={recipe.id}, save_as_new={save_as_new})")
    return recipe, file_path


def rename_custom_recipe(recipe_id: str, new_name: str) -> Optional[VoiceRecipe]:
    """Renames a custom user recipe (plus baked metadata and Fish registry key if present)."""
    clean_id = sanitize_recipe_id(recipe_id)
    old = load_recipe(clean_id)
    if not old:
        return None
    old_name = old.name
    updated = rename_recipe(clean_id, new_name)
    if not updated:
        return None

    meta_file = BAKED_DIR / clean_id / "meta.json"
    if meta_file.is_file():
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            meta["name"] = updated.name
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception:
            pass

    rename_fish_preset(old_name, updated.name)
    _vf_log("info", f"Renamed custom preset '{old_name}' -> '{updated.name}' (id={clean_id})")
    return updated


def delete_custom_recipe(recipe_id: str) -> bool:
    """Deletes a custom recipe from user recipes directory."""
    clean_id = sanitize_recipe_id(recipe_id)
    deleted = delete_recipe(clean_id)
    if deleted:
        _vf_log("info", f"Deleted custom preset id={clean_id}")
    return deleted

def bake_voice_profile(
    recipe: VoiceRecipe,
    register_to_audio_config: bool = True,
    base_audio: Optional[np.ndarray] = None,
    progress_cb: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes the full pipeline, bakes reference audio + text, exports to Hecos voice_clones,
    registers into audio.yaml, and extracts complete Voice DNA metrics.
    """
    _vf_log("info", f"Baking voice profile: id={recipe.id}, name='{recipe.name}', register={register_to_audio_config}")

    # 1. Process DSP
    audio, fs = forge_pipeline.process(recipe, base_audio=base_audio, progress_cb=progress_cb)

    def _cb(phase: str, frac: float, msg: str) -> None:
        if progress_cb is not None:
            try:
                progress_cb(phase, frac, msg)
            except Exception:
                pass

    # 2. Prepare target directories
    _cb("register", 0.15, "Exporting reference WAV and transcript files...")
    baked_profile_dir = BAKED_DIR / recipe.id
    baked_profile_dir.mkdir(parents=True, exist_ok=True)

    # 3. Save reference WAV and TXT inside package
    local_wav = baked_profile_dir / "reference.wav"
    local_txt = baked_profile_dir / "reference.txt"
    save_audio_file(audio, str(local_wav), fs=fs)
    with open(local_txt, "w", encoding="utf-8") as f:
        f.write(recipe.reference_text.strip())

    # 4. Only persist to custom recipes directory if this is already a custom profile
    #    (never auto-clone built-in Base/Cinematic presets into My Custom Profiles on bake)
    if recipe.category == "custom" and not is_builtin_preset(recipe.id):
        save_recipe(recipe)

    # 5. Export to Hecos voice clones directory
    hecos_wav_filename = f"{recipe.id}.wav"
    hecos_txt_filename = f"{recipe.id}.txt"
    hecos_wav_path = HECOS_VOICE_CLONES_DIR / hecos_wav_filename
    hecos_txt_path = HECOS_VOICE_CLONES_DIR / hecos_txt_filename

    shutil.copyfile(str(local_wav), str(hecos_wav_path))
    shutil.copyfile(str(local_txt), str(hecos_txt_path))
    _vf_log("debug", f"Exported voice clone assets to {hecos_wav_path}")

    # 6. Extract acoustic features & Voice DNA
    _cb("register", 0.55, "Computing Voice DNA metrics & spectrogram...")
    f0, timeaxis, sp, ap = forge_pipeline.vocoder.analyze(audio, fs=fs, use_cache=True)
    f0_stats = extract_f0_stats(f0)
    formants = estimate_formants(sp, fs=fs)
    centroid = calculate_spectral_centroid(audio, fs=fs)
    hnr = calculate_hnr(ap)
    dna = compute_voice_dna(f0_stats, formants, centroid, hnr, recipe.model_dump())
    spectro_data = generate_spectrogram_data(audio, fs=fs, f0=f0, sp=sp)

    # 7. Register in audio.yaml if requested
    registered = False
    if register_to_audio_config:
        _cb("register", 0.85, "Registering Fish Speech voice preset in audio.yaml...")
        registered = register_fish_preset(
            preset_name=recipe.name,
            reference_audio_filename=hecos_wav_filename,
            reference_text=recipe.reference_text,
            inference_preset="Standard & Balanced"
        )

    meta = {
        "id": recipe.id,
        "name": recipe.name,
        "language": recipe.language,
        "reference_text": recipe.reference_text,
        "reference_audio_file": hecos_wav_filename,
        "registered_in_audio_yaml": registered,
        "f0_stats": f0_stats,
        "formants": formants,
        "spectral_centroid_hz": centroid,
        "hnr_db": hnr,
        "voice_dna": dna,
        "spectrogram": spectro_data
    }

    meta_file = baked_profile_dir / "meta.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    _vf_log("info", f"Voice profile baked cleanly: id={recipe.id}, name='{recipe.name}', registered={registered}")
    if progress_cb is not None:
        try:
            progress_cb("register", 1.0, f"Voice '{recipe.name}' baked and ready")
        except Exception:
            pass

    return meta
