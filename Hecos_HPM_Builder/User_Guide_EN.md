# Hecos Package Maker — Complete User Guide

## What is HPM Builder?

**HPM Builder** (`Hecos_Package_Maker.bat`) is the official tool to create, sign, and distribute `.hpkg` packages for Hecos.
It is located in the folder `C:\Hecos-Packages\Hecos_HPM_Builder\`.

---

## First Time: Initial Configuration

If this is your first time using the tool, follow these steps in order.

### Step 1 — Generate Cryptographic Keys

Every package must be **digitally signed** by your private key, and Hecos will verify the signature using your public key.

1. Open `Hecos_Package_Maker.bat` with a double click.
2. Select `1. [KEY] Generate Keys`.
3. The script will automatically create two files in `C:\Hecos\hecos\data\trusted_keys\`:
   - `hpm_private.pem` → **Your private key. Never share it!**
   - `hpm_public.pem` → The public key, used by Hecos to verify packages.

> [!CAUTION]
> The **private** key (`hpm_private.pem`) must never be shared or sent to anyone.
> If you lose it or it is compromised, all packages signed with it become untrusted.

> [!NOTE]
> The public key (`hpm_public.pem`) is already in the Hecos `trusted_keys` folder, so Hecos will recognize it automatically without additional configuration.

---

## How to Create a New Package from Scratch

### Step 2 — Scaffold (Create the base structure)

1. Open `Hecos_Package_Maker.bat`.
2. Select `2. [NEW] Scaffold New Package`.
3. Enter the **Package ID** (all lowercase, no spaces, e.g.: `my_plugin`).
4. Enter the **human-readable name** (e.g.: `My Awesome Plugin`).
5. Choose the type: `plugin`, `module`, or `theme`.

The script will automatically create the `my_plugin_src\` folder in `C:\Hecos-Packages\` with this structure:

```
my_plugin_src/
├── hpkg_manifest.toml      ← The "brain" of the package, edit it!
├── plugin/
│   └── my_plugin/
│       └── __init__.py     ← Python backend entry point
└── web_ui/
    ├── templates/
    │   └── config_my_plugin.html  ← Config Hub Panel
    └── static/
        └── js/
            └── my_plugin_panel.js ← Panel JS logic
```

### Step 3 — Modify the files

Open the generated folder and modify:
- **`hpkg_manifest.toml`**: Enter the description, FontAwesome icon, category, and verify file paths.
- **`plugin/my_plugin/__init__.py`**: Write the Python logic of your plugin.
- **The HTML/JS files**: Create the panel in the Config Hub.

---

## How to Build an Existing Package

### (For ready packages, like `voice_visualizer_src`)

1. Open `Hecos_Package_Maker.bat`.
2. Select `3. [BLD] Validate & Build Package`.
3. Choose the number corresponding to the `_src` folder of the package.

The script will execute in order:
1. **Parsing** → Reads and verifies the syntax of `hpkg_manifest.toml`.
2. **Validation** → Checks that the files declared in the manifest (HTML, JS, CSS) physically exist.
3. **Hashing** → Calculates the SHA-256 checksum of each file and injects it into the manifest.
4. **Signing** → Cryptographically signs the manifest with your Ed25519 private key.
5. **Archive** → Creates the `.hpkg` file in `C:\Hecos-Packages\packages\`.

Expected output if everything goes well:

```
[INFO] Validating package 'Voice Visualizer'...
[INFO] Calculating file hashes...
[INFO] Generating payload for cryptographic signature...
[INFO] Signature applied successfully.
[INFO] Creating compressed archive voice_visualizer-1.0.0.hpkg...
[INFO] DONE -> C:\Hecos-Packages\packages\voice_visualizer-1.0.0.hpkg (11.2 KB)
```

---

## How to Install a Package in Hecos

1. Open the browser at `https://localhost:7070/hecos/config/ui#packages`.
2. In the **Packages** tab, click on **Install Package**.
3. Select the newly created `.hpkg` file (it will be located in `C:\Hecos-Packages\packages\`).
4. Hecos verifies the signature, extracts the files, and reloads the UI.

---

## Advanced Tools (New in v1.4.0)

HPM Builder offers many other advanced tools from the main menu:
- **`8. [EDT] Edit Manifest`**: Interactive editor to quickly update Version, Name, Author, and Description without opening the TOML file manually.
- **`D. [SYNC] Dev Sync`**: Instantly synchronize your changes from the `_src` folder to the live Hecos folder to test code in real-time, without having to rebuild the `.hpkg`.
- **`C. [CAP] Auto-Generate Capabilities`**: Scans the code to extract LLM Tools, slash commands, and widgets, automatically inserting them into the manifest to let Antigravity understand what the package does.
- **`I. [INFO]` / `A. [ALLI]`**: Prints handy "Package Info Sheets" on the screen, with all features and capabilities clearly summarized.
- **`9. [CAT] Build Store Catalog`**: Creates the `index.json` file useful if you want to upload your packages to a repository or a custom online Store.

---

## Reference: `hpkg_manifest.toml` Structure

```toml
id = "my_plugin"                # Unique ID, only lowercase and underscores
name = "My Plugin"              # Human-readable name
version = "1.0.0"               # Semantic version X.Y.Z
hecos_min_version = "0.35.0"    # Minimum required Hecos version
type = "plugin"                 # plugin | module | theme
author = "Your name"
description = "Short description of the package."
target_dir = "plugins"

# Config Hub Panel (optional)
[config_panel]
tab_id = "my_plugin"
tab_label = "My Plugin"
tab_icon = "fa-cube"            # FontAwesome class e.g. fa-wifi, fa-robot
category = "CONNETTIVITA"
template_file = "web_ui/templates/config_my_plugin.html"
js_file = "web_ui/static/js/my_plugin_panel.js"
# css_file = "web_ui/static/css/my_plugin.css"  # Optional

# Dashboard Widget (optional)
[[widgets]]
extension_path = "web_ui/extensions/my_widget"
```

---

## Frequently Asked Questions

**Q: The package is installed but the widget does not appear?**
A: Restart Hecos to force the reload of Python plugins. JS/CSS files are loaded dynamically without restarting.

**Q: "Package is NOT signed" error during installation?**
A: The private key (`hpm_private.pem`) was not found at build time. Check that it exists in `C:\Hecos\hecos\data\trusted_keys\`. If it is not there, use option `1. [KEY]` to generate it, then rebuild with `3. [BLD]`.

**Q: Can I distribute packages to other users?**
A: Yes. Provide both the `.hpkg` file and your public key (`hpm_public.pem`). Users must add it to their `trusted_keys` folder for Hecos to accept your packages.

**Q: How do I update an already installed package?**
A: Increase `version` in the manifest (e.g., `1.0.0` → `1.1.0`), rebuild, and reinstall.

**Q: Where can I find valid icons for `tab_icon`?**
A: Search on fontawesome.com/icons (version 5 Free). Use only the class name, e.g.: `fa-wifi` (not `fas fa-wifi`).
