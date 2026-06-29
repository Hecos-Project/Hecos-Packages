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

### Default Configurations (Injected into YAML) — ⚠️ LEGACY / AVOID
When installed, HPM can inject defaults into `hecos/config/data/system.yaml` via `[config_defaults]`.
**This is NOT the recommended approach** for new packages (see "Autonomous Config" section below).
The only valid use of `[config_defaults]` is to declare `enabled = true` so that
the Central Hub knows the plugin is active. All other settings must live in the package's own TOML.
```toml
[config_defaults]
enabled = true   # ← Only this. Nothing else.
```

### ✅ Autonomous Package Configuration (THE STANDARD)

**Every HPM package must manage its own configuration independently, without touching `system.yaml`.**
This is the pattern established by `image_gen` and must be followed by all packages.

**The pattern:**
1. Inside your package, create a `<pkg>_config/` folder with:
   - `defaults.toml` — factory defaults, shipped with the package (read-only)
   - `config_manager.py` — reads/writes a `<pkg>.toml` file in the same directory
   - `__init__.py` — empty or re-exports `get_config`, `save_config`
2. In your `hpkg_manifest.toml`, declare `api_routes_file = "web/routes.py"` and expose GET/POST endpoints.
3. Your config panel HTML fetches from those endpoints (not from `window.cfg`).

**`config_manager.py` skeleton:**
```python
import os
from pathlib import Path
try:
    import tomllib
except ImportError:
    import tomli as tomllib
import tomli_w

_THIS_DIR    = Path(__file__).parent.resolve()
_DEFAULTS    = _THIS_DIR / "defaults.toml"
_CONFIG_FILE = _THIS_DIR / "my_plugin.toml"   # created at runtime

def get_config() -> dict:
    if not _CONFIG_FILE.exists():
        _CONFIG_FILE.write_bytes(_DEFAULTS.read_bytes())
    return tomllib.loads(_CONFIG_FILE.read_bytes().decode("utf-8"))

def save_config(data: dict) -> bool:
    _CONFIG_FILE.write_bytes(tomli_w.dumps(data).encode("utf-8"))
    return True
```

**`hpkg_manifest.toml` declaration:**
```toml
[config_panel]
tab_id           = "my_plugin"
tab_label        = "My Plugin"
tab_icon         = "fa-puzzle-piece"    # Just the FontAwesome class, NO <i> tags
category         = "SISTEMA"
template_file    = "web/templates/config_my_plugin.html"
js_file          = "web/static/js/my_plugin_panel.js"
api_routes_file  = "web/routes.py"
config_api_get   = "/hecos/api/plugins/my_plugin/config"
config_api_post  = "/hecos/api/plugins/my_plugin/config"

[config_defaults]
enabled = true   # ← ONLY this. Tells the Hub this plugin is active.
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
- **CRITICAL — `data-icon-injected="true"`:** Hecos has an automatic icon injector that scans every `.card-title` and prepends an icon. If your `card-title` uses `display:flex` (to separate a title from action buttons on the right), add `data-icon-injected="true"` to the `div`. Otherwise the injector will insert a second icon, break the flex layout, and push your text to the center.
  ```html
  <!-- ✅ Correct — tells the injector to leave this alone -->
  <div class="card-title" data-icon-injected="true" style="display:flex; justify-content:space-between; align-items:center;">
      <span><i class="fas fa-clock"></i> My Panel</span>
      <div><!-- action buttons --></div>
  </div>
  ```
- **State initialization:** Because your HTML is lazy-loaded and injected dynamically by the Hub, `DOMContentLoaded` won't work inside your panel JS. Use a `MutationObserver` to detect when your `#tab-YOUR_TAB_ID` is added to the DOM to initialize things like dropdowns.
- **Saving state:** Use your own custom endpoints defined in `api_routes_file` to persist configuration autonomously to your module's TOML file. Do NOT call `window.saveConfig(true)` (that writes to `system.yaml`). For notifications, use `window.showToast(msg, 'success'|'error')` and `window.hpmShowConfirm(msg, btnLabel, callback)`.

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

---

## 🧠 6. Lessons Learned & Gotchas (The "Wisdom")

During the development and extraction of built-in modules into `.hpkg` packages, we encountered several common pitfalls. Keep these in mind to save debugging time:

1. **Exact File Naming and Paths**
   - The HPM unpacking engine relies on strict path mapping. If your TOML says `js_file = "web_ui/static/js/my_panel.js"`, ensure the file is *exactly* there in your `_src` folder.
   - Watch out for typos in the TOML paths! A wrong path means the file won't be copied, and the UI will fail to load or find the JS/CSS.

