# Hecos AI Browser Automation

Provides a programmable, AI-controlled Chromium browser (via Playwright) for Hecos.

## Features

- Navigate URLs, read DOM content, click elements, fill forms
- Two modes: **App Mode** (isolated Chromium) and **CDP Takeover** (hook into your real Chrome/Edge)
- No coordinate guessing — uses semantic DOM selectors
- Ad blocker, headless mode, multi-tab support
- Full Config Hub panel with live settings

## Installation

Install via the Hecos Package Manager (HPM). After installation, run:

```
python -m playwright install chromium
```

to install the Chromium browser binary (required for App Mode).

## CDP Mode (Takeover)

To use your real Chrome or Edge browser, launch it with:

```
chrome.exe --remote-debugging-port=9222
```

Then switch to CDP Mode in the Config Hub → AI Browser panel.

## Available Tools (LLM)

| Tool | Description |
|------|-------------|
| `BROWSER__open_url` | Navigate to a URL |
| `BROWSER__get_page_text` | Read all visible text from the current page |
| `BROWSER__get_links` | List all hyperlinks on the page |
| `BROWSER__get_inputs` | List all form elements |
| `BROWSER__click_element` | Click by visible text or selector |
| `BROWSER__type_in_field` | Type into a form field |
| `BROWSER__scroll` | Scroll the page |
| `BROWSER__press_key` | Press a keyboard key |
| `BROWSER__run_js` | Execute JavaScript |
| `BROWSER__screenshot` | Take a viewport screenshot |
| `BROWSER__list_tabs` | List all open tabs |
| `BROWSER__switch_tab` | Switch to a specific tab |
| `BROWSER__new_tab` | Open a new tab |
| `BROWSER__close_tab` | Close current tab |
| `BROWSER__close` | Close the browser |
| `BROWSER__get_current_url` | Get current URL |
| `BROWSER__go_back` | Navigate back |
| `BROWSER__get_title` | Get page title |

## Requirements

- `playwright >= 1.40.0`
- Chromium binaries (install with `python -m playwright install chromium`)

## License

GPL-3.0 — Antonio Meloni / Hecos Project
