# Remote Access Pro

Controllo e monitoraggio remoto del server **Hecos** via Telegram.

Risponde a comandi rapidi direttamente in chat, **scavalcando l'AI** per risposte istantanee senza consumare token.

---

## Requisiti

- Plugin **Messenger** installato e configurato con un bot Telegram attivo.
- Libreria `psutil` (installata automaticamente).

---

## Comandi disponibili

| Comando   | Descrizione                              |
|-----------|------------------------------------------|
| `/status` | Report completo del server               |
| `/ip`     | IP locale e pubblico                     |
| `/cpu`    | Utilizzo CPU e numero di core            |
| `/ram`    | Utilizzo RAM (usata / totale)            |
| `/disco`  | Spazio disco (usato / totale)            |
| `/uptime` | Uptime del server dall'ultimo avvio      |
| `/aiuto`  | Lista di tutti i comandi disponibili     |

Qualsiasi altro messaggio viene passato normalmente all'intelligenza artificiale (Urania).

---

## Come funziona

Il plugin si registra come **pre-callback** sul Messenger. Quando arriva un messaggio Telegram:

1. Remote Access Pro controlla se il testo inizia con un comando riconosciuto (`/status`, `/ip`, ecc.).
2. Se sì → raccoglie i dati di sistema tramite `psutil` e risponde immediatamente.
3. Se no → lascia passare il messaggio all'AI normalmente.

---

## Autore

Antonio Meloni — Hecos Project
