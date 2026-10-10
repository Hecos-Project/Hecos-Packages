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
    p1 = os.path.join(pb_dir, "playbook.toml")
    if os.path.isfile(p1):
        return p1
    p2 = os.path.join(pb_dir, "manifest.toml")
    if os.path.isfile(p2):
        return p2
    return p1

def list_playbooks() -> List[dict]:
    res = []
    base_dir = _get_playbooks_dir()
    if not os.path.exists(base_dir):
        return res

    for item in os.listdir(base_dir):
        pb_dir = os.path.join(base_dir, item)
        if os.path.isdir(pb_dir):
            file_path = _get_pb_file(pb_dir)
            if os.path.isfile(file_path):
                data = _read_toml(file_path)
                meta = data.get("meta", {})
                if not meta.get("id"):
                    meta["id"] = item
                
                # Fetch tabs content
                tabs = data.get("tabs", [])
                for tab in tabs:
                    # Tab content can be in TOML directly or in external file
                    if "content" not in tab or not tab["content"]:
                        fname = tab.get("file")
                        if fname:
                            fpath = os.path.join(pb_dir, fname)
                            tab["content"] = _read_file(fpath)
                    if "content" not in tab:
                        tab["content"] = ""
                
                res.append({
                    "meta": meta,
                    "tabs": sorted(tabs, key=lambda x: x.get("order", 0))
                })
    return res

def get_playbook(playbook_id: str) -> dict:
    for pb in list_playbooks():
        if pb.get("meta", {}).get("id") == playbook_id:
            return pb
    return None

def create_playbook(name: str, description: str = "", icon: str = "fa-book-open") -> dict:
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
            "enabled": True,
            "source": "local"
        },
        "tabs": []
    }
    _write_toml(os.path.join(pb_dir, "playbook.toml"), data)
    return data

def update_playbook(playbook_id: str, **kwargs) -> dict:
    pb_dir = os.path.join(_get_playbooks_dir(), playbook_id)
    file_path = _get_pb_file(pb_dir)
    
    if not os.path.isfile(file_path):
        raise ValueError(f"Playbook '{playbook_id}' not found")
        
    data = _read_toml(file_path)
    if "meta" not in data: data["meta"] = {}
    
    for k, v in kwargs.items():
        if k in ["name", "description", "icon", "enabled"]:
            data["meta"][k] = v
            
    _write_toml(file_path, data)
    return get_playbook(playbook_id)

def delete_playbook(playbook_id: str) -> bool:
    pb_dir = os.path.join(_get_playbooks_dir(), playbook_id)
    if os.path.isdir(pb_dir):
        file_path = _get_pb_file(pb_dir)
        data = _read_toml(file_path)
        if data.get("meta", {}).get("source") == "hpm":
            raise ValueError("Cannot delete HPM-managed playbook directly.")
            
        shutil.rmtree(pb_dir)
        return True
    return False

def add_tab(playbook_id: str, name: str, content: str = "") -> dict:
    pb_dir = os.path.join(_get_playbooks_dir(), playbook_id)
    file_path = _get_pb_file(pb_dir)
    if not os.path.isfile(file_path):
        raise ValueError(f"Playbook '{playbook_id}' not found")
        
    data = _read_toml(file_path)
    if "tabs" not in data: data["tabs"] = []
    
    tab_id = "tab-" + str(uuid.uuid4())[:8]
    fname = f"{tab_id}.txt"
    order = len(data["tabs"]) + 1
    
    tab_meta = {
        "id": tab_id,
        "name": name,
        "file": fname,
        "enabled": True,
        "order": order,
        "content": content
    }
    data["tabs"].append(tab_meta)
    
    _write_file(os.path.join(pb_dir, fname), content)
    _write_toml(file_path, data)
    
    return tab_meta

def update_tab(playbook_id: str, tab_id: str, **kwargs) -> dict:
    pb_dir = os.path.join(_get_playbooks_dir(), playbook_id)
    file_path = _get_pb_file(pb_dir)
    if not os.path.isfile(file_path):
        raise ValueError(f"Playbook '{playbook_id}' not found")
        
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
        
    if "content" in kwargs:
        target_tab["content"] = kwargs["content"]
        fname = target_tab.get("file") or f"{tab_id}.txt"
        target_tab["file"] = fname
        _write_file(os.path.join(pb_dir, fname), kwargs["content"])
            
    _write_toml(file_path, data)
    return target_tab

def delete_tab(playbook_id: str, tab_id: str) -> bool:
    pb_dir = os.path.join(_get_playbooks_dir(), playbook_id)
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
    pb_dir = os.path.join(_get_playbooks_dir(), playbook_id)
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

def get_active_playbook_context(max_tokens: int = 2000) -> str:
    sections = []
    total_chars = 0
    max_chars = max_tokens * 4
    
    playbooks = list_playbooks()
    for pb in playbooks:
        meta = pb.get("meta", {})
        if not meta.get("enabled"): continue
        
        for tab in pb.get("tabs", []):
            if not tab.get("enabled"): continue
            
            content = tab.get("content", "").strip()
            if not content: continue
            
            section = f"[PLAYBOOK: {meta.get('name')} / {tab.get('name')}]\n{content}\n"
            
            if total_chars + len(section) > max_chars:
                diff = max_chars - total_chars
                if diff > 100:
                    sections.append(section[:diff] + "... (TRUNCATED)")
                break
                
            sections.append(section)
            total_chars += len(section)
            
    return "\n".join(sections)
