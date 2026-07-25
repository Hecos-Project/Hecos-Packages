import os
from pathlib import Path
import tomli_w
try:
    import tomllib
except ImportError:
    import tomli as tomllib

SOURCES_DIR = Path(r"C:\Hecos-Packages\sources\personas")

def patch_manifests():
    for d in SOURCES_DIR.iterdir():
        if d.is_dir() and d.name.endswith("_src"):
            manifest_path = d / "hpkg_manifest.toml"
            if manifest_path.exists():
                with open(manifest_path, "rb") as f:
                    data = tomllib.load(f)
                
                original_id = data.get("id")
                # Fix ID to lowercase
                if original_id:
                    new_id = original_id.lower()
                    data["id"] = new_id
                    # Set plugin_dir to the exact folder name containing the persona.yaml
                    # (which is the original CamelCase name)
                    data["plugin_dir"] = original_id
                    
                    with open(manifest_path, "wb") as f:
                        f.write(tomli_w.dumps(data).encode("utf-8"))
                    print(f"Patched {d.name}: id='{new_id}', plugin_dir='{original_id}'")

if __name__ == "__main__":
    patch_manifests()
