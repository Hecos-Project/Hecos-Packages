# 📖 Hecos Document Reader

Universal document reader with text-to-speech (TTS) capabilities, visual PDF canvas rendering, direct slash commands, and autonomous LLM system calls for the Hecos ecosystem.

---

## 🌟 Panoramica & Funzionalità

Hecos Document Reader trasforma qualsiasi documento in un audiolibro interattivo e visivo, integrandosi perfettamente nella Web UI di Hecos:

- **Visual PDF Canvas Rendering** — Rendering visivo completo tramite PDF.js. Illustrazioni, diagrammi, fotoromanzi, fumetti e impaginazioni grafiche vengono preservati esattamente come nell'originale.
- **Doppio Motore TTS (Dual TTS Engine)**:
  - **Hecos Local TTS**: Sintesi vocale locale neurale (Piper / Kokoro / XTTS2 / Fish Speech) con caching audio client-side a livello di singola frase e pre-fetching in background.
  - **Browser Web Speech API**: Sintesi istantanea a latenza zero con selezione tra tutte le voci di sistema del browser.
- **Barra di Progressione Pulita con Indicatore Cold-Start Discreto**:
  - **Barra di Lettura Primaria (Viola/Indaco)**: Visualizza la progressione della lettura del documento (frasi lette sul totale), con possibilità di seek istantaneo cliccando in qualsiasi punto.
  - **Indicatore di Caricamento Motore Non Invasivo (Blu/Ciano)**: Si attiva in modo elegante ed esclusivo **soltanto al primo avvio** del motore vocale o durante il **cambio di preset TTS neurale** (es. Piper, Kokoro, XTTS2), mostrando il progresso di caricamento dei pesi in RAM/VRAM.
  - **Esperienza di Lettura Minimale & Senza Distrazioni**: Durante la normale lettura continuativa frase per frase, l'interfaccia rimane completamente pulita e silenziosa (nessuna pillola o barra lampeggiante invasiva), garantendo la massima concentrazione sul documento.
- **Evidenziazione Sincronizzata** — Evidenziazione dinamica della frase corrente e della singola parola pronunciata durante la lettura.
- **Controlli Audiolibro** — Play, Pause, Frase Precedente/Successiva, Stop, Regolazione Velocità Granulare (0.50× – 3.00× con step 0.05), Tonalità e Volume.
- **Navigazione Pagina & Miniature** — Barra laterale con anteprima e miniature per saltare istantaneamente a qualsiasi pagina.
- **Integrazione Chat Automatica** — Aggiunge automaticamente il pulsante *"📖 Read Document"* a tutte le schede documento presenti nella chat.
- **Comandi Diretti (Direct Slash Commands)** — Esecuzione istantanea senza passare dall'LLM.
- **System Calls & Autonomia LLM** — L'AI Hecos può consultare, cercare e aprire documenti in autonomia quando richiesto dall'utente.

---

## ⚡ Comandi Diretti (Direct Slash Commands)

I comandi diretti permettono all'utente (e ai Flussi di automazione) di manovrare il Document Reader all'istante digitando nella chat o nella palette comandi:

| Comando | Alias | Descrizione | Esempio |
| :--- | :--- | :--- | :--- |
| `/read [file]` | `/leggi`, `/reader`, `/docreader`, `/leggi_documento` | Apre e avvia la lettura del documento. Se omesso, apre il selettore e la lista documenti. | `/read fotoromanzo`<br>`/read C:/docs/report.pdf` |
| `/stop_reading` | `/ferma_lettura`, `/stop_doc`, `/stop_reader` | Interrompe immediatamente la lettura vocale attiva. | `/stop_reading` |
| `/read_list` | `/doc_list`, `/lista_lettura` | Elenca tutti i documenti disponibili nella cartella libreria. | `/read_list` |

---

## 🤖 System Calls & Strumenti LLM (Autonomous Tool Calling)

Document Reader espone a Hecos e al modello LLM le seguenti chiamate di sistema (System Calls):

### 1. `DOCUMENT_READER__read_document(path: str)`
Apre un documento nella modalità lettura fullscreen con sintesi vocale.
- **Risoluzione Intelligente & Ricerca Parziale**: Se l'utente chiede:
  > *"Entra nella cartella e leggimi il fotoromanzo numero 1"*
  
  Hecos invoca `read_document(path="fotoromanzo numero 1")` o `path="fotoromanzo"`.
  Il resolver interno esegue la normalizzazione dei token, rimuove le stop-words ed esegue il matching automatico con `Hecos_News_Urania_9800_Fotoromanzo.pdf` all'interno della cartella `hecos/media/documents`!

### 2. `DOCUMENT_READER__stop_reading()`
Interrompe la sessione di lettura vocale in corso tramite l'evento `<docreader-stop>`.

### 3. `DOCUMENT_READER__list_documents(folder: str)`
Scansiona e restituisce la tabella formattata di tutti i documenti leggibili con nome, formato (PDF, TXT, MD, HTML, DOCX) e dimensione.

---

## ⌨️ Controlli con Mouse, Rotellina e Tastiera (Scorciatoie)

Il Document Reader include una gestione avanzata e intuitiva dei controlli di velocità e navigazione:

