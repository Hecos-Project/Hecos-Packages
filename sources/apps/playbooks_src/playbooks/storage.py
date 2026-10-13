import os
import uuid
import shutil
from typing import List, Dict, Any
from hecos.core.logging import logger

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

try:
    import tomli_w
    _HAS_TOMLI_W = True
except ImportError:
    _HAS_TOMLI_W = False

def get_playbooks_settings() -> dict:
    try:
        from hecos.core.constants import HECOS_DIR
        data_file = os.path.join(HECOS_DIR, "data", "playbooks_settings.json")
    except Exception:
        data_file = os.path.join(os.getcwd(), "hecos", "data", "playbooks_settings.json")
    
    defaults = {
        "single_mode": False,
        "master_enabled": True
    }
    if os.path.isfile(data_file):
        try:
            import json
            with open(data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults.update(data)
        except Exception as e:
            logger.warning(f"[Playbooks] Error reading settings: {e}")
    return defaults

def save_playbooks_settings(settings: dict) -> dict:
    try:
        from hecos.core.constants import HECOS_DIR
        data_dir = os.path.join(HECOS_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        data_file = os.path.join(data_dir, "playbooks_settings.json")
    except Exception:
        data_file = os.path.join(os.getcwd(), "hecos", "data", "playbooks_settings.json")
        os.makedirs(os.path.dirname(data_file), exist_ok=True)
        
    current = get_playbooks_settings()
    current.update(settings)
    try:
        import json
        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
    except Exception as e:
        logger.error(f"[Playbooks] Error saving settings: {e}")
    return current

def _set_pb_enabled_silent(playbook_id: str, enabled: bool):
    try:
        pdir, _ = _find_playbook_dir(playbook_id)
        if pdir:
            fpath = _get_pb_file(pdir)
            if os.path.isfile(fpath):
                data = _read_toml(fpath)
                if "meta" not in data: data["meta"] = {}
                data["meta"]["enabled"] = enabled
                _write_toml(fpath, data)
    except Exception as e:
        logger.error(f"[Playbooks] Error setting enabled for {playbook_id}: {e}")

def set_single_mode(enabled: bool, active_pid: str = None) -> dict:
    settings = save_playbooks_settings({"single_mode": enabled})
    if enabled:
        # Enforce single mode: ensure at most 1 is active
        playbooks = list_playbooks()
        active_pbs = [p for p in playbooks if p.get("meta", {}).get("enabled")]
        if len(active_pbs) > 1:
            keep_pid = active_pid or active_pbs[0].get("meta", {}).get("id")
            for p in active_pbs:
                pid = p.get("meta", {}).get("id")
                if pid and pid != keep_pid:
                    _set_pb_enabled_silent(pid, False)
    return settings

def toggle_all_playbooks(enabled: bool, active_pid: str = None) -> list[dict]:
    settings = get_playbooks_settings()
    single_mode = settings.get("single_mode", False)
    
    playbooks = list_playbooks()
    if not playbooks:
        return []
        
    if not enabled:
        for pb in playbooks:
            pid = pb.get("meta", {}).get("id")
            if pid:
                _set_pb_enabled_silent(pid, False)
    else:
        if single_mode:
            target_pid = active_pid or playbooks[0].get("meta", {}).get("id")
            for pb in playbooks:
                pid = pb.get("meta", {}).get("id")
                if pid:
                    _set_pb_enabled_silent(pid, (pid == target_pid))
        else:
            for pb in playbooks:
                pid = pb.get("meta", {}).get("id")
                if pid:
                    _set_pb_enabled_silent(pid, True)
                    
    return list_playbooks()

def _get_playbooks_dir() -> str:
    try:
        from hecos.core.constants import HECOS_DIR
        root_dir = os.path.normpath(os.path.join(HECOS_DIR, ".."))
        d = os.path.join(root_dir, "workspace", "playbooks")
    except Exception:
        d = os.path.join(os.getcwd(), "workspace", "playbooks")
    os.makedirs(d, exist_ok=True)
    return d

def _read_toml(path: str) -> dict:
    if not os.path.isfile(path) or tomllib is None:
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception as e:
        logger.error(f"[Playbooks] Error reading {path}: {e}")
        return {}

def _write_toml(path: str, data: dict) -> None:
    if not _HAS_TOMLI_W:
        logger.error(f"[Playbooks] tomli_w not installed, cannot write {path}")
        return
    try:
        with open(path, "wb") as f:
            tomli_w.dump(data, f)
    except Exception as e:
        logger.error(f"[Playbooks] Error writing {path}: {e}")

def _read_file(path: str) -> str:
    if not os.path.isfile(path): return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

def _write_file(path: str, content: str) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"[Playbooks] Error writing file {path}: {e}")

def _get_pb_file(pb_dir: str) -> str:
    for fname in ["playbook.toml", "manifest.toml", "hpkg_manifest.toml"]:
        p = os.path.join(pb_dir, fname)
        if os.path.isfile(p):
            return p
    return os.path.join(pb_dir, "playbook.toml")

def _get_hpm_playbooks_dir() -> str:
    try:
        from hecos.core.constants import HECOS_DIR
        return os.path.join(HECOS_DIR, "hpm", "playbooks")
    except Exception:
        return os.path.join(os.getcwd(), "hecos", "hpm", "playbooks")

def _find_playbook_dir(playbook_id: str):
    """Return (dir_path, source) for the given playbook id, or (None, None)."""
    # 1. Local workspace playbooks
    local_dir = os.path.join(_get_playbooks_dir(), playbook_id)
    if os.path.isdir(local_dir):
        return local_dir, "local"
    # 2. HPM playbooks directory
    hpm_dir = os.path.join(_get_hpm_playbooks_dir(), playbook_id)
    if os.path.isdir(hpm_dir):
        return hpm_dir, "hpm"
    # 3. Via HPM PackageRegistry
    try:
        from hecos.core.package_manager.registry import PackageRegistry
        from hecos.core.constants import HECOS_DIR
        reg = PackageRegistry(os.path.join(HECOS_DIR, "data"))
        pkg = reg.get(playbook_id)
        if pkg and pkg.get("install_path") and os.path.isdir(pkg["install_path"]):
            return pkg["install_path"], "hpm"
    except Exception:
        pass
    return None, None

def list_playbooks() -> list[dict]:
    res = []
    seen_ids = set()
    
    dirs_to_check = [
        (_get_playbooks_dir(), "local"),
        (_get_hpm_playbooks_dir(), "hpm")
    ]

    try:
        from hecos.core.package_manager.registry import PackageRegistry
        from hecos.core.constants import HECOS_DIR
        reg = PackageRegistry(os.path.join(HECOS_DIR, "data"))
        for pkg in reg.list_all():
            if pkg.get("type") == "playbook" or (pkg.get("manifest_snapshot") or {}).get("category") == "playbooks":
                ipath = pkg.get("install_path")
                if ipath and os.path.isdir(ipath):
                    parent_dir = os.path.dirname(ipath)
                    if (parent_dir, "hpm") not in dirs_to_check:
                        dirs_to_check.append((parent_dir, "hpm"))
    except Exception as e:
        logger.debug(f"[Playbooks] Registry scan: {e}")

    for base_dir, default_source in dirs_to_check:
        if not os.path.exists(base_dir):
            continue

        for item in os.listdir(base_dir):
            pb_dir = os.path.join(base_dir, item)
            if not os.path.isdir(pb_dir):
                continue

            file_path = _get_pb_file(pb_dir)
            if os.path.isfile(file_path):
                data = _read_toml(file_path)
                meta = data.get("meta", {})
                pid = meta.get("id") or item
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)

                meta["id"] = pid
                if "source" not in meta:
                    meta["source"] = default_source
                if "enabled" not in meta:
                    meta["enabled"] = True

                # Enrich with hpkg_manifest.toml if available and fields are missing
                hpkg_manifest_file = os.path.join(pb_dir, "hpkg_manifest.toml")
                if os.path.isfile(hpkg_manifest_file):
                    hpkg_data = _read_toml(hpkg_manifest_file)
                    if not meta.get("name") and hpkg_data.get("name"):
                        meta["name"] = hpkg_data["name"]
                    if not meta.get("description") and hpkg_data.get("description"):
                        meta["description"] = hpkg_data["description"]
                    if not meta.get("version") and hpkg_data.get("version"):
                        meta["version"] = hpkg_data["version"]
                    if not meta.get("author") and hpkg_data.get("author"):
                        meta["author"] = hpkg_data["author"]
                
                # Mode: training | roleplay | learning | freestyle
                if "mode" not in meta:
                    meta["mode"] = data.get("mode", "training")

                # Chat role block
                chat_role = data.get("chat_role", {})
                if not isinstance(chat_role, dict):
                    chat_role = {}
                chat_role.setdefault("enabled", False)
                chat_role.setdefault("brief", "")
                chat_role.setdefault("difficulty", "medium")

                tabs = data.get("tabs", [])
                for tab in tabs:
                    if "content" not in tab or not tab["content"]:
                        fname = tab.get("file")
                        if fname:
                            fpath = os.path.join(pb_dir, fname)
                            tab["content"] = _read_file(fpath)
                    if "content" not in tab:
                        tab["content"] = ""
                    # Default target to 'presenter' for backwards compatibility
                    if "target" not in tab or tab["target"] not in ["presenter", "chat", "both", "system"]:
                        tab["target"] = "presenter"
                
                res.append({
                    "meta": meta,
                    "mode": meta.get("mode", "training"),
                    "chat_role": chat_role,
                    "tabs": sorted(tabs, key=lambda x: x.get("order", 0))
                })
    return res

