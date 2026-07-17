import shutil
from pathlib import Path
from modules.logging_sys import log_info, log_error, log_warn
from modules.settings import get_src_dir, get_hecos_root

def dev_sync_package():
    """
    Sincronizza istantaneamente i file dalla cartella *_src del progetto
    alla cartella di installazione live di Hecos (hecos/hpm/), ignorando
    le dipendenze e i file extra creati a runtime.
    Questo permette uno sviluppo rapidissimo senza dover ricompilare il .hpkg.
    """
    src_dir = get_src_dir()
    hecos_hpm_dir = get_hecos_root() / "hpm"
    
    if not hecos_hpm_dir.exists():
        log_error(f"Live HPM folder not found: {hecos_hpm_dir}")
        return
        
    src_dirs = [d for d in src_dir.iterdir() if d.is_dir() and d.name.endswith("_src")]
    
    if not src_dirs:
        log_warn(f"No '*_src' folder found in {src_dir}")
        return
        
    print("\nPackages available for Development -> Live synchronization:")
    for i, d in enumerate(src_dirs):
        print(f"  {i+1}. {d.name}")
        
    choice = input("\nSelect the package to synchronize (0 to cancel): ")
    try:
        idx = int(choice) - 1
        if idx == -1: return
        target_dir = src_dirs[idx]
    except:
        return

    # Calcola il nome del pacchetto (es. da "reminder_src" a "reminder")
    pkg_id = target_dir.name.replace("_src", "")
    live_pkg_dir = hecos_hpm_dir / pkg_id

    if not live_pkg_dir.exists():
        log_error(f"Package '{pkg_id}' is not currently installed in Hecos.")
        log_warn("You must install the package normally via .hpkg at least once before using Dev Sync.")
        return

    log_info(f"Synchronizing from '{target_dir.name}' to '{live_pkg_dir}'...")
    
    # Copiamo i file usando shutil.copytree che sovrascrive i file esistenti
    # ignorando cartelle speciali come __pycache__
    try:
        shutil.copytree(
            target_dir, 
            live_pkg_dir, 
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git', 'hpkg_manifest.json')
        )
        log_info(f"✅ Synchronization completed! Your changes are now active in the live system.")
        log_info(f"   (Note: you may need to restart Hecos or reload the package from the Package Manager if you modified core Python code).")
    except Exception as e:
        log_error(f"Error during synchronization: {e}")
