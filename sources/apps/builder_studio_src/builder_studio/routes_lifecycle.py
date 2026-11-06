import os
import sys
import json
import queue
import shutil
import sqlite3
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timezone

_cur_dir = os.path.dirname(os.path.abspath(__file__))
if _cur_dir not in sys.path:
    sys.path.insert(0, _cur_dir)

from logger import info, error
from flask import jsonify, request, Response
from flask_login import login_required
from manifest_io import save_manifest
from routes_backup import (
    _strip_ansi,
    _get_repo_root,
    _find_live_package_path,
    _backup_live_package
)


def register_lifecycle_routes(app, cfg_mgr, hecos_src, log):
    """Registers package catalog generation, local installation and dev-sync routes."""

    @app.route('/api/hpm/builder/catalog', methods=['POST'])
    @login_required
    def builder_catalog():
        data = request.get_json() or {}
        cli_dir = data.get('builder_cli_dir') or r"C:\Hecos-Packages\Hecos_HPM_Builder"
        repo_dir = (data.get('repo_root') or data.get('repo_dir') or '').replace('\\', '/')
        packages_dir = (data.get('packages_dir') or data.get('repo_dest') or '').replace('\\', '/')
        sources_dir = (data.get('sources_dir') or data.get('repo_src') or '').replace('\\', '/')
        github_repo = data.get('github_repo', '')

        args = []
        if repo_dir:
            args.append(f'repo_dir=r"{repo_dir}"')
        if packages_dir:
            args.append(f'packages_dir=r"{packages_dir}"')
        if sources_dir:
            args.append(f'sources_dir=r"{sources_dir}"')
        if github_repo:
            args.append(f'github_repo=r"{github_repo}"')
        args_str = ", ".join(args)

        code = (
            f'import sys\n'
            f'sys.path.insert(0, r"{cli_dir}")\n'
            f'from modules.store_generator import generate_store_catalog\n'
            f'generate_store_catalog({args_str})\n'
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

        if not Path(hpkg_path).exists():
            return jsonify({'ok': False, 'error': f'File not found: {hpkg_path}'})

        def _sse(event: str, d: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(d)}\n\n"

        def generate():
            # Auto Live Backup before installing
            try:
                import zipfile
                try:
                    import tomllib
                except ImportError:
                    import tomli as tomllib

                with zipfile.ZipFile(hpkg_path, 'r') as zf:
                    if 'hpkg_manifest.toml' in zf.namelist():
                        m_data = tomllib.loads(zf.read('hpkg_manifest.toml').decode('utf-8'))
                        p_id = m_data.get('id')
                        if p_id:
                            r_root = _get_repo_root(hpkg_path)
                            bk_path = _backup_live_package(p_id, r_root, log_func=log.info)
                            if bk_path:
                                yield _sse("progress", {"step": "backup", "message": f"Auto live backup created: {bk_path.name}"})
            except Exception as e_bk:
                log.warning(f"[Builder] Auto live backup before install note: {e_bk}")

            yield _sse("progress", {"step": "install", "message": "Installing locally built package..."})
            try:
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

        return Response(generate(), mimetype="text/event-stream")

    @app.route('/api/hpm/builder/dev-sync', methods=['POST'])
    @login_required
    def builder_dev_sync():
        data = request.get_json() or {}
        src_dir = data.get('src_dir', '')
        hecos_root = data.get('hecos_root') or r"C:\Hecos\hecos"
        if not src_dir:
            return jsonify({'ok': False, 'error': 'No src_dir provided'})

        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        src = Path(src_dir)
        if not src.exists():
            return jsonify({'ok': False, 'error': f'Source directory not found: {src_dir}'})

        manifest_data = data.get('manifest')
        manifest = {}
        manifest_path = src / "hpkg_manifest.toml"
        if manifest_data and isinstance(manifest_data, dict):
            manifest = dict(manifest_data)
        elif manifest_path.is_file():
            try:
                manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as e_toml:
                info(f"[BUILDER] Could not parse hpkg_manifest.toml in {src}: {e_toml}")

        pkg_id = data.get('pkg_id') or manifest.get('id') or src.name.replace('_src', '')
        plugin_dir = manifest.get('plugin_dir')
        pkg_type = manifest.get('type')
        pkg_name = manifest.get('name', pkg_id)

        # 1. Locate LIVE package installation folder
        live_path = _find_live_package_path(pkg_id, hecos_root, pkg_type=pkg_type)
        if not live_path:
            return jsonify({
                'ok': False,
                'error': f"Live version of package '{pkg_id}' not found in the installation ({hecos_root})."
            })

        # 2. Determine target destination directory inside sources (Live -> Source)
        dest_dir = src
        if plugin_dir and plugin_dir != ".":
            clean_plugin_dir = plugin_dir.strip("/\\")
            if (src / clean_plugin_dir).is_dir():
                dest_dir = src / clean_plugin_dir
        elif plugin_dir == "." or (src / "main.py").is_file():
            dest_dir = src
        elif (src / pkg_id).is_dir():
            dest_dir = src / pkg_id
        elif (src / pkg_id.replace('-', '_')).is_dir():
            dest_dir = src / pkg_id.replace('-', '_')
        elif (src / pkg_id.replace('_', '-')).is_dir():
            dest_dir = src / pkg_id.replace('_', '-')

        try:
            ignore = shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo', '.git', 'Thumbs.db')
            shutil.copytree(str(live_path), str(dest_dir), dirs_exist_ok=True, ignore=ignore)

            # Sync root README.md if dest_dir is a nested folder and live has README.md
            if dest_dir != src and (live_path / "README.md").is_file() and (src / "README.md").is_file():
                try:
                    shutil.copy2(str(live_path / "README.md"), str(src / "README.md"))
                except Exception:
                    pass

            # 3. Save / Update Manifest if passed from Workbench
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if manifest_data and isinstance(manifest_data, dict):
                manifest['update_date'] = now_str
                save_manifest(str(src), manifest)
                info(f"[BUILDER] Saved updated manifest to {src / 'hpkg_manifest.toml'}")

                # Update manifest.json in src and dest_dir if present
                for m_json_path in [src / "manifest.json", dest_dir / "manifest.json"]:
                    if m_json_path.is_file():
                        try:
                            with open(m_json_path, "r", encoding="utf-8") as f:
                                mj = json.load(f)
                            if "version" in manifest:
                                mj["version"] = manifest["version"]
                            if "name" in manifest:
                                mj["name"] = manifest["name"]
                            if "description" in manifest:
                                mj["description"] = manifest["description"]
                            with open(m_json_path, "w", encoding="utf-8") as f:
                                json.dump(mj, f, indent=4, ensure_ascii=False)
                        except Exception as e_mj:
                            info(f"[BUILDER] Could not update {m_json_path}: {e_mj}")

                # Sync manifest to live_path if present
                if (live_path / "hpkg_manifest.toml").is_file():
                    try:
                        save_manifest(str(live_path), manifest)
                    except Exception:
                        pass
                if (live_path / "manifest.json").is_file():
                    try:
                        with open(live_path / "manifest.json", "r", encoding="utf-8") as f:
                            mj = json.load(f)
                        if "version" in manifest:
                            mj["version"] = manifest["version"]
                        if "name" in manifest:
                            mj["name"] = manifest["name"]
                        if "description" in manifest:
                            mj["description"] = manifest["description"]
                        with open(live_path / "manifest.json", "w", encoding="utf-8") as f:
                            json.dump(mj, f, indent=4, ensure_ascii=False)
                    except Exception:
                        pass

                # Update packages.db version & name
                try:
                    db_path = Path(hecos_root) / 'data' / 'packages.db'
                    if db_path.is_file():
                        conn = sqlite3.connect(str(db_path))
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE packages SET version = ?, name = ?, updated_at = ? WHERE id = ? OR install_path = ?",
                            (manifest.get('version'), manifest.get('name'), now_str, pkg_id, str(live_path))
                        )
                        conn.commit()
                        conn.close()
                except Exception as e_db:
                    info(f"[BUILDER] Could not update packages.db: {e_db}")

            file_count = sum(len(files) for _, _, files in os.walk(str(dest_dir)))
            ver_info = f" (v{manifest.get('version')})" if manifest.get('version') else ""
            logs = [
                f"[INFO] Package: {pkg_name} ({pkg_id}){ver_info}",
                f"[INFO] Live path: {live_path}",
                f"[INFO] Target source: {dest_dir}",
                f"[INFO] Dev Sync OK: Live files and manifest synced to local source ({file_count} files in source)."
            ]
            info(f"[BUILDER] Dev Sync OK: {live_path} -> {dest_dir}")
            return jsonify({
                'ok': True,
                'logs': '\n'.join(logs),
                'live_path': str(live_path),
                'dest_dir': str(dest_dir),
                'pkg_id': pkg_id,
                'version': manifest.get('version')
            })
        except Exception as e:
            error(f"[BUILDER] Dev Sync error: {e}")
            return jsonify({'ok': False, 'error': str(e)})
