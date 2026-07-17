# Hecos Package Maker — Guida Utente Completa

## Cos'è HPM Builder?

**HPM Builder** (`Hecos_Package_Maker.bat`) è il tool ufficiale per creare, firmare e distribuire pacchetti `.hpkg` per Hecos.
Si trova nella cartella `C:\Hecos-Packages\Hecos_HPM_Builder\`.

---

## Prima Volta: Configurazione Iniziale

Se è la prima volta che usi lo strumento, segui questi passaggi nell'ordine indicato.

### Step 1 — Genera le chiavi crittografiche

Ogni pacchetto deve essere **firmato digitalmente** dalla tua chiave privata, e Hecos verificherà la firma usando la tua chiave pubblica.

1. Apri `Hecos_Package_Maker.bat` con un doppio click.
2. Seleziona `1. [KEY] Generate Keys`.
3. Lo script creerà automaticamente due file in `C:\Hecos\hecos\data\trusted_keys\`:
   - `hpm_private.pem` → **La tua chiave privata. Non condividerla mai!**
   - `hpm_public.pem` → La chiave pubblica, usata da Hecos per verificare i pacchetti.

> [!CAUTION]
> La chiave **privata** (`hpm_private.pem`) non deve mai essere condivisa o inviata a nessuno.
> Se la perdi o la comprometti, tutti i pacchetti firmati con essa diventano inaffidabili.

> [!NOTE]
> La chiave pubblica (`hpm_public.pem`) è già nella cartella `trusted_keys` di Hecos, quindi Hecos la riconoscerà automaticamente senza configurazioni aggiuntive.

---

## Come Creare un Nuovo Pacchetto da Zero

### Step 2 — Scaffold (Crea la struttura base)

1. Apri `Hecos_Package_Maker.bat`.
2. Seleziona `2. [NEW] Scaffold New Package`.
3. Inserisci il **Package ID** (tutto minuscolo, niente spazi, es: `my_plugin`).
4. Inserisci il **nome leggibile** (es: `My Awesome Plugin`).
5. Scegli il tipo: `plugin`, `module` o `theme`.

Lo script creerà automaticamente in `C:\Hecos-Packages\` la cartella `my_plugin_src\` con questa struttura:

```
my_plugin_src/
├── hpkg_manifest.toml      ← Il "cervello" del pacchetto, editalo!
├── plugin/
│   └── my_plugin/
│       └── __init__.py     ← Entry point Python del backend
└── web_ui/
    ├── templates/
    │   └── config_my_plugin.html  ← Pannello Config Hub
    └── static/
        └── js/
            └── my_plugin_panel.js ← Logica JS del pannello
