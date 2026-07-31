import os
import json
import zipfile
from pathlib import Path
from modules.logging_sys import log_info, log_error, log_warn, log_debug
from modules.settings import get_packages_dir, get_src_dir
from modules.crypto import sha256_file, sign_payload, verify_signature

try:
    import tomllib
except ImportError:
    import tomli as tomllib

import tomli_w

def _json_to_toml(d: dict) -> str:
    return tomli_w.dumps(d)

def build_package():
    src_dir = get_src_dir()
    packages_dir = get_packages_dir()
    src_dirs = [d for d in src_dir.rglob("*_src") if d.is_dir()]
    
    if not src_dirs:
        log_warn(f"No '*_src' folder found in {src_dir}")
        return
        
    print("Available packages:")
    from colorama import Fore, Style
    for i, d in enumerate(src_dirs):
        cat = d.parent.name
        label = f"{cat}/{d.name}" if cat != src_dir.name else d.name
        color = Fore.LIGHTCYAN_EX if i % 2 == 0 else Fore.WHITE
        print(f"  {color}{i+1}. {label}{Style.RESET_ALL}")
        
    choice = input("\nSelect the package(s) to build (e.g. 1,6,7 or 0 to cancel): ")
    
    parts = [p.strip() for p in choice.split(",") if p.strip()]
    if not parts or parts == ["0"]:
        return

    targets = []
    for part in parts:
        try:
            idx = int(part) - 1
            if 0 <= idx < len(src_dirs):
                targets.append(src_dirs[idx])
            else:
                from modules.utils import log_warn
                log_warn(f"Invalid selection: {part}")
        except ValueError:
            from modules.utils import log_warn
            log_warn(f"Invalid input format: {part}")

    for target_dir in targets:
        print(f"\n--- Building {target_dir.name} ---")
        _build_single_package(target_dir, packages_dir)

def _build_single_package(target_dir, packages_dir):
    manifest_path = target_dir / "hpkg_manifest.toml"
    if not manifest_path.exists():
        log_error(f"{manifest_path.name} not found in {target_dir}")
        return False

    # Auto-generate capabilities
    from modules.capabilities_gen import auto_generate_capabilities
    auto_generate_capabilities(target_dir)

    # Parsing manifest
    try:
        manifest = tomllib.loads(manifest_path.read_bytes().decode("utf-8"))
    except Exception as e:
        log_error(f"TOML syntax error in {manifest_path.name}: {e}")
        return False

    log_info(f"Validating package '{manifest.get('name', 'Unknown')}'...")
    errors = []
    
    if "id" not in manifest: errors.append("Missing 'id' field")
    if "version" not in manifest: errors.append("Missing 'version' field")

    if "config_panel" in manifest:
        cp = manifest["config_panel"]
        for key in ["template_file", "js_file", "css_file", "api_routes_file"]:
            if key in cp and not (target_dir / cp[key]).exists():
                errors.append(f"File {key} not found: {cp[key]}")

    if "readme" in manifest:
        readme_file = manifest["readme"]
        if not (target_dir / readme_file).exists():
            errors.append(f"Readme file '{readme_file}' not found")
    else:
        errors.append("Missing required 'readme' field (insert at least a README.md file)")

    if errors:
        log_error("Validation failed. Fix the following errors:")
        for err in errors: log_error(f"  - {err}")
        return False
        
    log_debug("Validation passed.")

    log_info("Calculating file hashes...")
    file_hashes = {}
    files_to_pack = []
    
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fname in files:
            full = Path(root) / fname
            rel = full.relative_to(target_dir).as_posix()
            if rel in ("hpkg_manifest.toml", "hpkg_manifest.json"):
                continue
            files_to_pack.append((full, rel))
            file_hashes[rel] = sha256_file(full)

    manifest["file_hashes"] = file_hashes

    # Creazione Payload Bytes per la Firma
    log_info("Generating payload for cryptographic signature...")
    payload_dict = dict(manifest)
    payload_dict.pop("signature", None)
    
    # Questo formato JSON deve essere IDENTICO a quello usato da Hecos in signature.py
    payload_bytes = json.dumps(payload_dict, sort_keys=True, separators=(',', ':')).encode("utf-8")
    
    signature_b64 = sign_payload(payload_bytes)
    if signature_b64:
        manifest["signature"] = signature_b64
        log_info("Signature applied successfully.")
    else:
        log_warn("Unsigned package. Installation on Hecos may fail if it requires verified packages.")

    # Converti in TOML finale
    try:
        import tomli_w
        final_toml = tomli_w.dumps(manifest).encode("utf-8")
    except ImportError:
        log_debug("tomli_w not found, using custom TOML serializer.")
        final_toml = _json_to_toml(manifest).encode("utf-8")

    pkg_name = f"{manifest['id']}-{manifest['version']}.hpkg"
    
    # Determina la cartella di output in base alla categoria del sorgente
    cat = target_dir.parent.name
    # Se il genitore non è 'sources' (quindi è una categoria come 'plugins', 'libraries'), usa quella
    out_dir = packages_dir
    if cat != get_src_dir().name:
        out_dir = packages_dir / cat
        out_dir.mkdir(parents=True, exist_ok=True)
        
    out_path = out_dir / pkg_name
    
    log_info(f"Creating compressed archive {pkg_name}...")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("hpkg_manifest.toml", final_toml)
        for full, rel in files_to_pack:
            zf.write(full, rel)
            
    size_kb = out_path.stat().st_size / 1024
    log_info(f"DONE -> {out_path} ({size_kb:.1f} KB)")
    return True

