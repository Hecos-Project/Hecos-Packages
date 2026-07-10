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
    packages_dir = get_packages_dir()
    src_dirs = [d for d in packages_dir.iterdir() if d.is_dir() and d.name.endswith("_src")]
    
    if not src_dirs:
        log_warn(f"Nessuna cartella '*_src' trovata in {packages_dir}")
        return
        
    print("Pacchetti disponibili:")
    for i, d in enumerate(src_dirs):
        print(f"  {i+1}. {d.name}")
        
    choice = input("\nSeleziona il pacchetto da compilare (0 per annullare): ")
    try:
        idx = int(choice) - 1
        if idx == -1: return
        target_dir = src_dirs[idx]
    except:
        return

def _build_single_package(target_dir, packages_dir):
    manifest_path = target_dir / "hpkg_manifest.toml"
    if not manifest_path.exists():
        log_error(f"{manifest_path.name} non trovato in {target_dir}")
        return False

    # Auto-generate capabilities
    from modules.capabilities_gen import auto_generate_capabilities
    auto_generate_capabilities(target_dir)

    # Parsing manifest
    try:
        manifest = tomllib.loads(manifest_path.read_bytes().decode("utf-8"))
    except Exception as e:
        log_error(f"Errore sintassi TOML in {manifest_path.name}: {e}")
        return False

    log_info(f"Validazione pacchetto '{manifest.get('name', 'Unknown')}' in corso...")
    errors = []
    
    if "id" not in manifest: errors.append("Manca il campo 'id'")
    if "version" not in manifest: errors.append("Manca il campo 'version'")

    if "config_panel" in manifest:
        cp = manifest["config_panel"]
        for key in ["template_file", "js_file", "css_file", "api_routes_file"]:
            if key in cp and not (target_dir / cp[key]).exists():
                errors.append(f"File {key} non trovato: {cp[key]}")

    if "readme" in manifest:
        readme_file = manifest["readme"]
        if not (target_dir / readme_file).exists():
            errors.append(f"File readme '{readme_file}' non trovato")
    else:
        errors.append("Manca il campo obbligatorio 'readme' (inserire almeno un file README.md)")

    if errors:
        log_error("Validazione fallita. Correggi i seguenti errori:")
        for err in errors: log_error(f"  - {err}")
        return False
        
    log_debug("Validazione superata.")

    log_info("Calcolo hash dei file...")
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
    log_info("Generazione payload per firma crittografica...")
    payload_dict = dict(manifest)
    payload_dict.pop("signature", None)
    
    # Questo formato JSON deve essere IDENTICO a quello usato da Hecos in signature.py
    payload_bytes = json.dumps(payload_dict, sort_keys=True, separators=(',', ':')).encode("utf-8")
    
    signature_b64 = sign_payload(payload_bytes)
    if signature_b64:
        manifest["signature"] = signature_b64
        log_info("Firma applicata con successo.")
    else:
        log_warn("Pacchetto non firmato. L'installazione su Hecos potrebbe fallire se richiede pacchetti verificati.")

    # Converti in TOML finale
    try:
        import tomli_w
        final_toml = tomli_w.dumps(manifest).encode("utf-8")
    except ImportError:
        log_debug("tomli_w non trovato, uso il serializzatore TOML custom.")
        final_toml = _json_to_toml(manifest).encode("utf-8")

    pkg_name = f"{manifest['id']}-{manifest['version']}.hpkg"
    out_path = packages_dir / pkg_name
    
    log_info(f"Creazione archivio compresso {pkg_name}...")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("hpkg_manifest.toml", final_toml)
        for full, rel in files_to_pack:
            zf.write(full, rel)
            
    size_kb = out_path.stat().st_size / 1024
    log_info(f"DONE -> {out_path} ({size_kb:.1f} KB)")
    return True

def build_package():
    src_dir = get_src_dir()
    packages_dir = get_packages_dir()
    src_dirs = [d for d in src_dir.iterdir() if d.is_dir() and d.name.endswith("_src")]
    
    if not src_dirs:
        log_warn(f"Nessuna cartella '*_src' trovata in {src_dir}")
        return
        
    print("Pacchetti disponibili:")
    for i, d in enumerate(src_dirs):
        print(f"  {i+1}. {d.name}")
        
    choice = input("\nSeleziona il pacchetto da compilare (0 per annullare): ")
    try:
        idx = int(choice) - 1
        if idx == -1: return
        target_dir = src_dirs[idx]
    except:
        return

    _build_single_package(target_dir, packages_dir)

