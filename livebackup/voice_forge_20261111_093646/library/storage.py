"""
Voice Forge - File Storage & Directory Management
Manages recipes, temporary preview audio files, and exported voice clone references.
"""

import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

try:
    from ..core.recipe import VoiceRecipe
except (ImportError, ValueError):
    from core.recipe import VoiceRecipe

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PACKAGE_ROOT / "data"
RECIPES_DIR = DATA_DIR / "recipes"
PREVIEWS_DIR = DATA_DIR / "previews"
BAKED_DIR = DATA_DIR / "baked"
HECOS_VOICE_CLONES_DIR = Path(r"c:\Hecos\hecos\assets\voice_clones")

def ensure_directories():
    """Ensures all necessary local storage directories exist."""
    RECIPES_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    BAKED_DIR.mkdir(parents=True, exist_ok=True)
    if not HECOS_VOICE_CLONES_DIR.exists():
        HECOS_VOICE_CLONES_DIR.mkdir(parents=True, exist_ok=True)

ensure_directories()

def sanitize_recipe_id(recipe_id: str) -> str:
    """Normalizes a recipe ID to filesystem-safe characters."""
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "_", os.path.basename(str(recipe_id or "").strip()))
    return cleaned.strip("_")


def generate_custom_recipe_id(name: str) -> str:
    """Generates a unique custom recipe ID prefixed with 'custom_'."""
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "timbre").lower()).strip("_")[:28] or "timbre"
    return f"custom_{slug}_{uuid.uuid4().hex[:6]}"


def save_recipe(recipe: VoiceRecipe) -> Path:
    """Saves a VoiceRecipe to JSON file."""
    ensure_directories()
    clean_id = sanitize_recipe_id(recipe.id) or generate_custom_recipe_id(recipe.name)
    recipe.id = clean_id
    now_iso = datetime.utcnow().isoformat()
    if not recipe.created_at:
        recipe.created_at = now_iso
    recipe.updated_at = now_iso

    file_path = RECIPES_DIR / f"{clean_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(recipe.model_dump_json(indent=2))
    return file_path


def load_recipe(recipe_id: str) -> Optional[VoiceRecipe]:
    """Loads a VoiceRecipe by ID from user data."""
    clean_id = sanitize_recipe_id(recipe_id)
    if not clean_id:
        return None
    file_path = RECIPES_DIR / f"{clean_id}.json"
    if not file_path.is_file():
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return VoiceRecipe(**data)
    except Exception:
        return None


def rename_recipe(recipe_id: str, new_name: str) -> Optional[VoiceRecipe]:
    """Renames an existing custom user recipe in RECIPES_DIR."""
    clean_name = (new_name or "").strip()
    if not clean_name:
        return None
    recipe = load_recipe(recipe_id)
    if not recipe:
        return None
    recipe.name = clean_name
    save_recipe(recipe)
    return recipe


def list_user_recipes() -> List[Dict[str, Any]]:
    """Lists all saved custom user recipes."""
    ensure_directories()
    results = []
    for p in RECIPES_DIR.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
                results.append({
                    "id": d.get("id", p.stem),
                    "name": d.get("name", p.stem),
                    "description": d.get("description", ""),
                    "category": "custom",
                    "language": d.get("language", "en"),
                    "tags": d.get("tags", []),
                    "is_builtin": False,
                    "updated_at": d.get("updated_at", "")
                })
        except Exception:
            continue
    results.sort(key=lambda x: x.get("name", "").lower())
    return results


def delete_recipe(recipe_id: str) -> bool:
    """Deletes a custom recipe."""
    clean_id = sanitize_recipe_id(recipe_id)
    if not clean_id:
        return False
    file_path = RECIPES_DIR / f"{clean_id}.json"
    if file_path.is_file():
        file_path.unlink()
        return True
    return False

def clean_old_previews(max_age_seconds: int = 3600):
    """Deletes preview WAV files older than 1 hour to conserve disk space."""
    ensure_directories()
    now = datetime.utcnow().timestamp()
    for p in PREVIEWS_DIR.glob("*.wav"):
        try:
            if now - p.stat().st_mtime > max_age_seconds:
                p.unlink()
        except Exception:
            pass
