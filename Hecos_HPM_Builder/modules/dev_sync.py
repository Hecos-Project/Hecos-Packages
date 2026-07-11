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
        log_error(f"Cartella HPM live non trovata: {hecos_hpm_dir}")
        return
        
    src_dirs = [d for d in src_dir.iterdir() if d.is_dir() and d.name.endswith("_src")]
    
    if not src_dirs:
        log_warn(f"Nessuna cartella '*_src' trovata in {src_dir}")
        return
        
    print("\nPacchetti disponibili per la sincronizzazione Sviluppo -> Live:")
    for i, d in enumerate(src_dirs):
        print(f"  {i+1}. {d.name}")
        
    choice = input("\nSeleziona il pacchetto da sincronizzare (0 per annullare): ")
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
        log_error(f"Il pacchetto '{pkg_id}' non è attualmente installato in Hecos.")
        log_warn("Devi installare il pacchetto normalmente via .hpkg almeno una volta prima di usare il Dev Sync.")
        return

    log_info(f"Sincronizzazione in corso da '{target_dir.name}' a '{live_pkg_dir}'...")
    
    # Copiamo i file usando shutil.copytree che sovrascrive i file esistenti
    # ignorando cartelle speciali come __pycache__
    try:
        shutil.copytree(
            target_dir, 
            live_pkg_dir, 
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git', 'hpkg_manifest.json')
        )
        log_info(f"✅ Sincronizzazione completata! Le tue modifiche sono ora attive nel sistema live.")
        log_info(f"   (Nota: potrebbe essere necessario riavviare Hecos o ricaricare il pacchetto dal Package Manager se hai modificato codice Python core).")
    except Exception as e:
        log_error(f"Errore durante la sincronizzazione: {e}")