def build_all_packages():
    src_dir = get_src_dir()
    packages_dir = get_packages_dir()
    src_dirs = [d for d in src_dir.iterdir() if d.is_dir() and d.name.endswith("_src")]
    
    if not src_dirs:
        log_warn(f"Nessuna cartella '*_src' trovata in {src_dir}")
        return

    log_info(f"Trovati {len(src_dirs)} pacchetti da compilare.")
    for target_dir in src_dirs:
        print(f"\n--- Compilazione di {target_dir.name} ---")
        _build_single_package(target_dir, packages_dir)

def get_available_hpkg():
    packages_dir = get_packages_dir()
    hpkg_files = [f for f in packages_dir.glob("*.hpkg")]
    
    if not hpkg_files:
        log_warn(f"Nessun pacchetto .hpkg trovato in {packages_dir}")
        return None
        
    print("Pacchetti disponibili:")
    for i, f in enumerate(hpkg_files):
        print(f"  {i+1}. {f.name}")
        
    choice = input("\nSeleziona il pacchetto (0 per annullare): ")
    try:
        idx = int(choice) - 1
        if idx == -1: return None
        return hpkg_files[idx]
    except:
        return None

def inspect_package():
    pkg_path = get_available_hpkg()
    if not pkg_path: return

    log_info(f"Ispezione pacchetto: {pkg_path.name}")
    try:
        with zipfile.ZipFile(pkg_path, 'r') as zf:
            files = zf.namelist()
            if "hpkg_manifest.toml" not in files:
                log_error("Il pacchetto non contiene 'hpkg_manifest.toml'!")
                return
            
            manifest_bytes = zf.read("hpkg_manifest.toml")
            manifest = tomllib.loads(manifest_bytes.decode("utf-8"))
            
            print("\n--- INFORMAZIONI PACCHETTO ---")
            print(f"ID:      {manifest.get('id', 'N/A')}")
            print(f"Nome:    {manifest.get('name', 'N/A')}")
            print(f"Vers:    {manifest.get('version', 'N/A')}")
            print(f"Autore:  {manifest.get('author', 'N/A')}")
            print("------------------------------")
            
            # Controllo firma
            signature_b64 = manifest.get("signature")
            if signature_b64:
                payload_dict = dict(manifest)
                payload_dict.pop("signature", None)
                payload_bytes = json.dumps(payload_dict, sort_keys=True, separators=(',', ':')).encode("utf-8")
                
                is_valid = verify_signature(payload_bytes, signature_b64)
                if is_valid:
                    log_info("Firma Crittografica: VALIDA")
                else:
                    log_error("Firma Crittografica: NON VALIDA o CHIAVE MANCANTE")
            else:
                log_warn("Firma Crittografica: ASSENTE")

            print("\n--- CONTENUTO FILE ---")
            for f in files:
                info = zf.getinfo(f)
                size = info.file_size
                print(f"  - {f} ({size} bytes)")
            
    except Exception as e:
        log_error(f"Errore durante la lettura del pacchetto: {e}")

def _unpack_single_package(pkg_path, ask_overwrite=True):
    try:
        with zipfile.ZipFile(pkg_path, 'r') as zf:
            if "hpkg_manifest.toml" not in zf.namelist():
                log_error(f"Il pacchetto {pkg_path.name} non contiene 'hpkg_manifest.toml'. Uso nome fallback.")
                out_dir_name = f"{pkg_path.stem}_src"
            else:
                manifest_bytes = zf.read("hpkg_manifest.toml")
                manifest = tomllib.loads(manifest_bytes.decode("utf-8"))
                manifest_id = manifest.get('id', pkg_path.stem)
                out_dir_name = f"{manifest_id}_src"

            out_dir = pkg_path.parent / out_dir_name

            if out_dir.exists():
                if ask_overwrite:
                    log_warn(f"La cartella {out_dir_name} esiste gia'.")
                    ans = input("Vuoi sovrascriverla? (s/N): ")
                    if ans.lower() != 's':
                        return
                else:
                    log_info(f"Sovrascrivo la cartella esistente {out_dir_name}...")

            log_info(f"Decompressione di {pkg_path.name} in {out_dir_name}...")
            zf.extractall(out_dir)
            log_info("Decompressione completata con successo.")
    except Exception as e:
        log_error(f"Errore durante l'estrazione di {pkg_path.name}: {e}")

def unpack_package():
    pkg_path = get_available_hpkg()
    if not pkg_path: return
    _unpack_single_package(pkg_path, ask_overwrite=True)

def unpack_all_packages():
    packages_dir = get_packages_dir()
    hpkg_files = [f for f in packages_dir.glob("*.hpkg")]
    
    if not hpkg_files:
        log_warn(f"Nessun pacchetto .hpkg trovato in {packages_dir}")
        return

    log_info(f"Trovati {len(hpkg_files)} pacchetti da decomprimere.")
    for pkg_path in hpkg_files:
        print(f"\n--- Estrazione di {pkg_path.name} ---")
        _unpack_single_package(pkg_path, ask_overwrite=False)