- **Regolazione Granulare della Velocità (0.50× – 3.00× con step di 0.05)**:
  - **Mouse / Cursore**: Slider dedicato `docreader-speed-slider` per impostare la velocità al millimetro trascinando con il mouse (es. `0.95×`, `1.00×`, `1.05×`, `1.10×`, `1.15×`, `1.20×`, `1.25×`).
  - **Rotellina del Mouse**: Passando il mouse sopra lo slider o il badge della velocità, girare la rotellina in su aumenta la velocità (`+0.05`), girare in giù la diminuisce (`-0.05`).
  - **Reset Rapido**: Cliccando sul badge della velocità (es. `1.15×`), la velocità viene istantaneamente reimpostata a `1.00×`.
  - **Freccette della Tastiera**:
    - **`Freccia Su` (`ArrowUp`)**: Aumenta la velocità di lettura (`+0.05`)
    - **`Freccia Giù` (`ArrowDown`)**: Diminuisce la velocità di lettura (`-0.05`)
    - **`Shift + Freccia Destra` / `Shift + Freccia Sinistra`**: Aumenta / diminuisce la velocità (`±0.05`)
- **Navigazione Documento da Tastiera**:
  - **`Freccia Destra` / `Freccia Sinistra`**: Salta alla frase successiva / precedente
  - **`Spazio`**: Play / Pause della lettura vocale
  - **`Pagina Su` / `Pagina Giù`**: Pagina precedente / successiva
- **`ESC` (Priorità intelligente a due livelli)**:
  - *Prima pressione*: se la voce sta leggendo, **interrompe la sintesi vocale** lasciando il documento aperto a schermo per la consultazione visiva.
  - *Seconda pressione* (o se non sta parlando): **chiude il lettore** e torna alla chat.

---

## 📁 Formati Documento Supportati

- **PDF (`.pdf`)**: Rendering visivo ad alta fedeltà con estrazione testo per frase e parola.
- **Testo Normale (`.txt`)**: Suddivisione automatica in paragrafi e frasi.
- **Markdown (`.md`)**: Lettura strutturata con formattazione visiva.
- **HTML (`.html`, `.htm`)**: Rendering pulito del contenuto testuale ed elementi visivi.
- **Word Document (`.docx`)**: Supporto integrato tramite estrazione testo.

---

## ⚙️ Configurazione (`docreader_config.json`)

Le impostazioni del plugin possono essere modificate graficamente dal pannello di configurazione Hecos (`Impostazioni` → `Document Reader`) oppure tramite il file di configurazione `docreader_config.json`:

```json
{
  "enabled": true,
  "tts_engine": "browser",
  "default_voice": "",
  "default_rate": 1.0,
  "default_pitch": 1.0,
  "highlight_color": "#a78bfa",
  "documents_dir": "C:\\Hecos\\hecos\\media\\documents"
}
```

### Parametri:
- `enabled` *(bool)*: Abilita o disabilita il plugin nel sistema.
- `tts_engine` *(string)*: Motore di sintesi vocale predefinito (`"browser"` o `"local"`).
- `default_voice` *(string)*: Nome della voce predefinita.
- `default_rate` *(float)*: Velocità di riproduzione (da 0.5 a 3.0, default 1.0).
- `default_pitch` *(float)*: Tonalità vocale (da 0.5 a 2.0, default 1.0).
- `highlight_color` *(string)*: Colore esadecimale di evidenziazione del testo letto.

---

## 📦 Struttura del Pacchetto & Build Autonomo

Document Reader è un pacchetto modulare conforme allo standard **Hecos Package Manager (HPM)**.

### Struttura sorgente:
```
document_reader/
├── __init__.py                  # Inizializzatore del modulo Python
├── main.py                      # Entry point con DocumentReaderTools, slash commands e system calls
├── routes.py                    # Route Flask e middleware di auto-iniezione
├── manifest.json                # Specifica HPM runtime (comandi, schema tool, pannello config)
├── hpkg_manifest.toml           # Specifica HPKG con capacità, dipendenze e slash commands
├── docreader_config.json        # Configurazione predefinita
├── README.md                    # Questa documentazione completa
├── build.py                     # Script autonomo di compilazione pacchetto .hpkg
├── web/
│   ├── routes.py                # Route web del plugin
│   ├── static/
│   │   ├── css/
│   │   │   └── document_reader.css   # Stili fullscreen glassmorphism & controlli audio
│   │   └── js/
│   │       ├── document_reader.js       # Core reader con PDF.js canvas & dual TTS
│   │       └── document_reader_panel.js # Logica del pannello di configurazione
│   └── templates/
│       └── config_document_reader.html  # Template HTML del pannello impostazioni
└── static/
    ├── css/
    └── js/
        └── document_reader_chat.js     # Script di auto-iniezione pulsante e tag observer
```

### Compilazione Autonoma del Pacchetto (`.hpkg`):
Per compilare il pacchetto `.hpkg` in completa autonomia, basta eseguire lo script `build.py`:

```bash
python build.py
```

Lo script verificherà l'integrità dei manifest (`manifest.json` e `hpkg_manifest.toml`), impacchetterà tutti gli asset senza file temporanei e genererà il pacchetto validato con checksum SHA256 pronto per l'installazione in `hecos/data/store_cache.json`.
