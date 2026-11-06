import os
import sys
import re
import shutil
import sqlite3
import datetime
from pathlib import Path

_cur_dir = os.path.dirname(os.path.abspath(__file__))
if _cur_dir not in sys.path:
    sys.path.insert(0, _cur_dir)

from logger import info, error
from flask import jsonify, request
from flask_login import login_required

_ANSI_RE = re.compile(r'\x1b(?:\[[0-9;]*[a-zA-Z]|\][^\x07]*\x07)')


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text or '')


def _get_repo_root(src_dir_or_pkg_path: str) -> Path:
    """Finds the repository root (e.g. C:\\Hecos-Packages or C:\\Hecos-Elite) containing 'sources' or 'packages'."""
    try:
        p = Path(src_dir_or_pkg_path).resolve()
        for parent in [p] + list(p.parents):
            if (parent / 'sources').is_dir() or (parent / 'packages').is_dir():
                return parent
    except Exception:
        pass
    return Path(r"C:\Hecos-Packages")


def _find_live_package_path(pkg_id: str, hecos_root: str = r"C:\Hecos\hecos", pkg_type: str = None) -> Path | None:
    """Locates the live (installed) directory of a package within Hecos."""
    live_path = None
    db_path = Path(hecos_root) / 'data' / 'packages.db'
    if not db_path.is_file():
        db_path = Path(r"C:\Hecos\hecos\data\packages.db")

    candidates = []
    for cand in [pkg_id, pkg_id.replace('_', '-'), pkg_id.replace('-', '_')]:
        if cand and cand not in candidates:
            candidates.append(cand)

    if db_path.is_file():
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            for cand in candidates:
                cursor.execute(
                    "SELECT install_path FROM packages WHERE id = ? OR name = ?",
                    (cand, cand)
                )
                row = cursor.fetchone()
                if row and row[0] and Path(row[0]).is_dir():
                    live_path = Path(row[0])
                    break
            conn.close()
        except Exception as e_db:
            info(f"[BUILDER] packages.db check failed: {e_db}")

    if not live_path:
        base_dir = Path(hecos_root)
        subdirs = [
            'modules', 'hpm', 'hpm/playbooks', 'hpm/libraries',
            'hpm/plugins', 'hpm/skill_packs', 'plugins', 'personas', 'themes', 'widgets'
        ]
        if pkg_type:
            type_dir_map = {
                "core_module": "modules",
                "system_app": "modules",
                "generic_module": "hpm",
                "plugin": "hpm",
                "library": "hpm",
                "extension": "hpm",
                "app": "hpm",
                "persona": "personas",
                "theme": "themes",
                "playbook": "hpm/playbooks",
                "skill_pack": "hpm/skill_packs",
            }
            pref = type_dir_map.get(pkg_type)
            if pref and pref in subdirs:
                subdirs.remove(pref)
                subdirs.insert(0, pref)

        for sub in subdirs:
            for cand in candidates:
                test_path = base_dir / sub / cand
                if test_path.is_dir():
                    live_path = test_path
                    break
            if live_path:
                break

    return live_path


def _backup_live_package(pkg_id: str, repo_root: Path, hecos_root: str = r"C:\Hecos\hecos", log_func=None) -> Path | None:
    """
    Creates an automatic full copy of the live installed package before building or installing.
    Destination: <repo_root>/livebackup/<pkg_id>_<timestamp>/ and <repo_root>/livebackup/<pkg_id>_latest/
    """
    if not pkg_id:
        return None
    try:
        live_path = _find_live_package_path(pkg_id, hecos_root)
        if not live_path or not live_path.is_dir():
            msg = f"[LIVE-BACKUP] No live version found for '{pkg_id}' in {hecos_root} (skipping auto-backup)."
            if log_func:
                log_func(msg)
            return None

        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        livebackup_root = repo_root / "livebackup"
        dest_timestamp = livebackup_root / f"{pkg_id}_{timestamp}"
        dest_latest = livebackup_root / f"{pkg_id}_latest"

        dest_timestamp.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(live_path), str(dest_timestamp), dirs_exist_ok=True)

        # Also maintain a ready-to-inspect latest mirror
        shutil.copytree(str(live_path), str(dest_latest), dirs_exist_ok=True)

        msg = f"[LIVE-BACKUP] Auto live backup created for '{pkg_id}' -> {dest_timestamp}"
        if log_func:
            log_func(msg)
        info(msg)
        return dest_timestamp
    except Exception as e:
        err_msg = f"[LIVE-BACKUP] Failed to create auto live backup for '{pkg_id}': {e}"
        if log_func:
            log_func(err_msg)
        error(err_msg)
        return None


def register_backup_routes(app, cfg_mgr, hecos_src, log):
    """Registers live-backup and package-backup routes."""

    @app.route('/api/hpm/builder/live-backup', methods=['POST'])
    @login_required
    def builder_live_backup():
        data = request.get_json() or {}
        hecos_root = data.get('hecos_root') or r"C:\Hecos\hecos"
        backup_dir = data.get('backup_dir')
        if not backup_dir:
            backup_dir = os.path.join(os.path.expanduser('~'), 'Desktop', 'HecosBackups')

        try:
            hpm_dir = Path(hecos_root) / 'hpm'
            live_builder = hpm_dir / 'builder_studio'

            if not live_builder.exists():
                return jsonify({'ok': False, 'error': 'Live builder_studio non trovato in hpm'})

            out_path = Path(backup_dir)
            out_path.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f'builder_studio_live_{timestamp}'
            archive_path = out_path / backup_name

            shutil.make_archive(str(archive_path), 'zip', str(live_builder))

            return jsonify({'ok': True, 'msg': f'Backup salvato in {archive_path}.zip'})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)})

    @app.route('/api/hpm/builder/backup-package', methods=['POST'])
    @login_required
    def builder_backup_package():
        data = request.get_json() or {}
        pkg_id = data.get('pkg_id')
        hecos_root = data.get('hecos_root') or r"C:\Hecos\hecos"
        dest_dir = data.get('dest_dir')
        if not pkg_id:
            return jsonify({'ok': False, 'error': 'No pkg_id specified.'})
        if not dest_dir:
            return jsonify({'ok': False, 'error': 'No destination folder specified.'})

        try:
            live_path = _find_live_package_path(pkg_id, hecos_root)
            if not live_path:
                return jsonify({'ok': False, 'error': f'Live version of {pkg_id} not found in the installation.'})

            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_folder_name = f'{pkg_id}_{timestamp}'
            dest_path = Path(dest_dir) / backup_folder_name
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.copytree(str(live_path), str(dest_path), dirs_exist_ok=True)

            return jsonify({'ok': True, 'msg': f'LIVE backup of {pkg_id} copied to:\n{dest_path}'})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)})