2. **Dynamic UI Persistence (The "No-Refresh" Rule)**
   - When a user installs, uninstalls, enables, or disables a package from the Package Manager, **the UI must update instantly without requiring a page refresh or reboot.**
   - **For Config Panels:** Hecos caches panels in `window._panelCache`. When your package is disabled, Hecos will automatically evict the panel from the DOM and cache. Make sure your JS handles re-initialization if the user re-enables the package and clicks the tab again.
   - **For Widgets:** If your package injects a widget into the Control Room or Sidebar, the frontend will attempt to load or remove the widget dynamically. Ensure your widget scripts don't break if loaded multiple times or if their DOM elements disappear suddenly.

3. **Widget Layout Conflicts**
   - If your package injects custom layouts or alters the grid (e.g., resizing grid columns), be careful not to override or conflict with other widgets.
   - **Never activate mutually exclusive layout switches simultaneously** in your testing or defaults, as this will break the CSS Grid and cause widgets to overlap or become unclickable.

4. **DOM Initialization**
   - Because panels and widgets are often lazy-loaded (injected via `fetch` after the initial page load), standard events like `window.addEventListener('DOMContentLoaded', ...)` **will not fire** for your scripts.
   - **Solution:** Use inline scripts that execute immediately upon injection, or attach a `MutationObserver` to watch for your specific `#tab-YOUR_ID` or `#widget-YOUR_ID` appearing in the DOM to run your setup logic.

5. **Package ID Matching**
   - Ensure the `id` in your manifest exactly matches the folder naming conventions if you are overriding `tab_id`. Mismatches between the package `id`, the `tab_id`, and the actual ID of the `<div>` inside your HTML template are the #1 cause of "Panel not found" errors.

6. **Config Autonomy — Never Write to `system.yaml` / `plugins.yaml`**
   - Built-in modules used `system.yaml` and `plugins.yaml` for their settings. **HPM packages must NOT do this.**
   - Each package owns its configuration in a `<pkg>_config/` subfolder, with a `defaults.toml` (factory defaults, read-only) and a `<pkg>.toml` (user config, created at first run).
   - Only `enabled = true` goes in `[config_defaults]` so the Hub knows the plugin is active. **All other settings go in the package's own TOML.**
   - See the `image_gen` package (`igen_config/config_manager.py`) as the reference implementation.

7. **`tab_icon` — Class Only, No HTML Tags**
   - In `[config_panel]`, set `tab_icon` to just the FontAwesome class name (e.g., `"fa-clock"`), **not** a full `<i>` HTML tag.
   - The Hub renderer wraps it automatically: `<i class="fas fa-clock"></i>`.
   - If you put `<i class="fas fa-clock"></i>` in the TOML, the renderer will double-wrap it, producing broken HTML and two icons in the sidebar.

8. **Hub Tab Visibility After Refresh**
   - If your package tab disappears from the sidebar after a page refresh but comes back after toggling enable/disable, the cause is always one of:
     a. `enabled = true` is missing from `[config_defaults]` in the manifest (so `system.yaml` has no entry, and the Hub can't determine the plugin state).
     b. The `[config_defaults]` `enabled` key was NOT written to `system.yaml` because an old `disabled` entry already existed (the installer uses `if existing.get(k) is None`, so it won't overwrite `false`). The force-enable in the install route handles this, but if you see the bug, check `system.yaml` for your plugin's `UPPER_TAG.enabled` value.

9. **Backend Panel Caching (`_HPM_PANEL_CACHE`)**
   - Hecos heavily caches the discovered panel paths in `routes_config_core.py` (via `_HPM_PANEL_CACHE`) to speed up tab rendering.
   - If you manually copy templates or bypass the HPM installer during development, the backend might cache `None` for your panel ID. 
   - **Solution:** You must restart Hecos or call `clear_hpm_panel_cache()` dynamically to force the backend to re-discover your `config_YOUR_ID.html` template.

10. **Widget Visibility upon Reactivation (`room_visible`)**
    - When a package is disabled via the Package Manager, all its widgets are hidden by setting `enabled`, `visible`, and `room_visible` to `False` in the backend state.
    - When reactivating the package, the backend must restore `room_visible = True` in addition to `visible = True`. If you skip `room_visible`, the widget will be treated as active but confined to the "Sidebar", meaning it will NOT appear in the central Control Room layout by default, leading to user confusion ("the widget is on but I can't see it").
