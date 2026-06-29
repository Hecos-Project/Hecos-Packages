"""
HPM Builder — Manifest Editor
Allows interactive editing of package metadata:
  - Version (interactive arrow-key picker + manual entry)
  - Name, Author, Description, License
"""
import os
import sys
from pathlib import Path
from colorama import Fore, Style

from modules.logging_sys import log_info, log_error, log_warn
from modules.settings import get_packages_dir

try:
    import tomllib
except ImportError:
    import tomli as tomllib

try:
    import tomli_w
    _HAS_TOMLI_W = True
except ImportError:
    _HAS_TOMLI_W = False

# ── Arrow-key input support ───────────────────────────────────────────────────

if sys.platform == "win32":
    import msvcrt
    def _getch():
        ch = msvcrt.getwch()
        if ch in ('\x00', '\xe0'):   # special key prefix on Windows
            ch2 = msvcrt.getwch()
            return ch + ch2
        return ch
    _ARROW_UP    = '\xe0H'
    _ARROW_DOWN  = '\xe0P'
    _ARROW_LEFT  = '\xe0K'
    _ARROW_RIGHT = '\xe0M'
else:
    import tty, termios
    def _getch():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                ch2 = sys.stdin.read(1)
                ch3 = sys.stdin.read(1)
                return ch + ch2 + ch3
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    _ARROW_UP    = '\x1b[A'
    _ARROW_DOWN  = '\x1b[B'
    _ARROW_LEFT  = '\x1b[D'
    _ARROW_RIGHT = '\x1b[C'

_ENTER = ('\r', '\n')
_ESC   = '\x1b'


# ── Version picker ────────────────────────────────────────────────────────────

def _parse_version(v: str):
    """Parse 'MAJOR.MINOR.PATCH' into a list of ints. Pads to 3 fields."""
    parts = v.strip().split(".")
    result = []
    for p in parts[:3]:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    while len(result) < 3:
        result.append(0)
    return result


def _render_version(parts: list, selected: int) -> str:
    """Render the version segments with the selected one highlighted."""
    labels = ["MAJOR", "MINOR", "PATCH"]
    rendered = []
    for i, (val, lbl) in enumerate(zip(parts, labels)):
        if i == selected:
            rendered.append(
                f"{Fore.YELLOW}{Style.BRIGHT}[{val}]{Style.RESET_ALL}"
            )
        else:
            rendered.append(f"{Fore.WHITE}{val}{Style.RESET_ALL}")
    return ".".join(rendered)


