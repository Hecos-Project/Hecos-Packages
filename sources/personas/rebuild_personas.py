import sys
from pathlib import Path

# Add HPM Builder to path to import its modules
sys.path.insert(0, r"C:\Hecos-Packages\Hecos_HPM_Builder")

from modules.builder import _build_single_package
from modules.settings import get_packages_dir, get_src_dir

src_dir = get_src_dir()
packages_dir = get_packages_dir()

personas_src = src_dir / "personas"
for d in personas_src.iterdir():
    if d.is_dir() and d.name.endswith("_src"):
        print(f"Building {d.name}...")
        _build_single_package(d, packages_dir)

print("All done!")
