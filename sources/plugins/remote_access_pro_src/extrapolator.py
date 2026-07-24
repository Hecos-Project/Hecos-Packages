"""
REMOTE ACCESS PRO — extrapolator.py
Raccoglie e formatta le informazioni di sistema per il reporting remoto.
"""
import platform
import socket
import time
import datetime

def _try_import(module_name):
    try:
        import importlib
        return importlib.import_module(module_name)
    except ImportError:
        return None


def get_system_info() -> dict:
    """Raccoglie tutte le metriche principali del sistema."""
    info = {}

    # ── Uptime ──────────────────────────────────────────────────────────────
    try:
        psutil = _try_import("psutil")
        if psutil:
            boot_ts = psutil.boot_time()
            uptime_secs = time.time() - boot_ts
            uptime_str = str(datetime.timedelta(seconds=int(uptime_secs)))
            info["uptime"] = uptime_str
        else:
            info["uptime"] = "N/A (psutil non disponibile)"
    except Exception as e:
        info["uptime"] = f"Errore: {e}"

    # ── CPU ─────────────────────────────────────────────────────────────────
    try:
        psutil = _try_import("psutil")
        if psutil:
            info["cpu_percent"] = psutil.cpu_percent(interval=0.5)
            info["cpu_cores"] = psutil.cpu_count(logical=True)
        else:
            info["cpu_percent"] = "N/A"
            info["cpu_cores"] = "N/A"
    except Exception as e:
        info["cpu_percent"] = f"Errore: {e}"

    # ── RAM ─────────────────────────────────────────────────────────────────
    try:
        psutil = _try_import("psutil")
        if psutil:
            ram = psutil.virtual_memory()
            info["ram_total_gb"] = round(ram.total / (1024 ** 3), 1)
            info["ram_used_gb"] = round(ram.used / (1024 ** 3), 1)
            info["ram_percent"] = ram.percent
        else:
            info["ram_total_gb"] = "N/A"
            info["ram_used_gb"] = "N/A"
            info["ram_percent"] = "N/A"
    except Exception as e:
        info["ram_percent"] = f"Errore: {e}"

    # ── Disco ────────────────────────────────────────────────────────────────
    try:
        psutil = _try_import("psutil")
        if psutil:
            disk = psutil.disk_usage("/")
            info["disk_total_gb"] = round(disk.total / (1024 ** 3), 1)
            info["disk_used_gb"] = round(disk.used / (1024 ** 3), 1)
            info["disk_percent"] = disk.percent
        else:
            info["disk_percent"] = "N/A"
    except Exception as e:
        info["disk_percent"] = f"Errore: {e}"

    # ── Rete: IP locale ──────────────────────────────────────────────────────
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        info["local_ip"] = s.getsockname()[0]
        s.close()
    except Exception:
        info["local_ip"] = "N/A"

    # ── Rete: IP pubblico ────────────────────────────────────────────────────
    try:
        import urllib.request
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as r:
            info["public_ip"] = r.read().decode("utf-8").strip()
    except Exception:
        info["public_ip"] = "N/A (offline?)"

    # ── Hostname & OS ────────────────────────────────────────────────────────
    info["hostname"] = socket.gethostname()
    info["os"] = f"{platform.system()} {platform.release()}"

    return info


def format_status_message(info: dict) -> str:
    """Formatta le metriche in un messaggio Telegram leggibile."""
    lines = [
        "📊 **Stato del Server Hecos**",
        "",
        f"🖥️  **Host:** `{info.get('hostname', 'N/A')}`",
        f"💿  **OS:** {info.get('os', 'N/A')}",
        f"⏱️  **Uptime:** `{info.get('uptime', 'N/A')}`",
        "",
        f"⚙️  **CPU:** {info.get('cpu_percent', 'N/A')}% ({info.get('cpu_cores', 'N/A')} core)",
        f"🧠  **RAM:** {info.get('ram_used_gb', 'N/A')} / {info.get('ram_total_gb', 'N/A')} GB ({info.get('ram_percent', 'N/A')}%)",
        f"💾  **Disco:** {info.get('disk_used_gb', 'N/A')} / {info.get('disk_total_gb', 'N/A')} GB ({info.get('disk_percent', 'N/A')}%)",
        "",
        f"🌐  **IP Locale:** `{info.get('local_ip', 'N/A')}`",
        f"🌍  **IP Pubblico:** `{info.get('public_ip', 'N/A')}`",
    ]
    return "\n".join(lines)
