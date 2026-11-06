import os
import re
import random
from hecos.core.logging import logger


def list_images(plugin_dir: str, folder: str = "", limit: int = 10, sort: str = "recent", random_pick: bool = False) -> str:
    """
    Lists available images in media/images, media/generated_photos, or any specified folder.
    """
    root_dir = os.path.dirname(os.path.dirname(plugin_dir))
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

    folders_to_scan = []
    if folder:
        cand1 = os.path.join(root_dir, "media", folder)
        cand2 = os.path.join(root_dir, folder)
        if os.path.isdir(cand1):
            folders_to_scan.append(cand1)
        elif os.path.isdir(cand2):
            folders_to_scan.append(cand2)
        elif os.path.isdir(folder):
            folders_to_scan.append(folder)

    if not folders_to_scan:
        for fld_name in ["images", "generated_photos"]:
            p = os.path.join(root_dir, "media", fld_name)
            if os.path.isdir(p):
                folders_to_scan.append(p)

    candidates = []
    for fld in folders_to_scan:
        subname = os.path.basename(fld)
        try:
            for fname in os.listdir(fld):
                ext = os.path.splitext(fname)[1].lower()
                if ext in IMAGE_EXTS:
                    fp = os.path.join(fld, fname)
                    st = os.stat(fp)
                    txt_prompt = ""
                    txt_cand = os.path.splitext(fp)[0] + ".txt"
                    if os.path.exists(txt_cand):
                        try:
                            with open(txt_cand, "r", encoding="utf-8") as tf:
                                for line in tf:
                                    if line.lower().startswith("prompt:"):
                                        txt_prompt = line.split(":", 1)[1].strip()[:80]
                                        break
                        except Exception:
                            pass
                    candidates.append({
                        "filename": fname,
                        "path": fp,
                        "subfolder": subname,
                        "mtime": st.st_mtime,
                        "size": st.st_size,
                        "prompt": txt_prompt
                    })
        except Exception as e:
            logger.warning(f"[DOCS] Failed reading folder '{fld}': {e}")

    if not candidates:
        return "No images found in media/images or media/generated_photos."

    total_count = len(candidates)
    safe_limit = max(1, min(limit or 10, 50))

    if random_pick or str(sort).lower() == "random":
        selected = random.sample(candidates, min(safe_limit, len(candidates)))
    elif str(sort).lower() == "oldest":
        candidates.sort(key=lambda x: x["mtime"])
        selected = candidates[:safe_limit]
    elif str(sort).lower() == "name":
        candidates.sort(key=lambda x: x["filename"].lower())
        selected = candidates[:safe_limit]
    else:  # recent
        candidates.sort(key=lambda x: x["mtime"], reverse=True)
        selected = candidates[:safe_limit]

    lines = [f"Found {total_count} existing image(s). Showing {len(selected)} (sort={sort}):"]
    for i, item in enumerate(selected, 1):
        size_kb = f"{item['size'] / 1024:.1f} KB"
        prompt_str = f' — Prompt: "{item["prompt"]}..."' if item["prompt"] else ""
        lines.append(f"  {i}. /api/images/{item['filename']} ({size_kb}){prompt_str}")

    lines.append("\nTo use these in a document, pass /api/images/FILENAME in template_vars (img1, img2...) or in <img> tags.")
    return "\n".join(lines)


def list_documents(output_dir: str, search: str = "") -> str:
    """
    Lists all documents in the output directory. Optionally filters by name.
    """
    try:
        files = []
        if not os.path.isdir(output_dir):
            return f"No documents folder found at `{output_dir}`."
        
        for f in sorted(os.listdir(output_dir)):
            full_path = os.path.join(output_dir, f)
            if not os.path.isfile(full_path):
                continue
            if search and search.lower() not in f.lower():
                continue
            
            size_bytes = os.path.getsize(full_path)
            size_str = f"{size_bytes / 1024:.1f} KB" if size_bytes > 1024 else f"{size_bytes} bytes"
            
            preview = ""
            if f.endswith(".html"):
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                    
                    title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
                    title = title_match.group(1) if title_match else ""
                    img_count = len(re.findall(r'<img\s', content, re.IGNORECASE))
                    
                    text = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(r'<[^>]+>', ' ', text)
                    text = re.sub(r'\s+', ' ', text).strip()[:200]
                    
                    preview_parts = []
                    if title:
                        preview_parts.append(f"Title: {title}")
                    preview_parts.append(f"Images: {img_count}")
                    preview_parts.append(f"Preview: {text}...")
                    preview = " | ".join(preview_parts)
                except Exception:
                    preview = "(unable to read preview)"
            
            url_path = full_path.replace("\\", "/")
            files.append(f"📄 **[{f}](file:///{url_path})** ({size_str})\n   {preview}" if preview else f"📄 **[{f}](file:///{url_path})** ({size_str})")
        
        if not files:
            return f"No documents found in {output_dir}" + (f" matching '{search}'" if search else "") + "."
        
        header = f"📁 Documents in `{output_dir}`"
        if search:
            header += f" (filter: '{search}')"
        return f"{header}\n\n" + "\n\n".join(files)
        
    except Exception as e:
        logger.error(f"[DOCS] Failed to list documents: {e}")
        return f"Error listing documents: {e}"
