"""
REMOTE ACCESS PRO — main.py
Agente di controllo remoto via Telegram.
Intercetta comandi (/status, /ip, /cpu, /ram) e risponde con i dati del server,
scavalcando l'AI per rispondere istantaneamente.
"""
from hecos.core.logging import logger

# ── Comandi riconosciuti ─────────────────────────────────────────────────────
COMMANDS = {
    "/status":  "full_status",
    "/ip":      "ip_only",
    "/cpu":     "cpu_only",
    "/ram":     "ram_only",
    "/disco":   "disk_only",
    "/disk":    "disk_only",
    "/uptime":  "uptime_only",
    "/aiuto":   "help",
    "/help":    "help",
}

HELP_TEXT = """🤖 **Remote Access Pro — Comandi disponibili:**

`/status`  — Report completo del server
`/ip`      — IP locale e pubblico
`/cpu`     — Utilizzo CPU
`/ram`     — Utilizzo RAM
`/disco`   — Spazio disco
`/uptime`  — Uptime del server
`/aiuto`   — Mostra questo messaggio

Tutti gli altri messaggi vengono elaborati dall'IA (Urania).
"""


def handle_remote_command(text: str) -> str | None:
    """
    Controlla se il testo è un comando remoto riconosciuto.
    Se sì, elabora e restituisce la risposta (stringa).
    Se no, restituisce None (così il messaggio viene passato all'AI).
    """
    stripped = text.strip().lower().split()[0] if text.strip() else ""
    action = COMMANDS.get(stripped)

    if action is None:
        return None  # Non è un comando remoto → passa all'AI

    try:
        from .extrapolator import get_system_info, format_status_message
        info = get_system_info()
    except Exception as e:
        logger.error("REMOTE_ACCESS_PRO", f"Errore extrapolation: {e}")
        return f"❌ Errore nel recupero dei dati di sistema: {e}"

    if action == "full_status":
        return format_status_message(info)

    if action == "ip_only":
        return (
            f"🌐 **IP Locale:** `{info.get('local_ip', 'N/A')}`\n"
            f"🌍 **IP Pubblico:** `{info.get('public_ip', 'N/A')}`"
        )

    if action == "cpu_only":
        return f"⚙️ **CPU:** {info.get('cpu_percent', 'N/A')}% ({info.get('cpu_cores', 'N/A')} core)"

    if action == "ram_only":
        return (
            f"🧠 **RAM:** {info.get('ram_used_gb', 'N/A')} / {info.get('ram_total_gb', 'N/A')} GB "
            f"({info.get('ram_percent', 'N/A')}%)"
        )

    if action == "disk_only":
        return (
            f"💾 **Disco:** {info.get('disk_used_gb', 'N/A')} / {info.get('disk_total_gb', 'N/A')} GB "
            f"({info.get('disk_percent', 'N/A')}%)"
        )

    if action == "uptime_only":
        return f"⏱️ **Uptime:** `{info.get('uptime', 'N/A')}`"

    if action == "help":
        return HELP_TEXT

    return None


class RemoteAccessPro:
    """Plugin Remote Access Pro per Hecos HPM."""

    TAG = "REMOTE_ACCESS_PRO"

    def on_load(self):
        logger.info("REMOTE_ACCESS_PRO", "Plugin caricato. Registrazione callback su Messenger...")
        self._register_with_messenger()

    def _register_with_messenger(self):
        """
        Tenta di registrare un pre-callback sul Messenger Telegram.
        Usa il modulo del Messenger già caricato (se presente).
        """
        try:
            # Recupera il modulo Messenger dall'HPM loader
            from hecos.core import module_bus
            bus = module_bus.get_bus()
            messenger = bus.get_plugin("messenger")
            if messenger and hasattr(messenger, "register_pre_callback"):
                messenger.register_pre_callback("remote_access_pro", handle_remote_command)
                logger.info("REMOTE_ACCESS_PRO", "Pre-callback registrato su Messenger. Comandi /status etc. attivi.")
            else:
                logger.warning("REMOTE_ACCESS_PRO", "Messenger non trovato o senza register_pre_callback. Modalità standalone.")
        except Exception as e:
            logger.warning("REMOTE_ACCESS_PRO", f"Impossibile registrarsi su Messenger: {e}")

    def on_unload(self):
        logger.info("REMOTE_ACCESS_PRO", "Plugin scaricato.")