def get_playbook(playbook_id: str) -> dict:
    for pb in list_playbooks():
        if pb.get("meta", {}).get("id") == playbook_id:
            return pb
    return None

def create_playbook(name: str, description: str = "", icon: str = "fa-book-open", mode: str = "training") -> dict:
    import re
    slug = re.sub(r'[^a-zA-Z0-9_\-]+', '-', name.lower()).strip('-') or 'playbook'
    pid = f"{slug}-{str(uuid.uuid4())[:6]}"
    pb_dir = os.path.join(_get_playbooks_dir(), pid)
    os.makedirs(pb_dir, exist_ok=True)
    
    data = {
        "meta": {
            "id": pid,
            "name": name,
            "description": description,
            "icon": icon,
            "mode": mode,
            "enabled": True,
            "source": "local"
        },
        "chat_role": {
            "enabled": False,
            "brief": "",
            "difficulty": "medium"
        },
        "tabs": []
    }
    _write_toml(os.path.join(pb_dir, "playbook.toml"), data)
    return data

def update_playbook(playbook_id: str, **kwargs) -> dict:
    pb_dir, _ = _find_playbook_dir(playbook_id)
    if not pb_dir:
        raise ValueError(f"Playbook '{playbook_id}' not found")
        
    file_path = _get_pb_file(pb_dir)
    if not os.path.isfile(file_path):
        raise ValueError(f"Playbook config not found in '{pb_dir}'")
        
    # If enabling and single_mode is active, disable all others first
    if kwargs.get("enabled") is True:
        settings = get_playbooks_settings()
        if settings.get("single_mode", False):
            for other_pb in list_playbooks():
                other_id = other_pb.get("meta", {}).get("id")
                if other_id and other_id != playbook_id and other_pb.get("meta", {}).get("enabled"):
                    _set_pb_enabled_silent(other_id, False)

    data = _read_toml(file_path)
    if "meta" not in data: data["meta"] = {}
    if "chat_role" not in data or not isinstance(data["chat_role"], dict):
        data["chat_role"] = {}
    
    for k, v in kwargs.items():
        if k in ["name", "description", "icon", "enabled"]:
            data["meta"][k] = v
        elif k == "mode":
            data["meta"]["mode"] = v
            data["mode"] = v
        elif k == "chat_role" and isinstance(v, dict):
            data["chat_role"].update(v)
        elif k == "chat_role_brief":
            data["chat_role"]["brief"] = v
        elif k == "chat_role_enabled":
            data["chat_role"]["enabled"] = bool(v)
        elif k == "chat_role_difficulty":
            data["chat_role"]["difficulty"] = v
            
    _write_toml(file_path, data)
    return get_playbook(playbook_id)

