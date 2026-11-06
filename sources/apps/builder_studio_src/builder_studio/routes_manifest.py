import os
import sys
import subprocess
from pathlib import Path

_cur_dir = os.path.dirname(os.path.abspath(__file__))
if _cur_dir not in sys.path:
    sys.path.insert(0, _cur_dir)

from logger import info, error
from flask import jsonify, request
from flask_login import login_required
from manifest_io import (
    load_manifest,
    list_preview_images,
    add_preview_image,
    delete_preview_image
)
from routes_backup import _strip_ansi


def register_manifest_routes(app, cfg_mgr, hecos_src, log):
    """Registers manifest loading, scaffolding wizard, capabilities and media endpoints."""

    @app.route('/api/hpm/builder/open-folder', methods=['POST'])
    @login_required
    def builder_open_folder():
        data = request.get_json() or {}
        raw_path = data.get('path', '')
        if not raw_path:
            return jsonify({'ok': False, 'error': 'No path provided'})

        path = os.path.normpath(str(raw_path).strip().strip('"').strip("'"))
        log.info(f"[Builder] open-folder requested for: {path}")

        target_exists = os.path.exists(path)
        parent_dir = path if os.path.isdir(path) else os.path.dirname(path)

        if not target_exists and not os.path.exists(parent_dir):
            log.warning(f"[Builder] Path not found: {path}")
            return jsonify({'ok': False, 'error': f'Path not found: {path}'})

        try:
            if os.path.isfile(path):
                subprocess.Popen(['explorer', f'/select,{path}'])
            elif os.path.isdir(path):
                os.startfile(path)
            elif os.path.exists(parent_dir):
                os.startfile(parent_dir)
            else:
                subprocess.Popen(['explorer', parent_dir])
            return jsonify({'ok': True})
        except Exception as e:
            try:
                dest = path if os.path.isdir(path) else parent_dir
                subprocess.Popen(['explorer', dest])
                return jsonify({'ok': True})
            except Exception as e2:
                log.error(f"[Builder] Failed to open folder: {e2}")
                return jsonify({'ok': False, 'error': str(e2)})

    @app.route('/api/hpm/builder/load', methods=['POST'])
    @login_required
    def builder_load():
        info('Loading manifest request')
        data = request.get_json() or {}
        src_dir = data.get('src_dir')
        if not src_dir:
            return jsonify({'ok': False, 'error': 'No source directory provided'})

        manifest = load_manifest(src_dir)
        if not manifest:
            return jsonify({'ok': False, 'error': 'Manifest not found or invalid'})

        images = list_preview_images(src_dir)
        return jsonify({'ok': True, 'manifest': manifest, 'images': images})

    @app.route('/api/hpm/builder/scan-sources', methods=['POST'])
    @login_required
    def builder_scan_sources():
        try:
            data = request.get_json() or {}
            base_dir = data.get('base_dir') or r"C:\Hecos-Packages\sources"
            out_dir = data.get('out_dir') or r"C:\Hecos-Packages\packages"
            sources_dir = Path(base_dir)
            packages_dir = Path(out_dir)
            sources = []
            if sources_dir.exists():
                for manifest_path in sources_dir.rglob("hpkg_manifest.toml"):
                    parent_dir = manifest_path.parent
                    manifest = load_manifest(str(parent_dir))
                    rel_path = str(parent_dir.relative_to(sources_dir))

                    if manifest:
                        pkg_id = manifest.get("id", parent_dir.name)
                        pkg_version = manifest.get("version", "1.0.0")
                        hpkg_matches = list(packages_dir.rglob(f"{pkg_id}-{pkg_version}.hpkg"))
                        if not hpkg_matches:
                            hpkg_matches = list(packages_dir.rglob(f"{pkg_id}-*.hpkg"))
                        hpkg_path = str(hpkg_matches[0]) if hpkg_matches else ""
                        pkg_info = {
                            "name": manifest.get("name", parent_dir.name),
                            "version": pkg_version,
                            "description": manifest.get("description", ""),
                            "type": manifest.get("type", "plugin"),
                            "rel_path": rel_path,
                            "id": pkg_id,
                            "built": bool(hpkg_path),
                            "hpkg_path": hpkg_path,
                        }
                    else:
                        pkg_info = {
                            "name": parent_dir.name,
                            "version": "1.0.0",
                            "description": "",
                            "type": "plugin",
                            "rel_path": rel_path,
                            "id": parent_dir.name,
                            "built": False,
                            "hpkg_path": "",
                        }
                    sources.append(pkg_info)

            sources.sort(key=lambda x: x["name"].lower())
            return jsonify({'ok': True, 'sources': sources})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)})

    @app.route('/api/hpm/builder/new-package', methods=['POST'])
    @login_required
    def builder_new_package():
        import toml
        try:
            data = request.get_json() or {}
            name = data.get('name', '').strip()
            pkg_id = (data.get('id') or name).lower().replace(' ', '_')
            version = data.get('version', '1.0.0').strip()
            author = data.get('author', '').strip()
            pkg_type = data.get('type', 'plugin').strip()
            description = data.get('description', '').strip()
            base_dir = data.get('base_dir', '').strip()

            if not name or not base_dir:
                return jsonify({'ok': False, 'error': 'name and base_dir are required'})

            sources_dir = Path(base_dir)
            pkg_dir = sources_dir / pkg_id
            if pkg_dir.exists():
                return jsonify({'ok': False, 'error': f'Directory already exists: {pkg_dir}'})

            pkg_dir.mkdir(parents=True, exist_ok=True)

            manifest = {
                'id': pkg_id,
                'name': name,
                'version': version,
                'author': author,
                'description': description,
                'type': pkg_type,
                'license': 'MIT',
                'capabilities': {},
            }
            with open(pkg_dir / 'hpkg_manifest.toml', 'w', encoding='utf-8') as f:
                toml.dump(manifest, f)

            init_content = f'''# {name}
# Author: {author}
# Version: {version}
# Type: {pkg_type}

"""
{description or name}
"""
'''
            with open(pkg_dir / '__init__.py', 'w', encoding='utf-8') as f:
                f.write(init_content)

            info(f"New package created: {pkg_dir}")
            return jsonify({'ok': True, 'path': str(pkg_dir)})
        except Exception as e:
            error(f"Failed to create new package: {e}")
            return jsonify({'ok': False, 'error': str(e)})

    @app.route('/api/hpm/builder/add-image', methods=['POST'])
    @login_required
    def builder_add_image():
        data = request.get_json() or {}
        src_dir = data.get('src_dir')
        image_path = data.get('image_path')

        if not src_dir or not image_path:
            return jsonify({'ok': False, 'error': 'Missing parameters'})

        try:
            new_name = add_preview_image(src_dir, image_path)
            images = list_preview_images(src_dir)
            return jsonify({'ok': True, 'new_name': new_name, 'images': images})
        except Exception as e:
            error(f"Failed to add image: {e}")
            return jsonify({'ok': False, 'error': str(e)})

    @app.route('/api/hpm/builder/add-image-upload', methods=['POST'])
    @login_required
    def builder_add_image_upload():
        try:
            src_dir = request.form.get('src_dir')
            if 'file' not in request.files or not src_dir:
                return jsonify({'ok': False, 'error': 'Missing file or src_dir'})

            file = request.files['file']
            if file.filename == '':
                return jsonify({'ok': False, 'error': 'No selected file'})

            add_preview_image(src_dir, file_data=file)
            images = list_preview_images(src_dir)
            return jsonify({'ok': True, 'images': images})
        except Exception as e:
            error(f"Failed to upload image: {e}")
            return jsonify({'ok': False, 'error': str(e)})

    @app.route('/api/hpm/builder/delete-image-upload', methods=['POST'])
    @login_required
    def builder_delete_image_upload():
        try:
            data = request.get_json() or {}
            src_dir = data.get('src_dir')
            image_name = data.get('image_name')

            if not src_dir or not image_name:
                return jsonify({'ok': False, 'error': 'Missing src_dir or image_name'})

            images = delete_preview_image(src_dir, image_name)
            return jsonify({'ok': True, 'images': images})
        except Exception as e:
            error(f"Failed to delete image: {e}")
            return jsonify({'ok': False, 'error': str(e)})

    @app.route('/api/hpm/builder/capabilities', methods=['POST'])
    @login_required
    def builder_capabilities():
        data = request.get_json() or {}
        cli_dir = data.get('builder_cli_dir') or r"C:\Hecos-Packages\Hecos_HPM_Builder"
        src_dir = data.get('src_dir', '')   # if empty: regenerate all packages
        src_root = data.get('src_root') or r"C:\Hecos-Packages\sources"
        if src_dir:
            code = (
                "import sys\n"
                f"sys.path.insert(0, r\"{cli_dir}\")\n"
                "from pathlib import Path\n"
                "import modules.settings\n"
                f"modules.settings.get_src_dir = lambda: Path(r\"{src_root}\")\n"
                "from modules.capabilities_gen import auto_generate_capabilities\n"
                f"result = auto_generate_capabilities(Path(r\"{src_dir}\"))\n"
                "print('[INFO] Capabilities updated.' if result else '[ERROR] Capabilities update failed.')\n"
            )
        else:
            code = (
                "import sys\n"
                f"sys.path.insert(0, r\"{cli_dir}\")\n"
                "from pathlib import Path\n"
                "import modules.settings\n"
                f"modules.settings.get_src_dir = lambda: Path(r\"{src_root}\")\n"
                "from modules.capabilities_gen import generate_all_capabilities\n"
                "generate_all_capabilities()\n"
            )
        try:
            res = subprocess.run([sys.executable, "-c", code], cwd=cli_dir, check=True, capture_output=True, text=True)
            return jsonify({'ok': True, 'logs': _strip_ansi(res.stdout + res.stderr)})
        except subprocess.CalledProcessError as e:
            return jsonify({'ok': False, 'error': 'Capabilities generation failed', 'logs': _strip_ansi(e.stdout + "\n" + e.stderr)})
