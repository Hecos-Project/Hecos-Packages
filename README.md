# 📦 Hecos Package Development Guide

Welcome to the **Hecos Package Ecosystem**! This guide provides everything developers and AIs need to know to create, structure, and distribute packages (`.hpkg`) for the Hecos platform.

Hecos Packages are modular, hybrid bundles that can contain:
- **Backend Plugins** (Python logic, LLM tools, Slash commands)
- **Frontend Widgets** (HTML/JS/CSS for the Sidebar or Control Room)
- **Central Hub Config Panels** (UI interfaces to configure the module)
- **Extensions & MCP** (Integrations with the core system)

---

## 📂 1. Directory Structure

A typical Hecos package source folder follows this structure:

```text
my_weather_pkg_src/
├── hpkg_manifest.toml             # [REQUIRED] The source of truth for the package.
├── main.py                        # [OPTIONAL] Python backend (LLM logic, API calls).
├── templates/                     # [OPTIONAL] Widget UI (Sidebar / Control Room).
│   └── my_weather_widget.html
└── web_ui/                        # [OPTIONAL] Central Hub config panel files.
    ├── templates/
    │   └── config_my_weather.html # HTML fragment for the Hub panel.
    └── static/js/
        └── my_weather_panel.js    # JS logic for the config panel.
```

---

## 📜 2. The `hpkg_manifest.toml`

The manifest is the core of any Hecos package. The Package Manager (`HPM`) uses it to register everything dynamically.

### Basic Package Info
```toml
id          = "weather_pro"         # Unique identifier (lowercase, underscores)
name        = "Weather Pro"         # Display Name
version     = "1.0.0"
hecos_min_version = "0.34.0"        # Minimum required Hecos version
type        = "plugin"              # core_module | plugin | app | extension | widget | persona | theme | skill_pack
author      = "Hecos Team"
description = "Hybrid weather module with LLM tools, widget, and config panel."
icon_url    = "https://example.com/icon.png"       # (Optional) Store catalog icon
screenshots = ["https://example.com/preview.png"]  # (Optional) Store catalog previews
```

### Runtime Configuration
```toml
tag            = "WEATHER_PRO"      # Global uppercase tag used in plugins.yaml
lazy_load      = true               # If true, loaded only when needed by LLM
is_class_based = true               # If true, Hecos instantiates it as a class

# Target directory is now AUTO-RESOLVED based on the 'type' field.
# e.g., 'app' -> 'apps/', 'persona' -> 'personas/', 'plugin' -> 'plugins/'
# You can override it explicitly using target_dir if absolutely necessary.
plugin_dir  = "plugin/weather_pro/" # Path inside the ZIP containing the backend code
```

### LLM Tools & Function Calling
Declare the schema so the Hecos AI knows how to use your module.
```toml
[[tool_schema]]
type = "function"
[tool_schema.function]
name = "WEATHER_PRO__get_current_weather"
description = "Get the current weather conditions for a specific city."
[tool_schema.function.parameters]
type = "object"
[tool_schema.function.parameters.properties.city]
type = "string"
```

### Slash Commands
Register commands that the user can type in the chat UI.
```toml
[[slash_commands]]
command = "/weather"
description = "Show current weather (/weather Rome)"
method = "get_current_weather"      # Method mapped in main.py
[slash_commands.args_schema]
city = "str?"
```

### Autonomous API Routes (Optional)
If your package needs its own backend endpoints (e.g., to manage its own independent configuration, load presets, or proxy external API calls securely), specify a Python file that exposes an `init_plugin_routes(app, cfg_mgr, root_dir, logger)` function.
```toml
api_routes_file = "web/routes.py"
```

### Central Hub Config Panel (Auto-Discovery)
Allows your module to inject a settings tab directly into the Central Hub.
```toml
[config_panel]
tab_id        = "weather_pro"       # Tab ID (creates #tab-weather_pro)
tab_label     = "Weather Pro"       # Name on the button
tab_icon      = "fa-cloud-sun"      # FontAwesome icon
category      = "CONNETTIVITÀ"      # Under which Hub Category it appears
template_file = "web_ui/templates/config_weather_pro.html"
js_file       = "web_ui/static/js/weather_pro_panel.js"
```

### Default Configurations (Injected into YAML)
When installed, HPM injects these into `hecos/config/data/plugins.yaml`.
**Important**: Use a flat `[config_defaults]` table. HPM automatically nests it under `plugins.YOUR_TAG`.
```toml
[config_defaults]
default_city = "Rome"
units        = "celsius"
```

