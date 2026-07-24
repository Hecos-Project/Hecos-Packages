import os
import sys
import json
import hashlib
import zipfile
import datetime
from colorama import Fore, Style
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print(f"{Fore.RED}Error: 'tomli' library is required to parse manifests.{Style.RESET_ALL}")
        sys.exit(1)

from pathlib import Path

def generate_store_catalog():
    print(f"\n{Fore.CYAN}--- Store Catalog Generator ---{Style.RESET_ALL}")
    
    builder_dir = Path(__file__).resolve().parent.parent
    packages_dir = (builder_dir.parent / "packages").resolve()
    website_store_dir = (builder_dir.parent.parent / "Hecos-Website" / "store").resolve()
    
    if not packages_dir.exists():
        print(f"{Fore.RED}Packages folder not found: {packages_dir}{Style.RESET_ALL}")
        return
        
    if not website_store_dir.exists():
        print(f"{Fore.RED}Website store folder not found: {website_store_dir}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}The file will be saved in {packages_dir} instead.{Style.RESET_ALL}")
        output_file = packages_dir / "index.json"
    else:
        output_file = website_store_dir / "index.json"

    catalog = {
        "version": "1",
        "catalog_url": "https://hecos-project.github.io/store/index.json",
        "generated_at": datetime.datetime.utcnow().isoformat()[:19] + "Z",
        "packages": []
    }
    
    hpkg_files = list(packages_dir.rglob("*.hpkg"))
    if not hpkg_files:
        print(f"{Fore.YELLOW}No .hpkg files found in {packages_dir}{Style.RESET_ALL}")
        return

    for filepath in hpkg_files:
        filename = filepath.name
        print(f"{Fore.LIGHTBLACK_EX}Analyzing {filename}...{Style.RESET_ALL}")
        
        # Hash e Size
        size = filepath.stat().st_size
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        file_hash = sha256.hexdigest()
        
        # Leggi Manifest dal file zip
        manifest_data = None
        try:
            with zipfile.ZipFile(filepath, "r") as zf:
                for zname in zf.namelist():
                    if zname.endswith("hpkg_manifest.toml"):
                        manifest_content = zf.read(zname).decode("utf-8")
                        manifest_data = tomllib.loads(manifest_content)
                        break
        except Exception as e:
            print(f"{Fore.RED}Error reading {filename}: {e}{Style.RESET_ALL}")
            continue
            
        if not manifest_data:
            print(f"{Fore.RED}hpkg_manifest.toml not found in {filename}{Style.RESET_ALL}")
            continue
            
        pkg_id = manifest_data.get("id") or filename.split("-")[0]

        # ── Preview image logic ───────────────────────────────────────────────
        # Priority:
        #   1. Explicit 'screenshots' list in the manifest TOML
        #   2. Auto-discovered preview_1, preview_2, … (png, jpg, jpeg, gif, webp) inside the package
        #   3. Legacy single preview.png fallback
        #   4. Default Hecos placeholder image
        PREVIEW_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
        BASE_RAW = f"https://raw.githubusercontent.com/Hecos-Project/Hecos-Packages/main/{pkg_id}_src"

        screenshots = manifest_data.get("screenshots", [])
        if not screenshots:
            try:
                with zipfile.ZipFile(filepath, "r") as zf:
                    names_lower = {n.lower(): n for n in zf.namelist()}

                    # Collect all preview_N.* files sorted numerically
                    numbered = {}
                    for lower, orig in names_lower.items():
                        basename = lower.split("/")[-1]  # strip any path prefix
                        if basename.startswith("preview_"):
                            stem, _, ext = basename.partition(".")
                            ext = "." + ext
                            if ext in PREVIEW_EXTS:
                                try:
                                    idx = int(stem.replace("preview_", ""))
                                    numbered[idx] = orig.split("/")[-1]
                                except ValueError:
                                    pass

                    if numbered:
                        # Build URLs for numbered previews, sorted by index
                        screenshots = [
                            f"{BASE_RAW}/{fname}"
                            for _, fname in sorted(numbered.items())
                        ]
                    elif "preview.png" in names_lower:
                        # Legacy single preview.png
                        screenshots = [f"{BASE_RAW}/preview.png"]
                    else:
                        # Final fallback
                        screenshots = ["https://raw.githubusercontent.com/Hecos-Project/Hecos-Packages/main/Hecos_module_Image_preview.png"]
            except Exception:
                screenshots = ["https://raw.githubusercontent.com/Hecos-Project/Hecos-Packages/main/Hecos_module_Image_preview.png"]

        # ── Capabilities block ────────────────────────────────────────────────
        cap = manifest_data.get("capabilities", {})
        capabilities = {
            "llm_tools":       cap.get("llm_tools", []),
            "slash_commands":  cap.get("slash_commands", []),
            "has_widget":      cap.get("has_widget", False),
            "has_config_panel": cap.get("has_config_panel", False),
            "has_api_routes":  cap.get("has_api_routes", False),
            "has_system_calls": cap.get("has_system_calls", False),
            "notes":           cap.get("notes", ""),
        }

        pkg_entry = {
            "id": pkg_id,
            "name": manifest_data.get("name", "Unknown Package"),
            "type": manifest_data.get("type", "plugin"),
            "level": manifest_data.get("level", 5),
            "version": manifest_data.get("version", "1.0.0"),
            "author": manifest_data.get("author", "Unknown"),
            "description": manifest_data.get("description", ""),
            "tags": manifest_data.get("tags", []),
            "download_url": f"https://raw.githubusercontent.com/Hecos-Project/Hecos-Packages/main/packages/{filename}",
            "size_bytes": size,
            "sha256": file_hash,
            "screenshots": screenshots,
            "changelog": manifest_data.get("changelog", "Automatic update generated by the Store Catalog Builder."),
            "homepage": manifest_data.get("homepage", f"https://hecos-project.github.io/store/#{pkg_id}"),
            "fa_icon": manifest_data.get("fa_icon", "fa-box"),
            "featured": manifest_data.get("featured", False),
            "capabilities": capabilities,
            "dependencies": manifest_data.get("dependencies", []),
            "pip_requirements": manifest_data.get("pip_requirements", []),
        }
        
        catalog["packages"].append(pkg_entry)

        print(f" {Fore.GREEN}[OK] Added: {pkg_entry['name']} v{pkg_entry['version']}{Style.RESET_ALL}")
        
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
        
        print(f"{Fore.GREEN}Catalog generated successfully at {output_file}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Found {len(catalog['packages'])} valid packages.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error saving the catalog: {e}{Style.RESET_ALL}")
