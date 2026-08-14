# Notifications Center

Plugin per Hecos che instrada notifiche di sistema verso i plugin MAIL e/o MESSENGER.

## Funzionamento

- Non gestisce direttamente email o messaggi: si appoggia ai plugin **MAIL** e **MESSENGER** già installati.
- Quando avviene un evento (es. un Flow termina con errore), il dispatcher legge le regole di configurazione e chiama il plugin appropriato per recapitare il messaggio.

## Requisiti

- Almeno uno tra i plugin **MAIL** o **MESSENGER** deve essere installato e configurato.

## Configurazione

Vai su **Pannello Configurazione → SISTEMA → Notifications** e:
1. Attiva le notifiche globali con il toggle in cima.
2. Aggiungi uno o più **Contatti** nel formato `PLUGIN_TAG:indirizzo`:
   - `MAIL:admin@example.com`
   - `MESSENGER:Telegram:@NomeUtente`
3. Nella tabella **Event Rules**, seleziona i contatti da notificare per ogni evento.
4. Salva e testa con il pulsante **Send Test Notification**.

## Versione

1.0.0
