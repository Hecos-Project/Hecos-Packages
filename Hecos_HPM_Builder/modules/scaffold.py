import os
from colorama import Fore, Style
from modules.logging_sys import log_info, log_error, log_warn
from modules.settings import get_src_dir, load_config

def _prompt_field(label: str, default_val: str) -> str:
    """Prompt the user for a new value, offering the default as an option."""
    print(f"\n  {Fore.CYAN}{label}{Style.RESET_ALL}")
    print(f"  {Fore.LIGHTBLACK_EX}1. Usa valore di default:{Style.RESET_ALL} {default_val}")
    print(f"  {Fore.LIGHTBLACK_EX}2. Inserisci nuovo valore{Style.RESET_ALL}")
    
    while True:
        choice = input(f"  Scelta (1/2) [1]: ").strip() or "1"
        if choice == "1":
            return default_val
        elif choice == "2":
            return input(f"  Nuovo {label}: ").strip()
        print("  Scelta non valida.")

def scaffold_package():
    packages_dir = get_src_dir()
    cfg = load_config()
    defaults = cfg.get("defaults", {})
    
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
    
    # Prompt for other manifest fields
    print(f"\n{Fore.YELLOW}--- Configurazione Manifest ---{Style.RESET_ALL}")
    pkg_author = _prompt_field("Autore", defaults.get("author", "Hecos Developer"))
    pkg_version = _prompt_field("Versione Iniziale", defaults.get("version", "1.0.0"))
    pkg_desc = _prompt_field("Descrizione", defaults.get("description", f"Descrizione del pacchetto {pkg_name}."))
    pkg_license = _prompt_field("Licenza", defaults.get("license", "MIT"))
    pkg_hecos_min = _prompt_field("Versione Minima Hecos", defaults.get("hecos_min_version", "0.39.0"))
    
    # Crea cartelle base
    os.makedirs(src_dir / "plugin" / pkg_id)
    os.makedirs(src_dir / "web_ui" / "static" / "js")
    os.makedirs(src_dir / "web_ui" / "templates")

    # Scrivi hpkg_manifest.toml
    manifest_content = f"""id = "{pkg_id}"
name = "{pkg_name}"
version = "{pkg_version}"
hecos_min_version = "{pkg_hecos_min}"
type = "{pkg_type}"
author = "{pkg_author}"
description = "{pkg_desc}"
target_dir = "hpm"

readme = "README.md"
changelog = "CHANGELOG.md"
license = "{pkg_license}"
keywords = ["{pkg_id}", "hecos"]

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
    with open(src_dir / "README.md", "w", encoding="utf-8") as f:
        f.write(f"# {pkg_name}\\n\\n{pkg_desc}\\n")
        
    with open(src_dir / "CHANGELOG.md", "w", encoding="utf-8") as f:
        f.write(f"# Changelog - {pkg_name}\\n\\n## {pkg_version}\\n- Initial release\\n")

    with open(src_dir / "plugin" / pkg_id / "__init__.py", "w", encoding="utf-8") as f:
        f.write("# Plugin Entry Point\n")
        
    main_py_content = f'''"""
MODULE: {pkg_name}
"""
from hecos_sdk import logger

class {pkg_id.capitalize()}Tools:
    def __init__(self):
        self.tag = "{pkg_id.upper()}"

    def status(self) -> str:
        return "Loaded"

tools = {pkg_id.capitalize()}Tools()
'''
    with open(src_dir / "plugin" / pkg_id / "main.py", "w", encoding="utf-8") as f:
        f.write(main_py_content)

        
    with open(src_dir / "web_ui" / "templates" / f"config_{pkg_id}.html", "w", encoding="utf-8") as f:
        f.write(f"<!-- {pkg_name} Config Panel -->\n<div>\n    <h2>{pkg_name}</h2>\n</div>\n")
        
    with open(src_dir / "web_ui" / "static" / "js" / f"{pkg_id}_panel.js", "w", encoding="utf-8") as f:
        f.write(f"// {pkg_name} JS Logic\nconsole.log('{pkg_name} loaded!');\n")

    log_info("Scaffold completato con successo!")
