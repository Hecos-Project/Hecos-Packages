# Hecos-Packages Repository

Community and official packages for the Hecos ecosystem.

## Structure

Each package lives in its own folder:
```
Hecos-Packages/
├── webcam_widget/          # Widget: Live webcam feed
│   ├── hpkg_manifest.toml  ← Package manifest (source of truth)
│   ├── main.py             ← Python backend (optional for pure widgets)
│   └── templates/
│       └── *.html          ← Widget HTML template
│
├── weather/                # Hybrid: Plugin + Widget
│   ├── hpkg_manifest.toml
│   ├── main.py             ← Python plugin (LLM tools)
│   └── widget/
│       └── *.html          ← Sidebar widget template
│
└── ...
```

## Package Types

| Type     | Description |
|----------|-------------|
| `widget` | Frontend-only UI widget (sidebar/room). No LLM tools. |
| `plugin` | Python backend with LLM tools. No visual widget. |
| `hybrid` | Both: Python plugin + sidebar widget. |

## Building a .hpkg File

A `.hpkg` file is simply a ZIP archive renamed to `.hpkg`:
```powershell
Compress-Archive -Path .\webcam_widget\* -DestinationPath .\webcam_widget-1.0.0.hpkg
```
Then upload the `.hpkg` file to the Hecos Package Manager.

## Manifest Format

See any `hpkg_manifest.toml` for the full format. Minimum required:
```toml
[package]
name    = "My Package"
tag     = "MY_PKG"
version = "1.0.0"
type    = "widget"  # or "plugin" or "hybrid"
```
