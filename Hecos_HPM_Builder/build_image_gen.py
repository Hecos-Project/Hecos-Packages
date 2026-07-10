import sys
import os
from pathlib import Path
from modules.builder import _build_single_package

src_dir = Path(r"C:\Hecos-Packages\image_gen_src")
pkgs_dir = Path(r"C:\Hecos-Packages")
_build_single_package(src_dir, pkgs_dir)
