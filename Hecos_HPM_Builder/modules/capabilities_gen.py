import os
import zipfile
from pathlib import Path
from modules.logging_sys import log_info, log_error, log_warn

try:
    import tomllib
except ImportError:
    import tomli as tomllib

import tomli_w
from colorama import Fore, Style

def auto_generate_capabilities(target_dir: Path) -> bool:
    manifest_path = target_dir / "hpkg_manifest.toml"
    if not manifest_path.exists():
        log_error(f"{manifest_path.name} not found in {target_dir}")
        return False

    try:
        manifest = tomllib.loads(manifest_path.read_bytes().decode("utf-8"))
    except Exception as e:
        log_error(f"TOML syntax error in {manifest_path.name}: {e}")
        return False

    pkg_tag = manifest.get("tag", "").upper()

    # Estrai tool_schema
    llm_tools = []
    for schema in manifest.get("tool_schema", []):
        name = schema.get("name")
        if not name and "function" in schema:
            name = schema["function"].get("name", "")
        if not name:
            continue
        
        if pkg_tag and name.startswith(f"{pkg_tag}__"):
            name = name[len(f"{pkg_tag}__"):]
        llm_tools.append(name)


    # Estrai slash_commands
    slash_commands = []
    for cmd in manifest.get("slash_commands", []):
        aliases = cmd.get("aliases", [])
        if aliases:
            slash_commands.extend(aliases)
        else:
            if "id" in cmd:
                slash_commands.append("/" + cmd["id"])

    # Determina flag
    has_widget       = "widgets" in manifest and len(manifest["widgets"]) > 0
    has_config_panel = "config_panel" in manifest
    has_api_routes   = "api_routes_file" in manifest or ("config_panel" in manifest and "api_routes_file" in manifest["config_panel"])

    # Mantieni system calls e notes se già presenti
    existing_cap     = manifest.get("capabilities", {})
    has_system_calls = existing_cap.get("has_system_calls", False)
    syscall_notes    = existing_cap.get("syscall_notes", "")
    notes            = existing_cap.get("notes", "")

    manifest["capabilities"] = {
        "llm_tools":       llm_tools,
        "slash_commands":  slash_commands,
        "has_widget":      has_widget,
        "has_config_panel": has_config_panel,
        "has_api_routes":  has_api_routes,
        "has_system_calls": has_system_calls,
        "syscall_notes":   syscall_notes,
        "notes":           notes,
    }

    try:
        manifest_path.write_bytes(tomli_w.dumps(manifest).encode("utf-8"))
        log_info(f"Capabilities auto-generated successfully for {manifest.get('name', 'package')}")
        return True
    except Exception as e:
        log_error(f"Error saving {manifest_path.name}: {e}")
        return False


# ── Menu: generate for ALL packages ──────────────────────────────────────────

def generate_all_capabilities():
    from modules.settings import get_src_dir
    src_root = get_src_dir()
    src_dirs = sorted([d for d in src_root.iterdir()
                       if d.is_dir() and d.name.endswith("_src")])

    if not src_dirs:
        log_warn(f"No '*_src' folder found in {src_root}")
        return

    ok_count = fail_count = 0
    for d in src_dirs:
        if auto_generate_capabilities(d):
            ok_count += 1
        else:
            fail_count += 1

    print(f"\n{'='*40}")
    print(f"  Updated: {ok_count}  |  Failed: {fail_count}")
    print(f"{'='*40}")


# ── Menu: generate for ONE package ───────────────────────────────────────────

