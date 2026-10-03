import os, sys, re
_cur_dir = os.path.dirname(os.path.abspath(__file__))
if _cur_dir not in sys.path:
    sys.path.insert(0, _cur_dir)

from logger import info, error

from flask import Blueprint, jsonify, request
from flask_login import login_required
from manifest_io import load_manifest, save_manifest, list_preview_images, add_preview_image
from compiler import compile_package

_ANSI_RE = re.compile(r'\x1b(?:\[[0-9;]*[a-zA-Z]|\][^\x07]*\x07)')
def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text or '')

def init_plugin_routes(app, cfg_mgr, hecos_src, log):
    @app.route('/api/hpm/builder/open-folder', methods=['POST'])
    @login_required
    def builder_open_folder():
        import os
        data = request.get_json() or {}
        path = data.get('path')
        if path and os.path.exists(path):
            os.startfile(path)
            return jsonify({'ok': True})
        return jsonify({'ok': False, 'error': 'Path not found'})

    @app.route('/api/hpm/builder/load', methods=['POST'])
    @login_required
    def builder_load():
        info(f'Loading manifest request')
        data = request.get_json() or {}
        src_dir = data.get('src_dir')
        if not src_dir:
            return jsonify({'ok': False, 'error': 'No source directory provided'})
            
        manifest = load_manifest(src_dir)
        if not manifest:
            return jsonify({'ok': False, 'error': 'Manifest not found or invalid'})
            
        images = list_preview_images(src_dir)
        return jsonify({'ok': True, 'manifest': manifest, 'images': images})
        
    @app.route('/api/hpm/builder/build', methods=['POST'])
    @login_required
    def builder_build():
        info(f'Build request received')
        data = request.get_json() or {}
        src_dir = data.get('src_dir')
        manifest = data.get('manifest')
        
        if not src_dir or not manifest:
            return jsonify({'ok': False, 'error': 'Missing data'})
            
        if 'readme' not in manifest:
            manifest['readme'] = 'README.md'
            
        # Ensure README.md actually exists on disk
        from pathlib import Path
        readme_path = Path(src_dir) / manifest['readme']
        if not readme_path.exists():
            pkg_name = manifest.get('name', 'Hecos Package')
            pkg_desc = manifest.get('description', '')
            readme_content = f"# {pkg_name}\n\n{pkg_desc}"
            try:
                readme_path.write_text(readme_content, encoding='utf-8')
            except Exception as e:
                return jsonify({'ok': False, 'error': f"Failed to create missing README: {e}"})
                
        # Fix GitHub raw URLs for store generator (store generator miscalculates folder name case-sensitivity)
        try:
            from manifest_io import list_preview_images
            imgs = list_preview_images(src_dir)
            if imgs:
                folder_name = Path(src_dir).name
                cat_name = Path(src_dir).parent.name
                base_raw = f"https://raw.githubusercontent.com/Hecos-Project/Hecos-Packages/main/sources/{cat_name}/{folder_name}"
                manifest['screenshots'] = [f"{base_raw}/{img}" for img in imgs]
            else:
                manifest['screenshots'] = []
        except:
            pass
                
        # 1. Save modifications to TOML
        if not save_manifest(src_dir, manifest):
            return jsonify({'ok': False, 'error': 'Failed to save manifest'})
            
        # 2. Compile .hpkg
        out_dir = data.get('out_dir')
        cli_dir = data.get('builder_cli_dir')
        build_res = compile_package(src_dir, out_dir, builder_path=cli_dir)
        if not build_res.get("ok"):
            return jsonify({'ok': False, 'error': build_res.get("error"), 'logs': build_res.get("logs")})
        
        # Invalidate the store catalog cache so next load fetches fresh data from GitHub
        try:
            import os
            hecos_src = Path(__file__).parent.parent.parent
            cache_file = hecos_src / "data" / "store_cache.json"
            if cache_file.exists():
                cache_file.unlink()
                info("Store cache invalidated after build")
        except Exception as e:
            info(f"Could not invalidate store cache: {e}")
            
        return jsonify({'ok': True, 'out_dir': build_res.get("out_dir"), 'hpkg_path': build_res.get("hpkg_path"), 'logs': build_res.get("logs")})

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

    @app.route('/api/hpm/builder/scan-sources', methods=['POST'])
    @login_required
    def builder_scan_sources():
        from pathlib import Path
        try:
            data = request.get_json() or {}
            base_dir  = data.get('base_dir') or r"C:\Hecos-Packages\sources"
            out_dir   = data.get('out_dir')  or r"C:\Hecos-Packages\packages"
            sources_dir  = Path(base_dir)
            packages_dir = Path(out_dir)
            sources = []
            if sources_dir.exists():
                for manifest_path in sources_dir.rglob("hpkg_manifest.toml"):
                    parent_dir = manifest_path.parent
                    manifest = load_manifest(str(parent_dir))
                    rel_path = str(parent_dir.relative_to(sources_dir))
                    
                    if manifest:
                        pkg_id      = manifest.get("id", parent_dir.name)
                        pkg_version = manifest.get("version", "1.0.0")
                        # Search for built .hpkg in packages_dir tree
                        hpkg_matches = list(packages_dir.rglob(f"{pkg_id}-{pkg_version}.hpkg"))
                        # Also search by id only (any version)
                        if not hpkg_matches:
                            hpkg_matches = list(packages_dir.rglob(f"{pkg_id}-*.hpkg"))
                        hpkg_path = str(hpkg_matches[0]) if hpkg_matches else ""
                        pkg_info = {
                            "name":     manifest.get("name", parent_dir.name),
                            "version":  pkg_version,
                            "description": manifest.get("description", ""),
                            "type":     manifest.get("type", "plugin"),
                            "rel_path": rel_path,
                            "id":       pkg_id,
                            "built":    bool(hpkg_path),
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
        from pathlib import Path
        import toml
        try:
            data = request.get_json() or {}
            name        = data.get('name', '').strip()
            pkg_id      = (data.get('id') or name).lower().replace(' ', '_')
            version     = data.get('version', '1.0.0').strip()
            author      = data.get('author', '').strip()
            pkg_type    = data.get('type', 'plugin').strip()
            description = data.get('description', '').strip()
            base_dir    = data.get('base_dir', '').strip()

            if not name or not base_dir:
                return jsonify({'ok': False, 'error': 'name and base_dir are required'})

            sources_dir = Path(base_dir)
            pkg_dir = sources_dir / pkg_id
            if pkg_dir.exists():
                return jsonify({'ok': False, 'error': f'Directory already exists: {pkg_dir}'})

            # Create folder structure
            pkg_dir.mkdir(parents=True, exist_ok=True)

            # Write manifest
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

            # Create minimal __init__.py
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
                
            from manifest_io import add_preview_image, list_preview_images
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
                
            from manifest_io import delete_preview_image
            images = delete_preview_image(src_dir, image_name)
            
            return jsonify({'ok': True, 'images': images})
        except Exception as e:
            error(f"Failed to delete image: {e}")
            return jsonify({'ok': False, 'error': str(e)})

    @app.route('/api/hpm/builder/batch-build', methods=['POST'])
    @login_required
    def builder_batch_build():
        from pathlib import Path
        try:
            data = request.get_json() or {}
            packages = data.get('packages', [])
            out_dir = data.get('out_dir')
            base_dir = data.get('base_dir')
            
            if not packages or not base_dir:
                return jsonify({'ok': False, 'error': 'Missing parameters'})
                
            sources_dir = Path(base_dir)
            success_count = 0
            fail_count = 0
            
            info(f"Starting Batch Build for {len(packages)} packages...")
            
            all_logs = []
            for rel_path in packages:
                pkg_path = sources_dir / rel_path
                if pkg_path.exists() and (pkg_path / "hpkg_manifest.toml").exists():
                    # Load name for separator
                    m = load_manifest(str(pkg_path))
                    pkg_display = m.get('name', rel_path) if m else rel_path
                    separator = f"\n{'─' * 48}\n  📦  {pkg_display}\n{'─' * 48}\n"
                    all_logs.append(separator)
                    
                    cli_dir = data.get('builder_cli_dir')
                    result = compile_package(str(pkg_path), out_dir, builder_path=cli_dir)
                    
                    pkg_logs = result.get("logs", "")
                    if pkg_logs:
                        all_logs.append(pkg_logs)
                        
                    if result.get("ok"):
                        success_count += 1
                        all_logs.append(f"[OK] Built → {result.get('hpkg_path', 'done')}\n")
                    else:
                        fail_count += 1
                        all_logs.append(f"[ERROR] Build failed: {result.get('error', 'unknown')}\n")
                else:
                    fail_count += 1
                    error_msg = f"[ERROR] Package at {rel_path} not found in {base_dir}"
                    error(error_msg)
                    all_logs.append(error_msg + "\n")
                    
            combined_logs = "".join(all_logs)
            return jsonify({'ok': True, 'success_count': success_count, 'fail_count': fail_count, 'logs': combined_logs})
        except Exception as e:
            error(f"Batch Build Failed: {e}")
            return jsonify({'ok': False, 'error': str(e)})


    @app.route('/api/hpm/builder/keys', methods=['POST'])
    @login_required
    def builder_keys():
        import subprocess, sys
        data = request.get_json() or {}
        cli_dir = data.get('builder_cli_dir') or r"C:\Hecos-Packages\Hecos_HPM_Builder"
        priv_path = data.get('builder_priv_key') or r"C:\Hecos\hecos\data\trusted_keys\hpm_private.pem"
        pub_path = data.get('builder_pub_key') or r"C:\Hecos\hecos\data\trusted_keys"
        code = (
            f'import sys\n'
            f'sys.path.insert(0, r"{cli_dir}")\n'
            f'from pathlib import Path\n'
            f'import modules.settings\n'
            f'modules.settings.get_private_key_path = lambda: Path(r"{priv_path}")\n'
            f'modules.settings.get_trusted_keys_dir = lambda: Path(r"{pub_path}")\n'
            f'import builtins\n'
            f'builtins.input = lambda _: "y"\n'
            f'from modules.crypto import generate_key_pair\n'
            f'generate_key_pair()\n'
        )
        try:
            res = subprocess.run([sys.executable, "-c", code], cwd=cli_dir, check=True, capture_output=True, text=True)
            return jsonify({'ok': True, 'logs': _strip_ansi(res.stdout)})
        except subprocess.CalledProcessError as e:
            return jsonify({'ok': False, 'error': 'Keys generation failed', 'logs': _strip_ansi(e.stdout + "\n" + e.stderr)})

    @app.route('/api/hpm/builder/catalog', methods=['POST'])
    @login_required
    def builder_catalog():
        import subprocess, sys
        data = request.get_json() or {}
        cli_dir = data.get('builder_cli_dir') or r"C:\Hecos-Packages\Hecos_HPM_Builder"
        code = (
            f'import sys\n'
            f'sys.path.insert(0, r"{cli_dir}")\n'
            f'from modules.store_generator import generate_store_catalog\n'
            f'generate_store_catalog()\n'
        )
        try:
            res = subprocess.run([sys.executable, "-c", code], cwd=cli_dir, check=True, capture_output=True, text=True)
            return jsonify({'ok': True, 'logs': _strip_ansi(res.stdout)})
        except subprocess.CalledProcessError as e:
            return jsonify({'ok': False, 'error': 'Catalog generation failed', 'logs': _strip_ansi(e.stdout + "\n" + e.stderr)})

    @app.route('/api/hpm/builder/install-local', methods=['POST'])
    @login_required
    def builder_install_local():
        data = request.get_json() or {}
        hpkg_path = data.get('hpkg_path', '')
        if not hpkg_path:
            return jsonify({'ok': False, 'error': 'No hpkg_path provided'})
            
        import threading
        import queue
        import json
        from pathlib import Path
        
        if not Path(hpkg_path).exists():
            return jsonify({'ok': False, 'error': f'File not found: {hpkg_path}'})
            
        def _sse(event: str, d: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(d)}\n\n"
            
        def generate():
            yield _sse("progress", {"step": "install", "message": "Installing locally built package..."})
            try:
                # Use the shared HPM helper
                import sys
                from hecos.modules.web_ui.routes_packages_helpers import _get_hpm_components
                registry, installer, _ = _get_hpm_components(r"C:\Hecos\hecos")
                
                q = queue.Queue()
                original_cb = installer._event_callback
                
                def _hpm_event_cb(evt_name, payload):
                    q.put((evt_name, payload))
                    if original_cb:
                        original_cb(evt_name, payload)
                        
                installer._event_callback = _hpm_event_cb
                
                result_box = []
                def _worker():
                    try:
                        res = installer.install_file(
                            hpkg_path=hpkg_path,
                            require_signature=False,
                            skip_dep_check=False,
                        )
                        result_box.append(res)
                    except Exception as e:
                        result_box.append(e)
                    finally:
                        q.put(None)
                        
                t = threading.Thread(target=_worker)
                t.start()
                
                while True:
                    msg = q.get()
                    if msg is None:
                        break
                    evt_name, payload = msg
                    if evt_name == "hpm:progress":
                        yield _sse("progress", payload)
                    elif evt_name == "hpm:error":
                        yield _sse("error", payload)
                    else:
                        yield _sse(evt_name.replace("hpm:", ""), payload)
                        
                t.join()
                installer._event_callback = original_cb
                
                if not result_box:
                    yield _sse("error", {"message": "Installation thread crashed unexpectedly."})
                    return
                
                result = result_box[0]
                if isinstance(result, Exception):
                    yield _sse("error", {"message": f"Installation failed: {result}"})
                    return
                    
                if not result.success:
                    yield _sse("error", {"message": f"Installation failed: {result.error}"})
                    return
                
                pip_installed = []
                if result.dep_report and result.dep_report.pip_installed:
                    pip_installed = result.dep_report.pip_installed
                
                yield _sse("success", {
                    "message": "Installed successfully!",
                    "pip_installed": pip_installed
                })
            except Exception as e:
                yield _sse("error", {"message": f"Unexpected error: {e}"})
                
        from flask import Response
        return Response(generate(), mimetype="text/event-stream")

    @app.route('/api/hpm/builder/dev-sync', methods=['POST'])
    @login_required
    def builder_dev_sync():
        data = request.get_json() or {}
        src_dir = data.get('src_dir', '')
        hecos_root = data.get('hecos_root') or r"C:\Hecos\hecos"
        if not src_dir:
            return jsonify({'ok': False, 'error': 'No src_dir provided'})
        from pathlib import Path
        import shutil
        src = Path(src_dir)
        hecos_hpm = Path(hecos_root) / 'hpm'
        if not hecos_hpm.exists():
            return jsonify({'ok': False, 'error': f'Live HPM folder not found: {hecos_hpm}'})
        pkg_id = src.name.replace('_src', '')
        dest = hecos_hpm / pkg_id
        if not dest.exists():
            dest.mkdir(parents=True, exist_ok=True)
            logs = [f'[INFO] Package folder created: {dest}']
        else:
            logs = []
        try:
            ignore = shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo', '.git')
            shutil.copytree(str(src), str(dest), dirs_exist_ok=True, ignore=ignore)
            logs.append(f'[INFO] Dev Sync OK: {src.name} -> {dest}')
            return jsonify({'ok': True, 'logs': '\n'.join(logs)})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)})

    @app.route('/api/hpm/builder/inspect', methods=['POST'])
    @login_required
    def builder_inspect():
        data = request.get_json() or {}
        pkg_id = data.get('pkg_id', '')
        packages_dir = data.get('packages_dir', r'C:\Hecos-Packages\packages')
        if not pkg_id:
            return jsonify({'ok': False, 'error': 'No pkg_id provided'})
        from pathlib import Path as P
        import zipfile as zf_mod
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        # Glob to handle versioned filenames like id-1.0.0.hpkg
        pkg_root = P(packages_dir)
        matches = list(pkg_root.rglob(f'{pkg_id}*.hpkg'))
        if not matches:
            return jsonify({'ok': False, 'error': f'No .hpkg found for "{pkg_id}" in {packages_dir}'})
        hpkg = matches[0]  # take most recent match
        try:
            with zf_mod.ZipFile(hpkg, 'r') as zf:
                files = zf.namelist()
                if "hpkg_manifest.toml" not in files:
                    return jsonify({'ok': False, 'error': 'No hpkg_manifest.toml inside package'})
                manifest = tomllib.loads(zf.read("hpkg_manifest.toml").decode("utf-8"))
                has_signature = bool(manifest.get("signature"))
                return jsonify({
                    'ok': True,
                    'manifest': manifest,
                    'files': files,
                    'has_signature': has_signature,
                    'file_count': len(files),
                    'size_kb': round(hpkg.stat().st_size / 1024, 1),
                    'hpkg_path': str(hpkg)
                })
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)})

    @app.route('/api/hpm/builder/unpack', methods=['POST'])
    @login_required
    def builder_unpack():
        import subprocess, sys
        data = request.get_json() or {}
        cli_dir = data.get('builder_cli_dir') or r"C:\Hecos-Packages\Hecos_HPM_Builder"
        pkg_id = data.get('pkg_id', '')
        packages_dir = data.get('packages_dir') or r"C:\Hecos-Packages\packages"
        unpack_dest = data.get('unpack_dest') or data.get('src_dir_root') or r"C:\Hecos-Packages\sources"
        if not pkg_id:
            return jsonify({'ok': False, 'error': 'No pkg_id provided'})
        # Find the actual versioned .hpkg file
        from pathlib import Path
        matches = list(Path(packages_dir).rglob(f'{pkg_id}*.hpkg'))
        if not matches:
            return jsonify({'ok': False, 'error': f'No .hpkg found for "{pkg_id}" in {packages_dir}. Build it first.'})
        hpkg_path = str(matches[0])
        hpkg_parent = str(matches[0].parent)
        code = (
            "import sys\n"
            f"sys.path.insert(0, r\"{cli_dir}\")\n"
            "from pathlib import Path\n"
            "import modules.settings\n"
            f"modules.settings.get_src_dir = lambda: Path(r\"{unpack_dest}\")\n"
            f"modules.settings.get_packages_dir = lambda: Path(r\"{hpkg_parent}\")\n"
            "from modules.builder import _unpack_single_package\n"
            f"_unpack_single_package(Path(r\"{hpkg_path}\"), ask_overwrite=False)\n"
        )
        try:
            res = subprocess.run([sys.executable, "-c", code], cwd=cli_dir, check=True, capture_output=True, text=True)
            return jsonify({'ok': True, 'logs': _strip_ansi(res.stdout + res.stderr), 'hpkg_path': hpkg_path})
        except subprocess.CalledProcessError as e:
            return jsonify({'ok': False, 'error': 'Unpack failed', 'logs': _strip_ansi(e.stdout + "\n" + e.stderr)})

    @app.route('/api/hpm/builder/capabilities', methods=['POST'])
    @login_required
    def builder_capabilities():
        import subprocess, sys
        data = request.get_json() or {}
        cli_dir = data.get('builder_cli_dir') or r"C:\Hecos-Packages\Hecos_HPM_Builder"
        src_dir = data.get('src_dir', '')   # if empty: regenerate all packages
        src_root = data.get('src_root') or r"C:\Hecos-Packages\sources"
        if src_dir:
            # Single package: use the low-level auto_generate_capabilities(path)
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
            # All packages
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
