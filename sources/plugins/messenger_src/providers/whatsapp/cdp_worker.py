"""
Isolated Playwright/CDP subprocess worker for WhatsApp Web.
Communicates via JSON files (never stdout pipes) and launches any dedicated
browser process with detached descriptors so child Chrome processes on Windows
can NEVER inherit pipes or deadlock the parent Hecos worker thread.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("hecos-wa-worker")
    except Exception:
        pass

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import dom_driver  # type: ignore[import-not-found]


def _is_port_open(port: int, timeout: float = 0.25) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _find_browser_executable() -> str:
    local_app = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(local_app, r"Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return ""


def _resolve_profile_dir() -> str:
    p = Path(_THIS_DIR)
    for parent in p.parents:
        if parent.name == "hecos" and (parent / "data").exists():
            target = parent / "data" / "whatsapp_session"
            target.mkdir(parents=True, exist_ok=True)
            return str(target)
    fallback = p / "whatsapp_session"
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback)


def _kill_browser_on_port(port: int) -> None:
    """Terminates any dedicated Chromium/Chrome process bound to `--remote-debugging-port=<port>`."""
    if sys.platform == "win32":
        try:
            ps_cmd = (
                f"Get-CimInstance Win32_Process | "
                f"Where-Object {{ $_.Name -match 'chrome|msedge' -and $_.CommandLine -match '--remote-debugging-port={port}(\\b|$)' }} | "
                f"ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                close_fds=True,
            )
        except Exception:
            pass
    deadline = time.time() + 4.0
    while time.time() < deadline and _is_port_open(port):
        time.sleep(0.2)


def _spawn_detached_browser(exe: str, port: int, profile_dir: str, headless: bool = False) -> tuple[bool, str]:
    cmd = [
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
    ]
    if headless:
        cmd.extend(["--headless=new", "--window-size=1280,900"])
    cmd.append("https://web.whatsapp.com")

    # DETACHED_PROCESS (0x08) | CREATE_NEW_PROCESS_GROUP (0x200) | CREATE_BREAKAWAY_FROM_JOB (0x01000000)
    win_flags = 0x00000008 | 0x00000200
    try:
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=(win_flags if sys.platform == "win32" else 0),
            close_fds=True,
        )
    except Exception as exc:
        return False, f"Failed to spawn browser session: {exc}"

    deadline = time.time() + 12.0
    while time.time() < deadline:
        if _is_port_open(port):
            time.sleep(0.5)
            return True, ""
        time.sleep(0.25)

    return False, f"Browser launched, but debug port {port} did not open within 12s."


def _ensure_dedicated_browser_running(
    port: int,
    headless: bool = False,
    force_visible: bool = False,
) -> tuple[bool, str]:
    """
    Starts the dedicated Hecos session if not already listening on `port`.
    If `force_visible` is True and a headless instance is currently holding `port`,
    restarts it in visible mode so the user can see the window / scan the QR code.
    """
    exe = _find_browser_executable()
    if not exe:
        return False, (
            "Neither Google Chrome nor Microsoft Edge was found in standard paths "
            "to launch the Dedicated Hecos Session."
        )

    profile_dir = _resolve_profile_dir()

    if _is_port_open(port):
        if force_visible:
            # Check if the running instance was launched with --headless
            try:
                if sys.platform == "win32":
                    out = subprocess.check_output(
                        [
                            "powershell",
                            "-NoProfile",
                            "-Command",
                            f"Get-CimInstance Win32_Process | Where-Object {{ $_.Name -match 'chrome|msedge' -and $_.CommandLine -match '--remote-debugging-port={port}(\\b|$)' }} | Select-Object -ExpandProperty CommandLine",
                        ],
                        stdin=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        timeout=4,
                        close_fds=True,
                    )
                    if "--headless" in (out or ""):
                        _kill_browser_on_port(port)
                    else:
                        return True, ""
                else:
                    return True, ""
            except Exception:
                return True, ""
        else:
            return True, ""

    return _spawn_detached_browser(exe, port, profile_dir, headless=(False if force_visible else headless))


def _acquire_whatsapp_page(
    browser: Any,
    auto_open_tab: bool = True,
    bring_front: bool = True,
) -> tuple[Optional[Any], str]:
    for ctx in browser.contexts:
        for pg in ctx.pages:
            try:
                if "web.whatsapp.com" in (pg.url or ""):
                    if bring_front:
                        try:
                            pg.bring_to_front()
                        except Exception:
                            pass
                    return pg, ""
            except Exception:
                continue

    if not auto_open_tab:
        return None, (
            "No open WhatsApp Web tab found in the browser, and 'Auto-open tab' is disabled "
            "in Messenger settings. Open https://web.whatsapp.com or enable Auto-open tab."
        )

    try:
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        pg = ctx.new_page()
        pg.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=30000)
        if bring_front:
            try:
                pg.bring_to_front()
            except Exception:
                pass
        return pg, ""
    except Exception as exc:
        return None, f"Failed to open a new WhatsApp Web tab automatically: {exc}"


def run_task(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "send_text")
    session_mode = payload.get("session_mode", "cdp")
    base_cdp_port = int(payload.get("cdp_port", 9222) or 9222)
    auto_open_tab = bool(payload.get("auto_open_tab", True))
    persistent_headless = bool(payload.get("persistent_headless", False))
    cdp_timeout = int(payload.get("cdp_timeout", 30) or 30)

    is_dedicated = session_mode == "persistent_profile"
    target_port = (base_cdp_port + 1) if is_dedicated else base_cdp_port
    method_label = (
        f"Dedicated Hecos Session (isolated profile, port {target_port})"
        if is_dedicated
        else f"Shared User Browser (CDP port {target_port})"
    )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return {"ok": False, "error": f"Playwright is not installed: {exc}", "method_used": method_label}

    if is_dedicated:
        if action == "status" and not _is_port_open(target_port):
            return {
                "ok": True,
                "state": "READY",
                "tab_open": False,
                "logged_in": None,
                "port": target_port,
                "profile_dir": _resolve_profile_dir(),
                "method_used": method_label,
                "summary": "Dedicated session is idle (click 'Open / Link WhatsApp Web' to scan QR or test).",
            }
        started, err_msg = _ensure_dedicated_browser_running(
            target_port,
            headless=persistent_headless,
            force_visible=(action == "open_session"),
        )
        if not started:
            return {"ok": False, "error": err_msg, "method_used": method_label}
    else:
        if not _is_port_open(target_port):
            if action == "open_session":
                exe = _find_browser_executable()
                if exe:
                    profile_tmp = os.path.join(os.environ.get("TEMP", "."), "hecos_browser_profile")
                    os.makedirs(profile_tmp, exist_ok=True)
                    _spawn_detached_browser(exe, target_port, profile_tmp, headless=False)
            if not _is_port_open(target_port):
                return {
                    "ok": False,
                    "state": "OFFLINE",
                    "port": target_port,
                    "method_used": method_label,
                    "error": (
                        f"Chrome CDP port {target_port} is not reachable. "
                        f"Launch Chrome with --remote-debugging-port={target_port}, "
                        "or switch WhatsApp Delivery Method to 'Dedicated Hecos Session' in Messenger settings."
                    ),
                }

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(
                f"http://127.0.0.1:{target_port}",
                timeout=max(5, cdp_timeout) * 1000,
            )

            if action == "status":
                wa_page, _ = _acquire_whatsapp_page(browser, auto_open_tab=False, bring_front=False)
                if wa_page is None:
                    return {
                        "ok": True,
                        "state": "READY" if auto_open_tab else "DEGRADED",
                        "tab_open": False,
                        "logged_in": None,
                        "port": target_port,
                        "method_used": method_label,
                        "summary": (
                            f"Connected on port {target_port} (WhatsApp Web tab will open automatically on send)."
                            if auto_open_tab
                            else f"Connected on port {target_port}, but no WhatsApp Web tab is open."
                        ),
                    }
                qr_vis = dom_driver.is_qr_login_visible(wa_page, timeout_ms=800)
                return {
                    "ok": True,
                    "state": "DEGRADED" if qr_vis else "ONLINE",
                    "tab_open": True,
                    "logged_in": not qr_vis,
                    "port": target_port,
                    "method_used": method_label,
                    "summary": (
                        "WhatsApp Web requires QR scan — click 'Open / Link WhatsApp Web'!"
                        if qr_vis
                        else f"WhatsApp Web active and logged in on port {target_port}."
                    ),
                }

            if action == "open_session":
                wa_page, err = _acquire_whatsapp_page(browser, auto_open_tab=True, bring_front=True)
                if err or wa_page is None:
                    return {"ok": False, "error": err or "Could not open WhatsApp Web tab.", "method_used": method_label}
                qr_vis = dom_driver.is_qr_login_visible(wa_page, timeout_ms=2000)
                return {
                    "ok": True,
                    "logged_in": not qr_vis,
                    "method_used": method_label,
                    "message": (
                        "WhatsApp Web window opened — please scan the QR code with your phone to link the session."
                        if qr_vis
                        else "WhatsApp Web session is open and logged in!"
                    ),
                }

            if action == "scan_groups":
                wa_page, err = _acquire_whatsapp_page(browser, auto_open_tab=auto_open_tab, bring_front=False)
                if err or wa_page is None:
                    return {"ok": False, "error": err or "WhatsApp Web page unavailable.", "method_used": method_label, "groups": []}
                res = dom_driver.scan_groups_on_page(wa_page)
                res["method_used"] = method_label
                return res

            if action == "poll_groups":
                wa_page, _ = _acquire_whatsapp_page(browser, auto_open_tab=False, bring_front=False)
                if wa_page is None or dom_driver.is_qr_login_visible(wa_page, timeout_ms=400):
                    return {"ok": False, "error": "WhatsApp Web tab not ready or awaiting QR scan.", "groups_data": {}}
                group_titles = payload.get("group_titles") or []
                groups_data: dict[str, Any] = {}
                for gtitle in group_titles:
                    if not gtitle:
                        continue
                    groups_data[gtitle] = dom_driver.read_recent_group_messages(wa_page, str(gtitle), max_messages=10)
                return {"ok": True, "groups_data": groups_data, "method_used": method_label}

            # Outbound send_text or send_media
            bring_front = not (is_dedicated and persistent_headless)
            wa_page, err = _acquire_whatsapp_page(browser, auto_open_tab=auto_open_tab, bring_front=bring_front)
            if err or wa_page is None:
                return {"ok": False, "error": err or "WhatsApp Web page unavailable.", "method_used": method_label}

            # Auto-recovery if user enabled Headless on a Dedicated Profile BEFORE scanning QR!
            if is_dedicated and persistent_headless and dom_driver.is_qr_login_visible(wa_page, timeout_ms=2500):
                try:
                    browser.close()
                except Exception:
                    pass
                _kill_browser_on_port(target_port)
                _ensure_dedicated_browser_running(target_port, headless=False, force_visible=True)
                return {
                    "ok": False,
                    "method_used": method_label,
                    "error": (
                        "Dedicated Hecos WhatsApp session is not linked yet (QR code login required). "
                        "Hecos has now opened the visible WhatsApp Web window on your screen — "
                        "scan the QR code once from your phone, then send again!"
                    ),
                }

            e164 = payload.get("e164", "")
            digits = payload.get("digits", "")
            contact_name = payload.get("contact_name")
            group_title = payload.get("group_title")

            if action == "send_media":
                res = dom_driver.send_files_on_page(
                    wa_page,
                    digits=digits,
                    e164=e164,
                    file_paths=payload.get("file_paths") or [],
                    caption=payload.get("caption") or "",
                    contact_name=contact_name,
                    nav_timeout_sec=cdp_timeout,
                    group_title=group_title,
                )
            else:
                res = dom_driver.send_text_on_page(
                    wa_page,
                    digits=digits,
                    e164=e164,
                    text=payload.get("text") or "",
                    single_block=bool(payload.get("single_block", True)),
                    contact_name=contact_name,
                    nav_timeout_sec=cdp_timeout,
                    group_title=group_title,
                )

            # Second check: if open_chat_for_recipient failed due to QR code while headless, pop open visible window!
            if (
                not res.get("ok")
                and is_dedicated
                and persistent_headless
                and "qr code" in str(res.get("error", "")).lower()
            ):
                try:
                    browser.close()
                except Exception:
                    pass
                _kill_browser_on_port(target_port)
                _ensure_dedicated_browser_running(target_port, headless=False, force_visible=True)
                res["error"] = (
                    "Dedicated Hecos WhatsApp session is not linked yet (QR code login required). "
                    "Hecos has now opened the visible WhatsApp Web window on your screen — "
                    "scan the QR code once from your phone, then send again!"
                )

            res["method_used"] = method_label
            return res

    except Exception as exc:
        return {"ok": False, "error": f"Playwright CDP worker error: {exc}", "method_used": method_label}


def main() -> None:
    # File-based IPC mode: cdp_worker.py <input_json_path> <output_json_path>
    if len(sys.argv) >= 3:
        in_path, out_path = sys.argv[1], sys.argv[2]
        try:
            with open(in_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception as exc:
            result = {"ok": False, "error": f"Failed reading worker input file: {exc}"}
        else:
            result = run_task(payload)
        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(result, fh, ensure_ascii=False)
        except Exception:
            pass
        return

    # Fallback stdin/stdout mode for manual CLI debugging
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        print(json.dumps({"ok": False, "error": "Empty worker payload received."}))
        return
    try:
        payload = json.loads(raw)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Invalid JSON payload: {exc}"}))
        return
    print(json.dumps(run_task(payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