### Sidebar / Control Room Widgets
Inject UI directly into the Hecos workspace.
```toml
[[widgets]]
extension_path = "web_ui/extensions/weather_pro_widget/"
```

### Dependencies
```toml
dependencies          = ["some_core_pkg"] # Hard requirements (blocks install if missing)
optional_dependencies = ["voice_pack"]    # Enhancements (warns only, does not block)
pip_requirements      = ["requests", "pytz"] # Python pip packages
```

---

## 🎨 3. Central Hub Config Panels

To make your module configurable, you can integrate a custom UI panel into the Hecos Central Hub.

**How it works:**
1. You declare `[config_panel]` in your manifest.
2. The HPM Installer extracts your HTML into `hecos/modules/web_ui/templates/modules/`.
3. When the user opens the Hub, Hecos calls `GET /api/hub/panels`, reads your package from SQLite, and automatically generates the navigation buttons in the chosen `category`.
4. Your HTML fragment is lazy-loaded (only fetched when the user clicks the tab).

**Best Practices for HTML UI:**
- Wrap everything in `<div id="tab-YOUR_TAB_ID" class="panel">`.
- Use the Hecos platform CSS classes:
  - `.card` for container blocks.
  - `.card-title` for section headers.
  - `.field`, `.config-input`, `.btn btn-primary` for forms.
  - `.toggle-row` and `.switch` for ON/OFF checkboxes.
- **State initialization:** Because your HTML is lazy-loaded and injected dynamically by the Hub, `DOMContentLoaded` won't work inside your panel JS. Use a `MutationObserver` to detect when your `#tab-YOUR_TAB_ID` is added to the DOM to initialize things like dropdowns.
- **Saving state:** You can hook into the global `window.saveConfig(true)` to save settings to the master YAML, or use your own custom endpoints defined in `api_routes_file` to persist configuration autonomously to your module's directory. For modern custom dialogs (alerts, confirms), use `window.showToast(msg, 'success'|'error')` and `window.hpmShowConfirm(msg, btnLabel, callback)`.

---

## 🔐 4. Security & Cryptographic Signing

Hecos enforces a strict verification process for packages to prevent malicious code execution.

### Dev Mode (Unsigned Packages)
If you are developing locally, you can create a simple ZIP archive and rename the extension to `.hpkg`. To install it, you must check the **"Allow unsigned packages"** checkbox in the Package Manager.

### Production (Signed Packages)
For distribution, packages must be cryptographically signed using Ed25519 keys.

1. **Generate a Keypair:**
   Use the Hecos compiler/CLI tool to generate your Author Keys.
   *This outputs a `private.pem` (keep secret!) and a `public.pem`.*
   
2. **Whitelisting:**
   To be trusted globally by a vanilla Hecos installation, your public key must be included in the `core/package_manager/trusted_keys/` folder of the official Hecos distribution, or the user must manually import your public key.

3. **Signing Process:**
   The compiler hashes all files in your package, creates a cryptographic signature using your private key, and embeds `manifest.json`, `signature.sig`, and `public.pem` into the final `.hpkg` ZIP container.

---

## 🛠️ 5. Packaging Process

Currently, you can package a module in two ways:

**Method A: Simple ZIP (Unsigned)**
```powershell
# Navigate into your package source folder
cd my_weather_pkg_src

# Zip all contents (not the parent folder itself)
Compress-Archive -Path * -DestinationPath ../weather_pro-1.0.0.hpkg
```
*Note: Must be installed with "Allow unsigned packages" enabled.*

**Method B: Hecos HPM Builder (Official CLI)**
For structured repositories (like the `Hecos-Packages` folder), use the official HPM Builder CLI (`Hecos_HPM_Builder/main.py`). The builder provides an interactive menu to handle the entire package lifecycle:
- **Build Packages**: Validates your TOML, generates file hashes, applies cryptographic signatures (Ed25519), and compiles into a `.hpkg` bundle. You can build a single package or **Build All** `*_src` folders at once.
- **Unpack Packages**: Extracts any `.hpkg` back into an editable `[ID]_src` folder for reverse engineering or modification.
- **Scaffold & Inspect**: Helps create new package skeletons and validates existing bundles for security and integrity.

---

## 💡 Quick Tips for AIs & Developers
- **Modularity:** Always check if your logic is better suited as a native Core Module (for heavy OS integration) or as a `.hpkg` (for dynamic, distributable features).
- **CSS Isolation:** When writing widgets or config panels, avoid polluting global CSS. Use specific IDs or inline variables.
- **Auto-Discovery:** Hecos handles Hub injection automatically. **Do not** manually edit core files like `config_manifest.js` or `_PANEL_MAP` in `routes_config_core.py` when creating a package.
