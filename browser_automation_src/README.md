# 🌐 Hecos AI Browser Automation

Provides a programmable, AI-controlled browser for Hecos. Navigate the web, read pages, fill forms and interact with any site — all from natural language in chat.

---

## ✨ Features

- Navigate URLs, read DOM content, click elements, fill forms
- Two modes: **CDP Takeover** (hook into your real Chrome/Edge) and **App Mode** (isolated Chromium)
- No coordinate guessing — uses semantic DOM selectors
- Ad blocker, headless mode, multi-tab support
- Full configuration panel in the Hecos Config Hub

---

## 🚀 Installation

Install via the Hecos Package Manager (HPM). After installation, if you want to use **App Mode**, install the Chromium binary:

```bash
python -m playwright install chromium
```

---

## ⚙️ Browser Modes

### 🎯 Mode 1: Your Real Browser (CDP Takeover) — *Recommended*

Hecos "undercover" takes control of your existing Google Chrome or Edge. It sees your extensions, active logins, bookmarks and cookies.

**Requirement:** Chrome must be launched with the remote debugging flag:

```
chrome.exe --remote-debugging-port=9222
```

> You can create a desktop shortcut with this parameter, or use the **"Avvia Chrome con debug"** button in the config panel.

**Advantages:**
- Access to your real sessions (Gmail, LinkedIn, etc.)
- No separate browser download needed
- Multi-tab support via `BROWSER__list_tabs` and `BROWSER__switch_tab`

---

### 🧪 Mode 2: Isolated AI Browser (App Mode)

Hecos uses a dedicated Chromium browser, completely separate from yours. No access to your passwords or saved sessions.

**Advantages:**
- Privacy — no access to your personal data
- Great for background web searches without disturbing you
- Runs headlessly in the background

---

## 💬 Slash Commands

Type these commands directly in chat to control the browser instantly.

| Command | Alias | Description | Example |
|---------|-------|-------------|---------|
| `/browser <url>` | `/b`, `/apri`, `/open` | Opens a URL in the Hecos AI browser | `/browser youtube.com` |
| `/b_close` | — | Closes the AI browser | `/b_close` |
| `/b_tabs` | — | Shows a list of open tabs | `/b_tabs` |
| `/screen` | `/screenshot`, `/vedi` | Takes a screenshot of the current page and shows it in chat | `/screen` |

---

## 🤖 LLM Tools (AI Commands)

These tools are used automatically by the AI during conversations. You can also ask for them explicitly in natural language.

| Tool | Description | Example prompt |
|------|-------------|----------------|
| `BROWSER__open_url` | Opens a URL in the browser | *"Apri Amazon.it"* |
| `BROWSER__get_page_text` | Reads all visible text on the current page | *"Cosa c'è scritto qui?"* |
| `BROWSER__get_links` | Lists all hyperlinks on the page | *"Mostrami tutti i link di questa pagina"* |
| `BROWSER__get_inputs` | Lists all form fields and buttons | *"Quali campi ha questo form?"* |
| `BROWSER__get_title` | Returns the current page title | *"Che pagina è aperta?"* |
| `BROWSER__get_current_url` | Returns the current URL | *"Qual è l'URL corrente?"* |
| `BROWSER__click_element` | Clicks an element by visible text or CSS selector | *"Clicca sul pulsante Accetta"* |
| `BROWSER__type_in_field` | Types text into a form field | *"Cerca 'Python tutorial' su Google"* |
| `BROWSER__scroll` | Scrolls the page up or down | *"Scorri in basso"* |
| `BROWSER__press_key` | Presses a keyboard key | *"Premi Invio"* |
| `BROWSER__run_js` | Executes JavaScript on the current page | *"Esegui document.title in JS"* |
| `BROWSER__screenshot` | Takes a viewport screenshot for visual AI analysis | *"Fai uno screenshot di questa pagina"* |
| `BROWSER__list_tabs` | Lists all open browser tabs (CDP only) | *"Quante tab ho aperte?"* |
| `BROWSER__switch_tab` | Switches to a specific tab by ID | *"Passa alla tab di YouTube"* |
| `BROWSER__new_tab` | Opens a new tab | *"Apri una nuova tab su google.com"* |
| `BROWSER__close_tab` | Closes the current tab | *"Chiudi questa tab"* |
| `BROWSER__go_back` | Navigates back | *"Torna indietro"* |
| `BROWSER__close` | Closes the entire browser | *"Chiudi il browser"* |

---

## 📖 Practical Examples

### 🔍 Web search and reading
```
"Cerca su Google 'migliori ristoranti Roma 2024' e dimmi i primi risultati"
→ Hecos opens Google, searches, reads results and replies.

"Apri Wikipedia e cercami la pagina sull'Intelligenza Artificiale. Riassumi l'intro."
→ Navigation + reading + summary in one message.
```

### 📝 Form filling (CDP Mode)
```
"Vai su mail.google.com, clicca su 'Scrivi' e compila il destinatario con mario@rossi.it,
 oggetto 'Ciao' e testo 'Come stai?'"
→ Works in CDP mode because Hecos uses YOUR Chrome with your saved credentials.
```

### 📸 Screenshot and visual analysis
```
"/browser amazon.it → /screen → 'Cosa vedi? Ci sono offerte del giorno?'"
→ Open, take screenshot, AI analyzes the image visually.
```

### 🗂️ Multi-tab management (CDP Mode)
```
"Quante tab ho aperte in Chrome? Mostrami i titoli"
→ Hecos lists all your real Chrome tabs.

"Passa alla tab di YouTube e dimmi che video sta suonando"
→ switch_tab + get_page_text to read the current video title.
```

---

## 🔒 Privacy & Security

| Mode | Access to your data | Recommended for |
|------|---------------------|-----------------|
| CDP Takeover | ✅ Sees logins, cookies, sessions | Tasks requiring authentication |
| App Mode | ❌ Completely isolated | Anonymous browsing, web scraping |

---

## 📝 Notes

- In CDP mode, Hecos first tries to connect to your Chrome. If it fails, it automatically falls back to AUTOMATION mode to find open windows.
- The `BROWSER__screenshot` tool returns a file path; the vision AI can analyze it to describe the page visually.
- For YouTube playback: use `run_js("document.querySelector('video').play()")` if `click_element('play')` doesn't work.