def delete_playbook(playbook_id: str) -> bool:
    pb_dir, source = _find_playbook_dir(playbook_id)
    if pb_dir and os.path.isdir(pb_dir):
        if source == "hpm":
            raise ValueError("Cannot delete HPM-managed playbook directly. Please uninstall it via Package Manager.")
            
        shutil.rmtree(pb_dir)
        return True
    return False

def add_tab(playbook_id: str, name: str, content: str = "", target: str = "presenter") -> dict:
    pb_dir, _ = _find_playbook_dir(playbook_id)
    if not pb_dir:
        raise ValueError(f"Playbook '{playbook_id}' not found")
        
    file_path = _get_pb_file(pb_dir)
    if not os.path.isfile(file_path):
        raise ValueError(f"Playbook config not found in '{pb_dir}'")
        
    data = _read_toml(file_path)
    if "tabs" not in data: data["tabs"] = []
    
    tab_id = "tab-" + str(uuid.uuid4())[:8]
    fname = f"{tab_id}.txt"
    order = len(data["tabs"]) + 1
    
    clean_target = target if target in ["presenter", "chat", "both", "system"] else "presenter"

    tab_meta = {
        "id": tab_id,
        "name": name,
        "file": fname,
        "enabled": True,
        "order": order,
        "target": clean_target,
        "content": content
    }
    data["tabs"].append(tab_meta)
    
    _write_file(os.path.join(pb_dir, fname), content)
    _write_toml(file_path, data)
    
    return tab_meta