def build_all_packages():
    src_dir = get_src_dir()
    packages_dir = get_packages_dir()
    src_dirs = [d for d in src_dir.rglob("*_src") if d.is_dir()]
    
    if not src_dirs:
        log_warn(f"No '*_src' folder found in {src_dir}")
        return

    log_info(f"Found {len(src_dirs)} packages to build.")
    for target_dir in src_dirs:
        print(f"\n--- Building {target_dir.name} ---")
        _build_single_package(target_dir, packages_dir)

def _pick_category(base_dir, prompt_label="category"):
    """Discover subdirectories in base_dir and let the user pick one.
    Returns the selected Path, or None if cancelled."""
    cats = sorted([d for d in base_dir.iterdir() if d.is_dir()])
    if not cats:
        log_warn(f"No categories found in {base_dir}")
        return None
    print(f"\nAvailable {prompt_label} categories:")
    for i, c in enumerate(cats):
        count = len(list(c.rglob("*.hpkg"))) if prompt_label == "unpack" else len([d for d in c.rglob("*_src") if d.is_dir()])
        print(f"  {i+1}. {c.name}  ({count} item{'s' if count != 1 else ''})")
    choice = input(f"\nSelect a {prompt_label} category (0 to cancel): ").strip()
    try:
        idx = int(choice) - 1
        if idx == -1:
            return None
        return cats[idx]
    except (ValueError, IndexError):
        return None

def build_by_category():
    """Build all packages belonging to a specific category (e.g. personas, plugins...)."""
    src_dir = get_src_dir()
    packages_dir = get_packages_dir()

    cat_dir = _pick_category(src_dir, "build")
    if not cat_dir:
        return

    src_dirs = [d for d in cat_dir.rglob("*_src") if d.is_dir()]
    if not src_dirs:
        log_warn(f"No '*_src' folders found in category '{cat_dir.name}'")
        return

    log_info(f"Building {len(src_dirs)} package(s) in category '{cat_dir.name}'...")
    ok = failed = 0
    for target_dir in src_dirs:
        print(f"\n--- Building {target_dir.name} ---")
        result = _build_single_package(target_dir, packages_dir)
        if result:
            ok += 1
        else:
            failed += 1
    log_info(f"Category '{cat_dir.name}' — Done: {ok} succeeded, {failed} failed.")

def unpack_by_category():
    """Unpack all .hpkg packages belonging to a specific category."""
    packages_dir = get_packages_dir()

    cat_dir = _pick_category(packages_dir, "unpack")
    if not cat_dir:
        return

    hpkg_files = list(cat_dir.rglob("*.hpkg"))
    if not hpkg_files:
        log_warn(f"No .hpkg files found in category '{cat_dir.name}'")
        return

    log_info(f"Unpacking {len(hpkg_files)} package(s) in category '{cat_dir.name}'...")
    for pkg_path in hpkg_files:
        print(f"\n--- Extracting {pkg_path.name} ---")
        _unpack_single_package(pkg_path, ask_overwrite=False)
    log_info(f"Category '{cat_dir.name}' — Unpack complete.")

