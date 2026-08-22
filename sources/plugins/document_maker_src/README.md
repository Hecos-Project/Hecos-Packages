# Document Maker

Official HPM module for generating PDF documents from HTML templates or raw content.

## Description

The **Document Maker** plugin allows Urania (Hecos' AI) to create professional PDF documents — magazines, reports, flyers, brochures — directly from the chat, without any external tools.

It leverages the `browser_automation` core module (Playwright) already integrated into Hecos, ensuring:
- 100% accurate visual rendering (CSS, backgrounds, images, fonts)
- Cross-platform support (Windows, Linux, macOS)
- No heavy additional dependencies (uses the existing isolated Chromium instance)

## LLM Tools

| Tool | Description |
|---|---|
| `DOCS__generate_pdf` | Converts raw HTML or an existing template into a PDF file and returns the absolute path |

### Parameters of `DOCS__generate_pdf`

| Parameter | Type | Description |
|---|---|---|
| `html_content` | string | Raw HTML to convert (optional if `template_id` is used) |
| `template_id` | string | ID or name of an existing template (optional if `html_content` is used) |
| `template_vars` | string | JSON containing variables to inject into the template (e.g. `{"title": "Hello"}`) |
| `filename` | string | Output PDF filename (optional, default: UUID) |

## Slash Commands

| Command | Description |
|---|---|
| `/pdf`, `/makepdf` | Quickly generates a PDF document from an HTML text or a Hecos template. |

## Usage Example

> "Create a magazine about our new product, generate the PDF, and send it to me via email."

Urania will sequentially call:
1. `TEMPLATES__create_template` — creates the HTML template
2. `DOCS__generate_pdf` — generates the PDF from the template
3. `MAIL__send_email` — sends the PDF as an attachment

## Dependencies

- `templates` plugin (for template rendering)
- `browser_automation` core module with Playwright and Chromium installed