def pick_version(current: str) -> str:
    """
    Interactive version picker.
    ← → to move between MAJOR/MINOR/PATCH
    ↑ ↓ to increment/decrement the selected segment
    ENTER to confirm, ESC to cancel (keep original).
    The user can also type a version string manually.
    """
    print(f"\n{Fore.CYAN}{'─'*56}{Style.RESET_ALL}")
    print(f"  {Style.BRIGHT}Selettore Versione Interattivo{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'─'*56}{Style.RESET_ALL}")
    print(f"  {Fore.LIGHTBLACK_EX}← → per spostarti · ↑ ↓ per cambiare valore{Style.RESET_ALL}")
    print(f"  {Fore.LIGHTBLACK_EX}Invio per confermare · Esc o Q per annullare{Style.RESET_ALL}")
    print(f"  {Fore.LIGHTBLACK_EX}Digita direttamente es. '2.0.1' e premi Invio{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'─'*56}{Style.RESET_ALL}\n")

    parts   = _parse_version(current)
    sel     = 0          # selected segment index (0=MAJOR, 1=MINOR, 2=PATCH)
    typed   = ""         # buffer for manual typing
    labels  = ["MAJOR", "MINOR", "PATCH"]

    def _redraw():
        # Clear previous line group (3 lines: version + label + hint)
        label_row = f"  {Fore.LIGHTBLACK_EX}  " + "    ".join(
            f"{Style.BRIGHT}{lbl}{Style.RESET_ALL}" if i == sel else lbl
            for i, lbl in enumerate(labels)
        ) + Style.RESET_ALL
        version_row = f"  Versione: {_render_version(parts, sel)}"
        typed_row   = f"  Libera: {Fore.YELLOW}{typed}{'▌' if typed else ''}{Style.RESET_ALL}"
        # Move up 3 lines and overwrite
        sys.stdout.write("\r\033[2A")   # up 2
        sys.stdout.write("\r\033[K" + version_row + "\n")
        sys.stdout.write("\r\033[K" + label_row + "\n")
        sys.stdout.write("\r\033[K" + typed_row)
        sys.stdout.flush()

    # Initial draw (no cursor move needed yet — print fresh)
    print(f"  Versione: {_render_version(parts, sel)}")
    print(f"  {Fore.LIGHTBLACK_EX}  " + "    ".join(labels) + Style.RESET_ALL)
    print(f"  Libera: {Fore.YELLOW}▌{Style.RESET_ALL}", end="", flush=True)

    while True:
        ch = _getch()

        # ── Arrow keys ──
        if ch == _ARROW_LEFT:
            typed = ""
            sel = (sel - 1) % 3
            _redraw()
        elif ch == _ARROW_RIGHT:
            typed = ""
            sel = (sel + 1) % 3
            _redraw()
        elif ch == _ARROW_UP:
            typed = ""
            parts[sel] = max(0, parts[sel] + 1)
            _redraw()
        elif ch == _ARROW_DOWN:
            typed = ""
            parts[sel] = max(0, parts[sel] - 1)
            _redraw()

        # ── Manual entry: digits and dot ──
        elif ch.isdigit() or ch == ".":
            typed += ch
            _redraw()

        # ── Backspace ──
        elif ch in ('\x08', '\x7f'):
            if typed:
                typed = typed[:-1]
            _redraw()

        # ── Confirm ──
        elif ch in _ENTER:
            print()  # move past the typed line
            if typed.strip():
                # Parse what the user manually typed
                candidate = typed.strip()
                parsed = _parse_version(candidate)
                result = ".".join(str(p) for p in parsed)
            else:
                result = ".".join(str(p) for p in parts)
            print(f"\n  {Fore.GREEN}✓ Versione confermata: {Style.BRIGHT}{result}{Style.RESET_ALL}\n")
            return result

        # ── Cancel (ESC or Q) ──
        elif ch == _ESC or ch.lower() == 'q':
            print()
            print(f"\n  {Fore.YELLOW}✗ Annullato — versione invariata: {current}{Style.RESET_ALL}\n")
            return current


# ── Metadata editor fields ────────────────────────────────────────────────────

_EDITABLE_FIELDS = [
    ("version",     "Versione",     True),   # True = use version picker
    ("name",        "Nome",         False),
    ("author",      "Autore",       False),
    ("description", "Descrizione",  False),
    ("license",     "Licenza",      False),
]


def _prompt_field(label: str, current, use_version_picker: bool):
    """
    Prompt the user to change a single field.
    Returns the new value (or the old one if left blank).
    """
    if use_version_picker:
        return pick_version(str(current))
    else:
        display = str(current) if current else "(vuoto)"
        new_val = input(
            f"  {Fore.CYAN}{label}{Style.RESET_ALL} "
            f"{Fore.LIGHTBLACK_EX}(attuale: {display} | Invio per mantenere){Style.RESET_ALL}: "
        ).strip()
        return new_val if new_val else current


def _write_manifest(path: Path, manifest: dict) -> bool:
    """Write the manifest back to the TOML file."""
    try:
        if _HAS_TOMLI_W:
            path.write_bytes(tomli_w.dumps(manifest).encode("utf-8"))
        else:
            from modules.builder import _json_to_toml
            path.write_bytes(_json_to_toml(manifest).encode("utf-8"))
        return True
    except Exception as e:
        log_error(f"Errore nella scrittura del manifest: {e}")
        return False


