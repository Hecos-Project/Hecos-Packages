import sys
import os
import json
import zipfile
from pathlib import Path

sys.path.append('C:\\Hecos-Packages\\Hecos_HPM_Builder')
from modules.settings import load_config, get_packages_dir
from modules.builder import *
from modules.crypto import sha256_file, sign_payload

load_config()

packages_dir = get_packages_dir()
src_dirs = [d for d in packages_dir.iterdir() if d.is_dir() and d.name.endswith('_src')]

for target_dir in src_dirs:
    print('Building:', target_dir.name)
    manifest_path = target_dir / 'hpkg_manifest.toml'
    manifest = tomllib.loads(manifest_path.read_bytes().decode('utf-8'))
    file_hashes = {}
    files_to_pack = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for fname in files:
            full = Path(root) / fname
            rel = full.relative_to(target_dir).as_posix()
            if rel in ('hpkg_manifest.toml', 'hpkg_manifest.json'):
                continue
            files_to_pack.append((full, rel))
            file_hashes[rel] = sha256_file(full)
    manifest['file_hashes'] = file_hashes
    
    payload_dict = dict(manifest)
    payload_dict.pop('signature', None)
    payload_bytes = json.dumps(payload_dict, sort_keys=True, separators=(',', ':')).encode('utf-8')
    signature_b64 = sign_payload(payload_bytes)
    if signature_b64:
        manifest['signature'] = signature_b64
    
    try:
        import tomli_w
        final_toml = tomli_w.dumps(manifest).encode('utf-8')
    except:
        final_toml = _json_to_toml(manifest).encode('utf-8')
        
    pkg_name = f"{manifest['id']}-{manifest['version']}.hpkg"
    out_path = packages_dir / pkg_name
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('hpkg_manifest.toml', final_toml)
        for full, rel in files_to_pack:
            zf.write(full, rel)
    print('Built:', out_path)