def generate_single_capabilities():
    from modules.settings import get_src_dir
    src_root = get_src_dir()
    src_dirs = sorted([d for d in src_root.iterdir()
                       if d.is_dir() and d.name.endswith("_src")])

    if not src_dirs:
        log_warn(f"No '*_src' folder found in {src_root}")
        return

    print("Available packages:\n")
    for i, d in enumerate(src_dirs):
        mf = d / "hpkg_manifest.toml"
        status = " [no manifest]"
        if mf.exists():
            try:
                m = tomllib.loads(mf.read_bytes().decode("utf-8"))
                status = " [cap OK]" if "capabilities" in m else " [no cap]"
            except Exception:
                status = " [TOML ERR]"
        print(f"  {i+1}. {d.name}{status}")

    choice = input("\nSelect the package (0 to cancel): ").strip()
    try:
        idx = int(choice) - 1
        if idx == -1:
            return
        if not (0 <= idx < len(src_dirs)):
            log_error("Invalid selection.")
            return
    except ValueError:
        log_error("Invalid input.")
        return

    auto_generate_capabilities(src_dirs[idx])


# ── Menu: show full package sheet ─────────────────────────────────────────────

def show_package_sheet():
    from modules.settings import get_src_dir, get_packages_dir
    src_root     = get_src_dir()
    packages_dir = get_packages_dir()

    src_dirs   = sorted([d for d in src_root.iterdir()
                         if d.is_dir() and d.name.endswith("_src")])
    hpkg_files = sorted(packages_dir.glob("*.hpkg")) if packages_dir.exists() else []

    options = [("src", d) for d in src_dirs] + [("hpkg", h) for h in hpkg_files]

    if not options:
        log_warn("No package found.")
        return

    print("Choose package:\n")
    for i, (kind, path) in enumerate(options):
        label = f"{Fore.GREEN}[SRC]{Style.RESET_ALL}  {path.name}" if kind == "src" else f"{Fore.MAGENTA}[HPKG]{Style.RESET_ALL} {path.name}"
        print(f"  {Fore.CYAN}{i+1}.{Style.RESET_ALL} {label}")

    choice = input(f"\n{Fore.YELLOW}Select (0 to cancel): {Style.RESET_ALL}").strip()
    try:
        idx = int(choice) - 1
        if idx == -1:
            return
        if not (0 <= idx < len(options)):
            log_error("Invalid selection.")
            return
        kind, path = options[idx]
    except ValueError:
        log_error("Invalid input.")
        return

    try:
        if kind == "src":
            mf = path / "hpkg_manifest.toml"
            manifest = tomllib.loads(mf.read_bytes().decode("utf-8"))
        else:
            with zipfile.ZipFile(path, "r") as zf:
                manifest = tomllib.loads(zf.read("hpkg_manifest.toml").decode("utf-8"))
    except Exception as e:
        log_error(f"Error reading manifest: {e}")
        return

    _print_package_sheet(manifest)


def show_all_package_sheets():
    from modules.settings import get_src_dir, get_packages_dir
    src_root     = get_src_dir()
    
    src_dirs   = sorted([d for d in src_root.iterdir()
                         if d.is_dir() and d.name.endswith("_src")])
    
    if not src_dirs:
        log_warn("No source package found.")
        return
        
    for path in src_dirs:
        try:
            mf = path / "hpkg_manifest.toml"
            if mf.exists():
                manifest = tomllib.loads(mf.read_bytes().decode("utf-8"))
                _print_package_sheet(manifest)
        except Exception as e:
            log_error(f"Error reading manifest of {path.name}: {e}")
    src_root     = get_src_dir()
    packages_dir = get_packages_dir()

    src_dirs   = sorted([d for d in src_root.iterdir()
                         if d.is_dir() and d.name.endswith("_src")])
    hpkg_files = sorted(packages_dir.glob("*.hpkg")) if packages_dir.exists() else []

    options = [("src", d) for d in src_dirs] + [("hpkg", h) for h in hpkg_files]

    if not options:
        log_warn("Nessun pacchetto trovato.")
        return

    print("Scegli pacchetto:\n")
    for i, (kind, path) in enumerate(options):
        label = f"[SRC]  {path.name}" if kind == "src" else f"[HPKG] {path.name}"
        print(f"  {i+1}. {label}")

    choice = input("\nSeleziona (0 per annullare): ").strip()
    try:
        idx = int(choice) - 1
        if idx == -1:
            return
        if not (0 <= idx < len(options)):
            log_error("Selezione non valida.")
            return
        kind, path = options[idx]
    except ValueError:
        log_error("Input non valido.")
        return

    try:
        if kind == "src":
            mf = path / "hpkg_manifest.toml"
            manifest = tomllib.loads(mf.read_bytes().decode("utf-8"))
        else:
            with zipfile.ZipFile(path, "r") as zf:
                manifest = tomllib.loads(zf.read("hpkg_manifest.toml").decode("utf-8"))
    except Exception as e:
        log_error(f"Errore nella lettura del manifest: {e}")
        return

    _print_package_sheet(manifest)