def update_tab(playbook_id: str, tab_id: str, **kwargs) -> dict:
    pb_dir, _ = _find_playbook_dir(playbook_id)
    if not pb_dir:
        raise ValueError(f"Playbook '{playbook_id}' not found")
        
    file_path = _get_pb_file(pb_dir)
    if not os.path.isfile(file_path):
        raise ValueError(f"Playbook config not found in '{pb_dir}'")
        
    data = _read_toml(file_path)
    tabs = data.get("tabs", [])
    
    target_tab = None
    for t in tabs:
        if t.get("id") == tab_id:
            target_tab = t
            break
            
    if not target_tab:
        raise ValueError(f"Tab '{tab_id}' not found")
        
    if "name" in kwargs:
        target_tab["name"] = kwargs["name"]
    if "enabled" in kwargs:
        target_tab["enabled"] = bool(kwargs["enabled"])
    if "order" in kwargs:
        target_tab["order"] = int(kwargs["order"])
    if "target" in kwargs:
        tgt = kwargs["target"]
        if tgt in ["presenter", "chat", "both", "system"]:
            target_tab["target"] = tgt
        
    if "content" in kwargs:
        target_tab["content"] = kwargs["content"]
        fname = target_tab.get("file") or f"{tab_id}.txt"
        target_tab["file"] = fname
        _write_file(os.path.join(pb_dir, fname), kwargs["content"])
            
    _write_toml(file_path, data)
    return target_tab

def delete_tab(playbook_id: str, tab_id: str) -> bool:
    pb_dir, _ = _find_playbook_dir(playbook_id)
    if not pb_dir: return False
    
    file_path = _get_pb_file(pb_dir)
    if not os.path.isfile(file_path): return False
    
    data = _read_toml(file_path)
    tabs = data.get("tabs", [])
    
    new_tabs = []
    for t in tabs:
        if t.get("id") == tab_id:
            fname = t.get("file")
            if fname:
                fpath = os.path.join(pb_dir, fname)
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
        else:
            new_tabs.append(t)
            
    data["tabs"] = new_tabs
    _write_toml(file_path, data)
    return True

def reorder_tabs(playbook_id: str, ordered_ids: List[str]) -> bool:
    pb_dir, _ = _find_playbook_dir(playbook_id)
    if not pb_dir: return False
    
    file_path = _get_pb_file(pb_dir)
    if not os.path.isfile(file_path): return False
    
    data = _read_toml(file_path)
    tabs = data.get("tabs", [])
    
    for t in tabs:
        tid = t.get("id")
        if tid in ordered_ids:
            t["order"] = ordered_ids.index(tid) + 1
            
    data["tabs"] = sorted(tabs, key=lambda x: x.get("order", 0))
    _write_toml(file_path, data)
    return True


def get_chat_playbook_context(max_tokens: int = 3500) -> str:
    """
    Restituisce il contesto destinato al modello CHAT (target='chat' o 'both'),
    includendo il brief di chat_role se presente ed abilitato.
    Prioritizza i tab con target='chat' (direttive ruolo) rispetto a target='both' (lore condiviso).
    """
    settings = get_playbooks_settings()
    if not settings.get("master_enabled", True):
        return ""
        
    single_mode = settings.get("single_mode", False)
    playbooks = list_playbooks()
    sections = []
    total_chars = 0
    max_chars = max_tokens * 4
    active_count = 0
    
    for pb in playbooks:
        meta = pb.get("meta", {})
        if not meta.get("enabled"): continue
        
        if single_mode and active_count >= 1:
            break
        active_count += 1
        
        pb_name = meta.get("name", "Active Playbook")
        chat_role = pb.get("chat_role", {})
        
        # 1. Role brief for the chat model (Highest priority)
        if chat_role.get("enabled") and chat_role.get("brief"):
            role_text = chat_role["brief"].strip()
            diff = chat_role.get("difficulty")
            diff_clause = f" (Difficulty: {diff})" if diff else ""
            role_sec = f"[PLAYBOOK CHAT ROLE: {pb_name}{diff_clause}]\n{role_text}\n"
            if total_chars + len(role_sec) <= max_chars:
                sections.append(role_sec)
                total_chars += len(role_sec)

        # 2. Tabs targeted to chat or both (Prioritize target='chat' before target='both')
        eligible_tabs = [
            t for t in pb.get("tabs", [])
            if t.get("enabled") and t.get("target") in ["chat", "both"]
        ]
        eligible_tabs.sort(key=lambda x: (0 if x.get("target") == "chat" else 1, x.get("order", 0)))

        for tab in eligible_tabs:
            content = tab.get("content", "").strip()
            if not content: continue
            
            section = f"[PLAYBOOK KNOWLEDGE: {pb_name} / {tab.get('name')}]\n{content}\n"
            if total_chars + len(section) > max_chars:
                diff_chars = max_chars - total_chars
                if diff_chars > 100:
                    sections.append(section[:diff_chars] + "... (TRUNCATED)")
                break
                
            sections.append(section)
            total_chars += len(section)
            
    return "\n".join(sections).strip()