def get_available_hpkg():
    packages_dir = get_packages_dir()
    hpkg_files = list(packages_dir.rglob("*.hpkg"))
    
    if not hpkg_files:
        log_warn(f"No .hpkg package found in {packages_dir}")
        return None
        
    print("Available packages:")
    from colorama import Fore, Style
    for i, f in enumerate(hpkg_files):
        color = Fore.LIGHTCYAN_EX if i % 2 == 0 else Fore.WHITE
        cat = f.parent.name
        label = f"{cat}/{f.name}" if cat != packages_dir.name else f.name
        print(f"  {color}{i+1}. {label}{Style.RESET_ALL}")
        
    choice = input("\nSelect the package (0 to cancel): ")
    try:
        idx = int(choice) - 1
        if idx == -1: return None
        return hpkg_files[idx]
    except:
        return None

def inspect_package():
    pkg_path = get_available_hpkg()
    if not pkg_path: return

    log_info(f"Inspecting package: {pkg_path.name}")
    try:
        with zipfile.ZipFile(pkg_path, 'r') as zf:
            files = zf.namelist()
            if "hpkg_manifest.toml" not in files:
                log_error("The package does not contain 'hpkg_manifest.toml'!")
                return
            
            manifest_bytes = zf.read("hpkg_manifest.toml")
            manifest = tomllib.loads(manifest_bytes.decode("utf-8"))
            
            print("\n--- PACKAGE INFORMATION ---")
            print(f"ID:      {manifest.get('id', 'N/A')}")
            print(f"Name:    {manifest.get('name', 'N/A')}")
            print(f"Vers:    {manifest.get('version', 'N/A')}")
            print(f"Author:  {manifest.get('author', 'N/A')}")
            print("------------------------------")
            
            # Controllo firma
            signature_b64 = manifest.get("signature")
            if signature_b64:
                payload_dict = dict(manifest)
                payload_dict.pop("signature", None)
                payload_bytes = json.dumps(payload_dict, sort_keys=True, separators=(',', ':')).encode("utf-8")
                
                is_valid = verify_signature(payload_bytes, signature_b64)
                if is_valid:
                    log_info("Cryptographic Signature: VALID")
                else:
                    log_error("Cryptographic Signature: INVALID or MISSING KEY")
            else:
                log_warn("Cryptographic Signature: MISSING")

            print("\n--- FILE CONTENT ---")
            for f in files:
                info = zf.getinfo(f)
                size = info.file_size
                print(f"  - {f} ({size} bytes)")
            
    except Exception as e:
        log_error(f"Error reading package: {e}")

def _unpack_single_package(pkg_path, ask_overwrite=True):
    try:
        with zipfile.ZipFile(pkg_path, 'r') as zf:
            if "hpkg_manifest.toml" not in zf.namelist():
                log_error(f"Package {pkg_path.name} does not contain 'hpkg_manifest.toml'. Using fallback name.")
                out_dir_name = f"{pkg_path.stem}_src"
            else:
                manifest_bytes = zf.read("hpkg_manifest.toml")
                manifest = tomllib.loads(manifest_bytes.decode("utf-8"))
                manifest_id = manifest.get('id', pkg_path.stem)
                out_dir_name = f"{manifest_id}_src"
            
            # Determina la cartella di destinazione corretta in sources/
            from modules.settings import get_src_dir
            cat = pkg_path.parent.name
            if cat == get_packages_dir().name:
                out_dir = get_src_dir() / out_dir_name
            else:
                out_dir = get_src_dir() / cat / out_dir_name

            if out_dir.exists():
                if ask_overwrite:
                    log_warn(f"Folder {out_dir_name} already exists.")
                    ans = input("Do you want to overwrite it? (y/N): ")
                    if ans.lower() != 'y':
                        return
                else:
                    log_info(f"Overwriting existing folder {out_dir_name}...")

            log_info(f"Unpacking {pkg_path.name} into {out_dir_name}...")
            zf.extractall(out_dir)
            log_info("Unpacking completed successfully.")
    except Exception as e:
        log_error(f"Error extracting {pkg_path.name}: {e}")

def unpack_package():
    pkg_path = get_available_hpkg()
    if not pkg_path: return
    _unpack_single_package(pkg_path, ask_overwrite=True)

def unpack_all_packages():
    packages_dir = get_packages_dir()
    hpkg_files = list(packages_dir.rglob("*.hpkg"))
    
    if not hpkg_files:
        log_warn(f"No .hpkg package found in {packages_dir}")
        return

    log_info(f"Found {len(hpkg_files)} packages to unpack.")
    for pkg_path in hpkg_files:
        print(f"\n--- Extracting {pkg_path.name} ---")
        _unpack_single_package(pkg_path, ask_overwrite=False)
