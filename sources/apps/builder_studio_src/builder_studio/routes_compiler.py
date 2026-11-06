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
from manifest_io import load_manifest, save_manifest, list_preview_images
from compiler import compile_package
from routes_backup import _strip_ansi, _get_repo_root, _backup_live_package


def register_compiler_routes(app, cfg_mgr, hecos_src, log):
    """Registers compiler, batch-build, inspection, keys and unpack endpoints."""

    @app.route('/api/hpm/builder/build', methods=['POST'])
    @login_required
    def builder_build():
        info('Build request received')
        data = request.get_json() or {}
        src_dir = data.get('src_dir')
        manifest = data.get('manifest')

        if not src_dir or not manifest:
            return jsonify({'ok': False, 'error': 'Missing data'})

        if 'readme' not in manifest:
            manifest['readme'] = 'README.md'

        # Ensure README.md actually exists on disk
        readme_path = Path(src_dir) / manifest['readme']
        if not readme_path.exists():
            pkg_name = manifest.get('name', 'Hecos Package')
            pkg_desc = manifest.get('description', '')
            readme_content = f"# {pkg_name}\n\n{pkg_desc}"
            try:
                readme_path.write_text(readme_content, encoding='utf-8')
            except Exception as e:
                return jsonify({'ok': False, 'error': f"Failed to create missing README: {e}"})

        # Fix GitHub raw URLs for store generator
        try:
            imgs = list_preview_images(src_dir)
            if imgs:
                folder_name = Path(src_dir).name
                cat_name = Path(src_dir).parent.name
                base_raw = f"https://raw.githubusercontent.com/Hecos-Project/Hecos-Packages/main/sources/{cat_name}/{folder_name}"
                manifest['screenshots'] = [f"{base_raw}/{img}" for img in imgs]
            else:
                manifest['screenshots'] = []
        except Exception:
            pass

        # Update timestamps
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if not manifest.get('creation_date'):
                manifest['creation_date'] = now
            if not manifest.get('build_date'):
                manifest['build_date'] = now
            else:
                manifest['update_date'] = now
        except Exception:
            pass

        # 1. Save modifications to TOML
        if not save_manifest(src_dir, manifest):
            return jsonify({'ok': False, 'error': 'Failed to save manifest'})

        # 0. Auto Live Backup before compilation
        pkg_id = manifest.get('id', Path(src_dir).name)
        repo_root = _get_repo_root(src_dir)
        live_bk = _backup_live_package(pkg_id, repo_root, log_func=log.info)

        # 2. Compile .hpkg
        out_dir = data.get('out_dir')
        cli_dir = data.get('builder_cli_dir')
        build_res = compile_package(src_dir, out_dir, builder_path=cli_dir)
        if not build_res.get("ok"):
            return jsonify({'ok': False, 'error': build_res.get("error"), 'logs': build_res.get("logs")})

        # Invalidate the store catalog cache so next load fetches fresh data from GitHub
        try:
            hecos_root = Path(__file__).parent.parent.parent
            cache_file = hecos_root / "data" / "store_cache.json"
            if cache_file.exists():
                cache_file.unlink()
                info("Store cache invalidated after build")
        except Exception as e:
            info(f"Could not invalidate store cache: {e}")

        return jsonify({
            'ok': True,
            'out_dir': build_res.get("out_dir"),
            'hpkg_path': build_res.get("hpkg_path"),
            'logs': build_res.get("logs"),
            'live_backup': str(live_bk) if live_bk else None
        })

    @app.route('/api/hpm/builder/batch-build', methods=['POST'])
    @login_required
    def builder_batch_build():
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
            repo_root = _get_repo_root(str(sources_dir))
            for rel_path in packages:
                pkg_path = sources_dir / rel_path
                if pkg_path.exists() and (pkg_path / "hpkg_manifest.toml").exists():
                    m = load_manifest(str(pkg_path))
                    p_id = m.get('id', pkg_path.name) if m else pkg_path.name
                    _backup_live_package(p_id, repo_root, log_func=info)

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

    @app.route('/api/hpm/builder/inspect', methods=['POST'])
    @login_required
    def builder_inspect():
        data = request.get_json() or {}
        pkg_id = data.get('pkg_id', '')
        packages_dir = data.get('packages_dir', r'C:\Hecos-Packages\packages')
        if not pkg_id:
            return jsonify({'ok': False, 'error': 'No pkg_id provided'})

        import zipfile as zf_mod
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        # Glob to handle versioned filenames like id-1.0.0.hpkg
        pkg_root = Path(packages_dir)
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
        data = request.get_json() or {}
        cli_dir = data.get('builder_cli_dir') or r"C:\Hecos-Packages\Hecos_HPM_Builder"
        pkg_id = data.get('pkg_id', '')
        packages_dir = data.get('packages_dir') or r"C:\Hecos-Packages\packages"
        unpack_dest = data.get('unpack_dest') or data.get('src_dir_root') or r"C:\Hecos-Packages\sources"
        if not pkg_id:
            return jsonify({'ok': False, 'error': 'No pkg_id provided'})

        # Find the actual versioned .hpkg file
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