def get_presenter_playbook_context(max_tokens: int = 3500) -> str:
    """
    Restituisce il contesto destinato al PRESENTER (target='presenter' o 'both').
    Prioritizza i tab con target='presenter' (direttive coach) rispetto a target='both' (lore condiviso).
    """
    settings = get_playbooks_settings()
    if not settings.get("master_enabled", True):
        return ""
        
    single_mode = settings.get("single_mode", False)
    playbooks = list_playbooks()
    sections = []
    total_chars = 0
    max_chars = max_tokens * 4
    active_count = 0
    
    for pb in playbooks:
        meta = pb.get("meta", {})
        if not meta.get("enabled"): continue
        
        if single_mode and active_count >= 1:
            break
        active_count += 1
        
        pb_name = meta.get("name", "Active Playbook")
        
        eligible_tabs = [
            t for t in pb.get("tabs", [])
            if t.get("enabled") and t.get("target", "presenter") in ["presenter", "both"]
        ]
        eligible_tabs.sort(key=lambda x: (0 if x.get("target") == "presenter" else 1, x.get("order", 0)))

        for tab in eligible_tabs:
            content = tab.get("content", "").strip()
            if not content: continue
            
            section = f"[PLAYBOOK: {pb_name} / {tab.get('name')}]\n{content}\n"
            if total_chars + len(section) > max_chars:
                diff_chars = max_chars - total_chars
                if diff_chars > 100:
                    sections.append(section[:diff_chars] + "... (TRUNCATED)")
                break
                
            sections.append(section)
            total_chars += len(section)
            
    return "\n".join(sections).strip()


# Backwards compatibility alias
get_active_playbook_context = get_presenter_playbook_context


def export_playbook(playbook_id: str) -> bytes:
    import zipfile
    import io
    
    pb_dir, _ = _find_playbook_dir(playbook_id)
    if not pb_dir or not os.path.isdir(pb_dir):
        raise ValueError("Playbook not found")
        
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(pb_dir):
            for file in files:
                fpath = os.path.join(root, file)
                arcname = os.path.relpath(fpath, pb_dir)
                zf.write(fpath, arcname)
    return buf.getvalue()

def import_playbook(zip_bytes: bytes) -> dict:
    import zipfile
    import io
    
    buf = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(buf, "r") as zf:
        has_toml = False
        for name in zf.namelist():
            if name == "playbook.toml" or name == "manifest.toml":
                has_toml = True
                break
        if not has_toml:
            raise ValueError("Invalid playbook zip: missing playbook.toml")
            
        pid = f"imported-{str(uuid.uuid4())[:6]}"
        pb_dir = os.path.join(_get_playbooks_dir(), pid)
        os.makedirs(pb_dir, exist_ok=True)
        zf.extractall(pb_dir)
        
        # update the id in meta
        file_path = _get_pb_file(pb_dir)
        data = _read_toml(file_path)
        if "meta" not in data:
            data["meta"] = {}
        data["meta"]["id"] = pid
        data["meta"]["source"] = "local"
        _write_toml(file_path, data)
        
        return get_playbook(pid)


def export_all_playbooks() -> bytes:
    import zipfile
    import io
    
    base_dir = _get_playbooks_dir()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(base_dir):
            for file in files:
                fpath = os.path.join(root, file)
                arcname = os.path.relpath(fpath, base_dir)
                zf.write(fpath, arcname)
    return buf.getvalue()

def import_all_playbooks(zip_bytes: bytes) -> bool:
    import zipfile
    import io
    
    base_dir = _get_playbooks_dir()
    buf = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(buf, "r") as zf:
        zf.extractall(base_dir)
    return True
