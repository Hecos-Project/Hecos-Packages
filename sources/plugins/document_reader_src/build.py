#!/usr/bin/env python3
"""
Hecos Document Reader — Autonomous Package Builder (build.py)
Validates manifests, bundles assets, and builds the .hpkg distribution package.
"""

import os
import sys
import json
import zipfile
import hashlib

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = r"C:\Hecos-Packages\packages\plugins"
INDEX_PATH = r"C:\Hecos-Packages\packages\index.json"
FALLBACK_OUTPUT_DIR = os.path.join(SOURCE_DIR, "dist")


def validate_manifests():
    """Verify that manifest.json and hpkg_manifest.toml exist and are valid."""
    manifest_json_path = os.path.join(SOURCE_DIR, "manifest.json")
    toml_path = os.path.join(SOURCE_DIR, "hpkg_manifest.toml")

    if not os.path.isfile(manifest_json_path):
        raise FileNotFoundError(f"Missing manifest.json at {manifest_json_path}")
    if not os.path.isfile(toml_path):
        raise FileNotFoundError(f"Missing hpkg_manifest.toml at {toml_path}")

    with open(manifest_json_path, "r", encoding="utf-8") as f:
        m_data = json.load(f)
    print(f"[OK] manifest.json validated: {m_data.get('id')} v{m_data.get('version')}")

    if tomllib:
        with open(toml_path, "rb") as f:
            t_data = tomllib.load(f)
        print(f"[OK] hpkg_manifest.toml validated: {t_data.get('id')} v{t_data.get('version')}")
    else:
        print("[INFO] tomllib not available, skipping deep TOML syntax parse.")

    return m_data.get("id", "document_reader"), m_data.get("version", "1.0.0")


def build_hpkg(pkg_id: str, version: str) -> str:
    """Bundle the directory into an .hpkg zip file."""
    target_dir = OUTPUT_DIR if os.path.isdir(os.path.dirname(OUTPUT_DIR)) else FALLBACK_OUTPUT_DIR
    os.makedirs(target_dir, exist_ok=True)
    out_hpkg = os.path.join(target_dir, f"{pkg_id}-{version}.hpkg")

    exclude_dirs = {"__pycache__", ".git", "dist", ".vscode", ".idea"}
    exclude_exts = {".pyc", ".pyo", ".pyd"}

    file_count = 0
    with zipfile.ZipFile(out_hpkg, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(SOURCE_DIR):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in exclude_exts or file == ".DS_Store" or file.endswith(".hpkg"):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, SOURCE_DIR).replace("\\", "/")
                zf.write(full_path, rel_path)
                file_count += 1

    print(f"[OK] Bundled {file_count} files into {out_hpkg}")
    return out_hpkg


def compute_sha256(file_path: str) -> str:
    """Compute sha256 checksum of the package."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def update_index(pkg_id: str, size: int, checksum: str):
    """Update package index.json if it exists."""
    if not os.path.isfile(INDEX_PATH):
        return
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            idx = json.load(f)
        for p in idx.get("packages", []):
            if p.get("id") == pkg_id:
                p["size_bytes"] = size
                p["sha256"] = checksum
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(idx, f, indent=2, ensure_ascii=False)
        print(f"[OK] Updated central index.json for {pkg_id}")
    except Exception as e:
        print(f"[!] Warning: Could not update index.json: {e}")


def main():
    print("==================================================")
    print("  Hecos Document Reader -- Autonomous HPKG Builder ")
    print("==================================================")
    pkg_id, version = validate_manifests()
    hpkg_file = build_hpkg(pkg_id, version)
    checksum = compute_sha256(hpkg_file)
    size = os.path.getsize(hpkg_file)
    print(f"[OK] Package Size: {size:,} bytes")
    print(f"[OK] SHA256: {checksum}")
    update_index(pkg_id, size, checksum)
    print("==================================================")
    print(f" BUILD COMPLETE: {hpkg_file}")
    print("==================================================")


if __name__ == "__main__":
    main()
