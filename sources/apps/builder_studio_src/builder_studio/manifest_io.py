
import os
from pathlib import Path
try:
    import tomllib
except ImportError:
    import tomli as tomllib
import tomli_w
from logger import info, error

def load_manifest(src_dir: str) -> dict:
    manifest_path = Path(src_dir) / "hpkg_manifest.toml"
    if not manifest_path.exists():
        return {}
    try:
        return tomllib.loads(manifest_path.read_bytes().decode("utf-8"))
    except Exception as e:
        error(f"Error reading manifest: {e}")
        return {}

def save_manifest(src_dir: str, data: dict) -> bool:
    manifest_path = Path(src_dir) / "hpkg_manifest.toml"
    try:
        manifest_path.write_bytes(tomli_w.dumps(data).encode("utf-8"))
        return True
    except Exception as e:
        error(f"Error saving manifest: {e}")
        return False

import shutil

def list_preview_images(src_dir: str) -> list:
    src_path = Path(src_dir)
    if not src_path.exists():
        return []
    
    images = []
    # Check preview_1.png, preview_2.png, etc.
    for p in src_path.glob("preview_*.png"):
        images.append(p.name)
    
    def extract_num(name):
        try:
            return int(name.replace("preview_", "").replace(".png", ""))
        except:
            return 0
            
    return sorted(images, key=extract_num)

def add_preview_image(src_dir: str, image_path: str = None, file_data = None) -> str:
    src_path = Path(src_dir)
    
    existing = list_preview_images(src_dir)
    next_idx = 1
    if existing:
        try:
            last_num = int(existing[-1].replace("preview_", "").replace(".png", ""))
            next_idx = last_num + 1
        except:
            pass
            
    new_name = f"preview_{next_idx}.png"
    dest_path = src_path / new_name
    
    if image_path:
        shutil.copy2(Path(image_path), dest_path)
    elif file_data:
        file_data.save(str(dest_path))
        
    info(f"Added preview image {new_name} to {src_dir}")
    return new_name

def delete_preview_image(src_dir: str, image_name: str) -> list:
    src_path = Path(src_dir)
    target = src_path / image_name
    
    if target.exists() and target.is_file():
        target.unlink()
        
    # Re-normalize numbering
    existing = list_preview_images(src_dir)
    new_images = []
    
    for i, old_name in enumerate(existing, start=1):
        expected_name = f"preview_{i}.png"
        old_path = src_path / old_name
        new_path = src_path / expected_name
        
        if old_name != expected_name and old_path.exists():
            old_path.rename(new_path)
            
        new_images.append(expected_name)
        
    return new_images