# ── Rendering: scheda visuale ─────────────────────────────────────────────────

def _print_package_sheet(manifest: dict):
    W = 56
    SEP = f"{Fore.CYAN}{'-' * W}{Style.RESET_ALL}"
    THICK_SEP = f"{Fore.CYAN}{'=' * W}{Style.RESET_ALL}"

    def chk(val):
        return f"  {Fore.GREEN}[Y]{Style.RESET_ALL}" if val else f"  {Fore.RED}[N]{Style.RESET_ALL}"

    def row(label, value, flag=None):
        val_str = f"{Fore.WHITE}{value}{Style.RESET_ALL}" if value else f"{Fore.LIGHTBLACK_EX}-{Style.RESET_ALL}"
        suffix  = chk(flag) if flag is not None else ""
        print(f"  {Fore.CYAN}{label:<24}{Style.RESET_ALL}{val_str}{suffix}")

    def wrap_print(text, indent=4, width=54):
        words = text.split()
        line = " " * indent
        for w in words:
            if len(line) + len(w) + 1 > width:
                print(f"{Fore.LIGHTBLACK_EX}{line}{Style.RESET_ALL}")
                line = " " * indent + w + " "
            else:
                line += w + " "
        if line.strip():
            print(f"{Fore.LIGHTBLACK_EX}{line}{Style.RESET_ALL}")

    print(f"\n{THICK_SEP}")
    print(f"{Fore.YELLOW}{'  HECOS PACKAGE SHEET':^{W}}{Style.RESET_ALL}")
    print(f"{THICK_SEP}")

    # -- Identita --
    print(f"\n  {SEP}")
    print(f"  {Fore.MAGENTA}IDENTITY{Style.RESET_ALL}")
    print(f"  {SEP}")
    row("Name:",         manifest.get("name"))
    row("ID:",           manifest.get("id"))
    row("Version:",     manifest.get("version"))
    row("Author:",       manifest.get("author"))
    row("Type:",         manifest.get("type"))
    row("Tag:",          manifest.get("tag"))
    row("License:",      manifest.get("license"))
    row("Min Hecos:",    manifest.get("hecos_min_version"))

    desc = manifest.get("description", "")
    if desc:
        print(f"\n  {Fore.CYAN}Description:{Style.RESET_ALL}")
        wrap_print(desc)

    # -- Capacita --
    cap = manifest.get("capabilities", {})
    print(f"\n  {SEP}")
    print(f"  {Fore.MAGENTA}CAPABILITIES{Style.RESET_ALL}")
    print(f"  {SEP}")
    row("Widget:",          "Yes" if cap.get("has_widget") else "No",        flag=cap.get("has_widget", False))
    row("Config Panel:",    "Yes" if cap.get("has_config_panel") else "No",  flag=cap.get("has_config_panel", False))
    row("API Routes:",      "Yes" if cap.get("has_api_routes") else "No",    flag=cap.get("has_api_routes", False))
    row("System Calls:",    "Yes" if cap.get("has_system_calls") else "No",  flag=cap.get("has_system_calls", False))

    tools = cap.get("llm_tools", [])
    print(f"\n  {Fore.CYAN}LLM Tools {Fore.YELLOW}({len(tools)}):{Style.RESET_ALL}")
    for t in tools:
        print(f"    {Fore.GREEN}-{Style.RESET_ALL} {Fore.WHITE}{t}{Style.RESET_ALL}")
    if not tools:
        print(f"    {Fore.LIGHTBLACK_EX}-{Style.RESET_ALL}")

    cmds = cap.get("slash_commands", [])
    print(f"\n  {Fore.CYAN}Slash Commands {Fore.YELLOW}({len(cmds)}):{Style.RESET_ALL}")
    for c in cmds:
        print(f"    {Fore.GREEN}-{Style.RESET_ALL} {Fore.WHITE}{c}{Style.RESET_ALL}")
    if not cmds:
        print(f"    {Fore.LIGHTBLACK_EX}-{Style.RESET_ALL}")

    if cap.get("syscall_notes"):
        print(f"\n  {Fore.CYAN}System Calls Notes:{Style.RESET_ALL}")
        wrap_print(cap["syscall_notes"])

    if cap.get("notes"):
        print(f"\n  {Fore.CYAN}Note:{Style.RESET_ALL}")
        wrap_print(cap["notes"])

    # -- Tecnico --
    print(f"\n  {SEP}")
    print(f"  {Fore.MAGENTA}TECHNICAL COMPONENTS{Style.RESET_ALL}")
    print(f"  {SEP}")

    pip_req = manifest.get("pip_requirements", [])
    print(f"\n  {Fore.CYAN}pip Dependencies {Fore.YELLOW}({len(pip_req)}):{Style.RESET_ALL}")
    for r in pip_req:
        print(f"    {Fore.GREEN}-{Style.RESET_ALL} {Fore.WHITE}{r}{Style.RESET_ALL}")
    if not pip_req:
        print(f"    {Fore.LIGHTBLACK_EX}-{Style.RESET_ALL}")

    widgets = manifest.get("widgets", [])
    if widgets:
        print(f"\n  {Fore.CYAN}Widget {Fore.YELLOW}({len(widgets)}):{Style.RESET_ALL}")
        for w in widgets:
            print(f"    {Fore.GREEN}-{Style.RESET_ALL} id={Fore.WHITE}{w.get('id')}{Style.RESET_ALL}  ->  {Fore.LIGHTBLACK_EX}{w.get('extension_path', '')}{Style.RESET_ALL}")

    cp = manifest.get("config_panel", {})
    if cp:
        print(f"\n  {Fore.CYAN}Config Panel:{Style.RESET_ALL}")
        row("    Tab ID:", cp.get("tab_id"))
        row("    Label:",  cp.get("tab_label"))
        row("    Category:", cp.get("category"))

    cmds_dict = manifest.get("commands", {})
    if cmds_dict:
        print(f"\n  {Fore.CYAN}Commands {Fore.YELLOW}({len(cmds_dict)}):{Style.RESET_ALL}")
        for k, v in cmds_dict.items():
            v_str = str(v)
            print(f"    {Fore.GREEN}-{Style.RESET_ALL} {Fore.WHITE}{k}:{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}{v_str[:55]}{'...' if len(v_str) > 55 else ''}{Style.RESET_ALL}")

    slash_cmds_list = manifest.get("slash_commands", [])
    if slash_cmds_list:
        print(f"\n  {Fore.CYAN}Slash Commands (details):{Style.RESET_ALL}")
        for cmd in slash_cmds_list:
            aliases_str = ", ".join(cmd.get("aliases", []))
            print(f"    {Fore.GREEN}-{Style.RESET_ALL} {Fore.WHITE}{cmd.get('id','')}{Style.RESET_ALL} ({aliases_str}) -- {Fore.LIGHTBLACK_EX}{cmd.get('description','')[:45]}{Style.RESET_ALL}")

    print(f"\n  {SEP}\n")