# ── Main entrypoint ───────────────────────────────────────────────────────────

def edit_manifest():
    """
    Interactive metadata editor for hpkg_manifest.toml.
    Lets the user pick a package, then edit version, name, author, description, license.
    """
    packages_dir = get_packages_dir()
    src_dirs = sorted([d for d in packages_dir.iterdir() if d.is_dir() and d.name.endswith("_src")])

    if not src_dirs:
        log_warn(f"Nessuna cartella '*_src' trovata in {packages_dir}")
        return

    print(f"{Fore.CYAN}Pacchetti disponibili:{Style.RESET_ALL}")
    for i, d in enumerate(src_dirs):
        # Peek at version
        mpath = d / "hpkg_manifest.toml"
        version_hint = ""
        if mpath.exists():
            try:
                m = tomllib.loads(mpath.read_bytes().decode("utf-8"))
                version_hint = f"  {Fore.LIGHTBLACK_EX}v{m.get('version', '?')}{Style.RESET_ALL}"
            except Exception:
                pass
        print(f"  {Fore.WHITE}{i+1}.{Style.RESET_ALL} {d.name}{version_hint}")

    choice = input(f"\n{Fore.YELLOW}Seleziona il pacchetto da modificare (0 per annullare):{Style.RESET_ALL} ").strip()
    try:
        idx = int(choice) - 1
        if idx < 0:
            return
        target_dir = src_dirs[idx]
    except (ValueError, IndexError):
        log_warn("Selezione non valida.")
        return

    manifest_path = target_dir / "hpkg_manifest.toml"
    if not manifest_path.exists():
        log_error(f"hpkg_manifest.toml non trovato in {target_dir.name}")
        return

    try:
        manifest = tomllib.loads(manifest_path.read_bytes().decode("utf-8"))
    except Exception as e:
        log_error(f"Errore lettura manifest: {e}")
        return

    print(f"\n{Fore.CYAN}{'─'*56}{Style.RESET_ALL}")
    print(f"  Modifica Metadati: {Style.BRIGHT}{manifest.get('name', target_dir.name)}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'─'*56}{Style.RESET_ALL}\n")

    print(f"  {Fore.LIGHTBLACK_EX}Lascia vuoto per mantenere il valore attuale.{Style.RESET_ALL}\n")

    changed = False
    for field_key, label, use_picker in _EDITABLE_FIELDS:
        current = manifest.get(field_key, "")
        new_val = _prompt_field(label, current, use_picker)
        if str(new_val) != str(current):
            manifest[field_key] = new_val
            changed = True
            log_info(f"  {label}: {current!r} → {new_val!r}")

    if not changed:
        print(f"\n  {Fore.LIGHTBLACK_EX}Nessuna modifica effettuata.{Style.RESET_ALL}\n")
        return

    print(f"\n{Fore.CYAN}{'─'*56}{Style.RESET_ALL}")
    print(f"  {Fore.WHITE}Riepilogo modifiche:{Style.RESET_ALL}")
    for field_key, label, _ in _EDITABLE_FIELDS:
        print(f"    {Fore.LIGHTBLACK_EX}{label}:{Style.RESET_ALL} {manifest.get(field_key, '')}")
    print(f"{Fore.CYAN}{'─'*56}{Style.RESET_ALL}\n")

    confirm = input(f"{Fore.YELLOW}Salvare le modifiche nel manifest? (s/N):{Style.RESET_ALL} ").strip().lower()
    if confirm != 's':
        print(f"\n  {Fore.YELLOW}Annullato — nessuna modifica salvata.{Style.RESET_ALL}\n")
        return

    if _write_manifest(manifest_path, manifest):
        log_info(f"Manifest aggiornato con successo: {manifest_path}")
        print(f"\n  {Fore.LIGHTBLACK_EX}Ricorda di ricompilare il pacchetto (opzione 3 o 4) per applicare le modifiche.{Style.RESET_ALL}\n")
    else:
        log_error("Salvataggio fallito.")
