"""
search/components/pip_component.py
Component wrapper for pip-installed packages with Hecos progress reporting.
"""
from __future__ import annotations

import sys
import os
import subprocess
import importlib.util
import logging
from typing import Tuple, Dict, Any, Optional, Callable, List

from .base import BaseComponent

logger = logging.getLogger("browser.search.pip_component")

try:
    from hecos.core.logging import logger as hecos_logger
except (ImportError, ValueError):
    hecos_logger = logger


def _resolve_python_exe() -> str:
    # Prefer Hecos dedicated virtualenv if it exists
    hecos_py = r"C:\Hecos\python_env\python.exe"
    if os.path.isfile(hecos_py):
        return hecos_py
    return sys.executable


class PipComponent(BaseComponent):
    """Manages installation of Python packages via pip."""

    def __init__(
        self,
        component_id: str,
        name: str,
        description: str,
        import_name: str,
        pip_package: str,
        category: str = "core",
        extra_imports: Optional[List[str]] = None
    ):
        super().__init__(component_id, name, description, category=category, auto_start=False)
        self.import_name = import_name
        self.pip_package = pip_package
        self.extra_imports = extra_imports or []

    def is_installed(self) -> bool:
        try:
            if not importlib.util.find_spec(self.import_name):
                return False
            for extra in self.extra_imports:
                if not importlib.util.find_spec(extra):
                    return False
            return True
        except Exception:
            return False

    def is_running(self) -> bool:
        return self.is_installed()

    def install(self, progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None) -> Tuple[bool, str]:
        py_exe = _resolve_python_exe()
        hecos_logger.info(f"[PIP] Installing {self.pip_package} using {py_exe}...")

        if progress_cb:
            progress_cb({"step": "start", "message": f"Installing {self.name} ({self.pip_package})..."})

        task_id = f"search_comp_{self.id}"
        try:
            # Use Hecos unified progress coordinator
            from hecos.core.progress import progress
            from hecos.core.progress.adapters.pip import run_pip, PIP_PHASES

            with progress.task(
                task_id,
                title=f"Pip: {self.name}",
                source="HSEARCH",
                phases=PIP_PHASES,
                cancellable=True
            ) as ptask:
                ret, out = run_pip(
                    ["install", "--upgrade", self.pip_package],
                    task=ptask,
                    python_exe=py_exe,
                    on_progress=progress_cb
                )
                if ret == 0 and self.is_installed():
                    ptask.done(f"{self.name} installed successfully.")
                    if progress_cb:
                        progress_cb({"step": "done", "percent": 100.0, "message": f"{self.name} successfully installed."})
                    return True, f"Successfully installed {self.pip_package}"
                else:
                    err_msg = f"Installation returned exit code {ret}: {out[-300:]}"
                    ptask.fail(err_msg)
                    if progress_cb:
                        progress_cb({"step": "error", "message": err_msg})
                    return False, err_msg
        except Exception as e:
            hecos_logger.error(f"[PIP] Failed to install {self.pip_package}: {e}")
            if progress_cb:
                progress_cb({"step": "error", "message": str(e)})
            return False, str(e)

    def uninstall(self) -> Tuple[bool, str]:
        py_exe = _resolve_python_exe()
        hecos_logger.info(f"[PIP] Uninstalling {self.pip_package}...")
        pkg_name = self.pip_package.split("==")[0].split(">=")[0].strip()
        task_id = f"search_comp_un_{self.id}"
        try:
            from hecos.core.progress import progress
            from hecos.core.progress.adapters.pip import run_pip
            with progress.task(task_id, title=f"Uninstall: {self.name}", source="HSEARCH", cancellable=True) as ptask:
                ret, out = run_pip(
                    ["uninstall", "-y", pkg_name],
                    task=ptask,
                    python_exe=py_exe
                )
                if ret == 0:
                    ptask.done(f"Uninstalled {pkg_name}")
                    return True, f"Uninstalled {pkg_name}"
                ptask.fail("Uninstall failed")
                return False, "Uninstall failed"
        except Exception as e:
            return False, str(e)
