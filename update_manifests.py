import os
import re
from pathlib import Path

target_dir = Path(r"C:\Hecos-Packages\sources")
src_dirs = [d for d in target_dir.rglob("*_src") if d.is_dir()]

for d in src_dirs:
    manifest_path = d / "hpkg_manifest.toml"
    if not manifest_path.exists():
        continue
    
    with open(manifest_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Update author
    if re.search(r'^author\s*=\s*".*"', content, flags=re.MULTILINE):
        content = re.sub(r'^author\s*=\s*".*"', 'author = "Antonio Meloni"', content, flags=re.MULTILINE)
    else:
        # Add after version
        content = re.sub(r'^(version\s*=\s*".*"\n)', r'\1author = "Antonio Meloni"\n', content, flags=re.MULTILINE)
        
    # Update license
    if re.search(r'^license\s*=\s*".*"', content, flags=re.MULTILINE):
        content = re.sub(r'^license\s*=\s*".*"', 'license = "GPL-3.0"', content, flags=re.MULTILINE)
    else:
        # Add after author
        content = re.sub(r'^(author\s*=\s*".*"\n)', r'\1license = "GPL-3.0"\n', content, flags=re.MULTILINE)
        
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(content)
        
print("Tutti i manifest aggiornati con Autore = Antonio Meloni e Licenza = GPL-3.0")