```

### Step 3 — Modifica i file

Apri la cartella generata e modifica:
- **`hpkg_manifest.toml`**: Inserisci la descrizione, l'icona FontAwesome, la categoria e verifica i percorsi dei file.
- **`plugin/my_plugin/__init__.py`**: Scrivi la logica Python del tuo plugin.
- **I file HTML/JS**: Crea il pannello nel Config Hub.

---

## Come Impacchettare un Pacchetto Esistente

### (Per pacchetti già pronti, come `voice_visualizer_src`)

1. Apri `Hecos_Package_Maker.bat`.
2. Seleziona `3. [BLD] Validate & Build Package`.
3. Scegli il numero corrispondente alla cartella `_src` del pacchetto.

Lo script eseguirà nell'ordine:
1. **Parsing** → Legge e verifica la sintassi del `hpkg_manifest.toml`.
2. **Validazione** → Controlla che i file dichiarati nel manifest (HTML, JS, CSS) esistano fisicamente.
3. **Hashing** → Calcola il checksum SHA-256 di ogni file e lo inietta nel manifest.
4. **Firma** → Firma crittograficamente il manifest con la tua chiave privata Ed25519.
5. **Archivio** → Crea il file `.hpkg` in `C:\Hecos-Packages\`.

Output atteso se tutto va bene:

```
[INFO] Validating package 'Voice Visualizer'...
[INFO] Calculating file hashes...
[INFO] Generating payload for cryptographic signature...
[INFO] Signature applied successfully.
[INFO] Creating compressed archive voice_visualizer-1.0.0.hpkg...
[INFO] DONE -> C:\Hecos-Packages\packages\voice_visualizer-1.0.0.hpkg (11.2 KB)
```

---

## Come Installare un Pacchetto in Hecos

1. Apri il browser su `https://localhost:7070/hecos/config/ui#packages`.
2. Nella tab **Packages**, clicca su **Install Package**.
3. Seleziona il file `.hpkg` appena creato (si troverà in `C:\Hecos-Packages\packages\`).
4. Hecos verifica la firma, estrae i file, e ricarica la UI.

---

## Strumenti Avanzati (Novità v1.4.0)

L'HPM Builder offre molti altri strumenti avanzati dal menu principale:
- **`8. [EDT] Edit Manifest`**: Editor interattivo per aggiornare velocemente Versione, Nome, Autore e Descrizione senza aprire il file TOML a mano.
- **`D. [SYNC] Dev Sync`**: Sincronizza istantaneamente le tue modifiche dalla cartella `_src` alla cartella live di Hecos per provare il codice in tempo reale, senza dover ricompilare il `.hpkg`.
- **`C. [CAP] Auto-Generate Capabilities`**: Scansiona il codice per estrarre LLM Tools, comandi slash e widget, inserendoli automaticamente nel manifest per far capire ad Antigravity cosa fa il pacchetto.
- **`I. [INFO]` / `A. [ALLI]`**: Stampa a schermo delle pratiche "Schede Informative" dei pacchetti, con tutte le caratteristiche e capacità riassunte chiaramente.
- **`9. [CAT] Build Store Catalog`**: Crea il file `index.json` utile se vuoi caricare i tuoi pacchetti in un repository o in uno Store online personalizzato.

---

## Riferimento: Struttura del `hpkg_manifest.toml`

```toml
id = "my_plugin"                # ID univoco, solo minuscole e underscore
name = "My Plugin"              # Nome leggibile
version = "1.0.0"               # Versione semantica X.Y.Z
hecos_min_version = "0.35.0"   # Versione minima di Hecos richiesta
type = "plugin"                 # plugin | module | theme
author = "Il tuo nome"
description = "Descrizione breve del pacchetto."
target_dir = "plugins"

# Pannello nel Config Hub (opzionale)
[config_panel]
tab_id = "my_plugin"
tab_label = "My Plugin"
tab_icon = "fa-cube"            # Classe FontAwesome es. fa-wifi, fa-robot
category = "CONNETTIVITA"
template_file = "web_ui/templates/config_my_plugin.html"
js_file = "web_ui/static/js/my_plugin_panel.js"
# css_file = "web_ui/static/css/my_plugin.css"  # Opzionale

# Widget Dashboard (opzionale)
[[widgets]]
extension_path = "web_ui/extensions/my_widget"
```

---

## Domande Frequenti

**D: Il pacchetto viene installato ma il widget non appare?**
R: Riavvia Hecos per forzare il reload dei plugin Python. I file JS/CSS vengono caricati dinamicamente senza riavvio.

**D: Errore "Package is NOT signed" nell'installazione?**
R: La chiave privata (`hpm_private.pem`) non è stata trovata al momento della compilazione.
Controlla che esista in `C:\Hecos\hecos\data\trusted_keys\`. Se non c'è, usare l'opzione `1. [KEY]` per generarla, poi ricompilare con `3. [BLD]`.

**D: Posso distribuire i pacchetti ad altri utenti?**
R: Sì. Fornisci sia il file `.hpkg` che la tua chiave pubblica (`hpm_public.pem`). Gli utenti devono aggiungerla nella loro cartella `trusted_keys` perché Hecos accetti i tuoi pacchetti.

**D: Come aggiorno un pacchetto già installato?**
R: Aumenta `version` nel manifest (es. `1.0.0` → `1.1.0`), ricompila, e reinstalla.

**D: Dove trovo le icone valide per `tab_icon`?**
R: Cerca su fontawesome.com/icons (versione 5 Free). Usa solo il nome classe, es: `fa-wifi` (non `fas fa-wifi`).
