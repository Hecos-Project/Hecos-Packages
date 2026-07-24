# Messenger Plugin per Hecos

Il plugin Messenger permette ad Hecos (e alla tua assistente AI) di inviare e ricevere messaggi attraverso vari provider: **Telegram**, **WhatsApp** e **Discord**.

## 🚀 Novità: Telegram Multi-Bot

Il modulo Telegram è stato riprogettato per supportare un numero infinito di bot attivi contemporaneamente.
Questa architettura ti permette di avere:
- Un **Bot Privato (Admin)** per controllare Hecos da remoto (tramite *Remote Access Pro*).
- Un **Bot Pubblico (es. Urania)** da inserire nei gruppi o nei canali per interagire con i tuoi amici.
- **Quanti bot vuoi**, per gestire community, alert aziendali, o chat differenti, tutto gestito da un singolo server Hecos.

### Configurazione Telegram
Nel pannello di configurazione, alla voce "Messenger", clicca su **"Aggiungi nuovo Bot"**.
Per ogni bot puoi configurare:
1. **Nome Identificativo:** (es. `admin`, `urania`). *Importante: usalo per il routing!*
2. **Token Bot:** Ottenuto da [@BotFather](https://t.me/BotFather).
3. **Default Chat ID:** La chat predefinita dove verranno inviati i messaggi se non specificata.
4. **Privilegi di Amministrazione:**
   - **Abilitato:** Il bot rifiuterà messaggi da chiunque non sia l'ID predefinito. Gestisce i comandi di sistema (`/uptime`, `/status`, ecc).
   - **Disabilitato (Gruppi/Pubblico):** Il bot diventerà "socievole". Puoi scegliere se deve rispondere solo quando menzionato (`@nomebot`), se deve reagire a certe **Parole Chiave**, o se deve rispondere a tutti i messaggi del gruppo.

### Come inviare messaggi a Bot specifici
Se non specifichi nulla, l'AI o i plugin invieranno il messaggio tramite il **primo bot abilitato** nella lista.

Se vuoi forzare l'uso di un bot specifico (ad esempio tramite un automatismo in Hecos Flows, o usando il comando rapido `/msg`), usa la sintassi:
`telegram:nome_del_bot:chat_id`

**Esempi:**
- `/msg telegram:admin:123456 Ciao Admin!` (Invia tramite il bot chiamato "admin" all'utente 123456)
- `/msg telegram:urania:@hecos_project Ciao Gruppo!` (Invia tramite il bot "urania" al gruppo @hecos_project)
- `/msg telegram:123456 Ciao!` (Se il nome bot è omesso, usa il primo bot disponibile).

## 📸 Invio Immagini (send_photo)
Il plugin Telegram supporta in modo nativo l'invio di immagini generate da Hecos (o presenti sul disco).
Se durante una chat chiedi all'IA di "generare un'immagine e mandarmela", Hecos userà automaticamente il tool `send_photo` (oppure `send_reply_photo` se sta rispondendo) inviandoti il file multimediale su Telegram!

## 🟢 WhatsApp & Discord
* **WhatsApp:** Utilizza automazione basata su PyWhatKit / CDP (Browser Automation). Adatto per invii una tantum a numeri non in rubrica, ma è sperimentale.
* **Discord:** Utilizza un Webhook URL per spingere notifiche all'interno di un canale Discord specifico. È attualmente in sola uscita (Hecos invia, ma non legge).
