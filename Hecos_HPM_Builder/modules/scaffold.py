import os
from modules.logging_sys import log_info, log_error, log_warn
from modules.settings import get_packages_dir

def scaffold_package():
    packages_dir = get_packages_dir()
    
    pkg_id = input("1. Inserisci il Package ID (es. my_plugin, no spazi): ").strip().lower()
    if not pkg_id: 
        log_warn("Nessun ID inserito, operazione annullata.")
        return

    pkg_name = input("2. Inserisci il nome leggibile (es. My Awesome Plugin): ").strip()
    pkg_type = input("3. Tipo di pacchetto (plugin/module/theme) [plugin]: ").strip().lower() or "plugin"
    
    src_dir = packages_dir / f"{pkg_id}_src"
    if src_dir.exists():
        log_error(f"La cartella {src_dir.name} esiste gia'!")
        return

    log_info(f"Creazione alberatura in {src_dir}...")
    
    # Crea cartelle base
    os.makedirs(src_dir / "plugin" / pkg_id)
    os.makedirs(src_dir / "web_ui" / "static" / "js")
    os.makedirs(src_dir / "web_ui" / "templates")

    # Scrivi hpkg_manifest.toml
    manifest_content = f"""id = "{pkg_id}"
name = "{pkg_name}"
version = "1.0.0"
hecos_min_version = "0.35.0"
type = "{pkg_type}"
author = "Hecos Developer"
description = "Descrizione del pacchetto {pkg_name}."
target_dir = "plugins"

[config_panel]
tab_id = "{pkg_id}"
tab_label = "{pkg_name}"
tab_icon = "fa-cube"
category = "CONNETTIVITA"
template_file = "web_ui/templates/config_{pkg_id}.html"
js_file = "web_ui/static/js/{pkg_id}_panel.js"
"""
    with open(src_dir / "hpkg_manifest.toml", "w", encoding="utf-8") as f:
        f.write(manifest_content)

    # Scrivi file vuoti di esempio
    with open(src_dir / "plugin" / pkg_id / "__init__.py", "w", encoding="utf-8") as f:
        f.write("# Plugin Entry Point\n")
        
    with open(src_dir / "web_ui" / "templates" / f"config_{pkg_id}.html", "w", encoding="utf-8") as f:
        f.write(f"<!-- {pkg_name} Config Panel -->\n<div>\n    <h2>{pkg_name}</h2>\n</div>\n")
        
    with open(src_dir / "web_ui" / "static" / "js" / f"{pkg_id}_panel.js", "w", encoding="utf-8") as f:
        f.write(f"// {pkg_name} JS Logic\nconsole.log('{pkg_name} loaded!');\n")

    log_info("Scaffold completato con successo!")
