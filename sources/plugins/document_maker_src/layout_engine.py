import os
import re
import json
from hecos.core.logging import logger


def get_save_dir(plugin_dir: str, config_file: str) -> str:
    """Returns the absolute directory where documents should be saved."""
    default_path = "media/documents"
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                default_path = data.get("pdf_save_path", default_path)
        except Exception as e:
            logger.error(f"[DOCS] Failed to read config: {e}")
    
    root_dir = os.path.dirname(os.path.dirname(plugin_dir))
    full_path = os.path.join(root_dir, os.path.normpath(default_path))
    os.makedirs(full_path, exist_ok=True)
    return full_path


def get_layout_config(config_file: str) -> dict:
    """Returns page margins, format, and layout optimization settings."""
    default_config = {
        "page_format": "A4",
        "ai_optimization": "hybrid",
        "margin_top": 20,
        "margin_bottom": 20,
        "margin_left": 20,
        "margin_right": 20
    }
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                default_config.update({k: data[k] for k in default_config.keys() if k in data})
        except Exception as e:
            logger.error(f"[DOCS] Failed to read config: {e}")
    return default_config


def resolve_image_paths(plugin_dir: str, html_content: str) -> str:
    """Resolves local image paths to file:/// URLs for Playwright rendering."""
    root_dir = os.path.dirname(os.path.dirname(plugin_dir))
    media_images_dir = os.path.join(root_dir, "media", "images")
    generated_photos_dir = os.path.join(root_dir, "media", "generated_photos")
    
    # 1. Collect all available generated image files sorted by mtime (oldest to newest)
    gen_files = []
    for fld in [media_images_dir, generated_photos_dir]:
        if os.path.isdir(fld):
            for f in os.listdir(fld):
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    gen_files.append(os.path.join(fld, f))
    gen_files.sort(key=lambda p: os.path.getmtime(p))

    # 2. Extract referenced alias indices strictly from image paths (e.g. image_1, img2.png, foto-3)
    alias_indices = []
    for match_num in re.findall(r'(?:img|image|foto|photo)[_-]?(\d+)(?:\.[a-zA-Z0-9]+)?', html_content, re.IGNORECASE):
        if match_num and match_num.isdigit():
            alias_indices.append(int(match_num))

    # Safe batch sizing: count of aliases or max index (bounded by available files)
    batch_count = max(alias_indices) if alias_indices else 6
    batch_count = max(batch_count, len(alias_indices), 1)
    batch = gen_files[-batch_count:] if gen_files else []

    unresolved_counter = [0]

    def resolve_img_path(match):
        path = match.group(2).strip()
        logger.debug(f"[DOCS] Regex intercepted image path: '{path}'")
        
        # Ignore remote and data URIs
        if path.startswith(("http://", "https://", "data:")):
            logger.debug(f"[DOCS] Skipping remote/data URI: '{path}'")
            return match.group(0)

        # If already file:///, verify target exists
        if path.startswith("file:///"):
            local_f = path.replace("file:///", "").replace("/", os.sep)
            if os.path.exists(local_f):
                return match.group(0)
            path = os.path.basename(local_f)

        abs_path = None
        clean_path = path.lstrip("/\\")

        # 1. Absolute Windows path (C:\... or C:/...)
        if os.path.isabs(clean_path) and (clean_path[1:3] in (":\\", ":/")):
            if os.path.exists(clean_path):
                abs_path = clean_path
            else:
                clean_path = os.path.basename(clean_path)

        # 2. Direct path relative to hecos root
        if not abs_path:
            cand = os.path.join(root_dir, clean_path)
            if os.path.exists(cand):
                abs_path = cand

        # 3. Direct filename check in media/images, media/generated_photos, and any media subdir
        if not abs_path:
            filename = os.path.basename(clean_path)
            cand = os.path.join(media_images_dir, filename)
            if os.path.exists(cand):
                abs_path = cand
            if not abs_path:
                cand = os.path.join(generated_photos_dir, filename)
                if os.path.exists(cand):
                    abs_path = cand
            if not abs_path:
                media_dir = os.path.dirname(media_images_dir)
                if os.path.isdir(media_dir):
                    for subdir in os.listdir(media_dir):
                        cand = os.path.join(media_dir, subdir, filename)
                        if os.path.exists(cand):
                            abs_path = cand
                            break

        # 4. Check with common extensions if filename lacks one
        if not abs_path or not os.path.exists(abs_path):
            filename = os.path.basename(clean_path)
            for ext in [".png", ".jpg", ".jpeg", ".webp"]:
                cand = os.path.join(media_images_dir, filename + ext)
                if os.path.exists(cand):
                    abs_path = cand
                    break

        # 5. Generic alias matching: image_1, image_1.png, img2, photo3.jpg, foto_4, etc.
        if not abs_path or not os.path.exists(abs_path):
            filename = os.path.basename(clean_path)
            m_idx = re.search(r'(?:img|image|foto|photo)?[_-]?(\d+)(?:\.[a-zA-Z0-9]+)?$', filename, re.IGNORECASE)
            if m_idx and batch:
                idx = int(m_idx.group(1))
                if 1 <= idx <= len(batch):
                    abs_path = batch[idx - 1]
                else:
                    abs_path = batch[(idx - 1) % len(batch)]
                logger.info(f"[DOCS] Generic image alias '{path}' mapped to '{abs_path}'")

        # 6. Safety fallback: Map to latest generated batch
        if not abs_path or not os.path.exists(abs_path):
            if batch:
                idx = unresolved_counter[0] % len(batch)
                unresolved_counter[0] += 1
                abs_path = batch[idx]
                logger.warning(f"[DOCS] Unresolved image '{path}' safely mapped to batch image '{abs_path}'")
            elif gen_files:
                abs_path = gen_files[-1]
                logger.warning(f"[DOCS] Unresolved image '{path}' safely mapped to latest image '{abs_path}'")

        if abs_path and os.path.exists(abs_path):
            file_url = "file:///" + os.path.normpath(abs_path).replace("\\", "/")
            logger.debug(f"[DOCS] Final mapped URL for Playwright: '{file_url}'")
            return f'{match.group(1)}{file_url}{match.group(3)}'
        
        logger.warning(f"[DOCS] Could not resolve image path: '{path}'")
        return match.group(0)

    # Match <img src="filename.png"> or <img src='filename.png'>
    img_pattern = r'(<img[^>]+src=["\'])(.*?)(["\'][^>]*>)'
    html_content = re.sub(img_pattern, resolve_img_path, html_content)

    # Match background-image: url('filename.png')
    bg_pattern = r"(url\(['\"]?)(.*?)(['\"]?\))"
    html_content = re.sub(bg_pattern, resolve_img_path, html_content)

    return html_content


def detect_background_color(html: str) -> str:
    """
    Detects the document background color from CSS variables,
    body rules, inline styles, or @media print rules.
    Falls back to '#ffffff' if light or not found.
    """
    def _clean_color(val: str) -> str:
        if not val:
            return ""
        val = val.strip().rstrip(";")
        val = re.sub(r'\s*!important', '', val, flags=re.I).strip()
        if 'gradient' in val.lower():
            color_matches = re.findall(r'#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})|rgba?\([^)]+\)|hsla?\([^)]+\)', val)
            if color_matches:
                return color_matches[-1]
            return ""
        if val.lower() in ("transparent", "none", "inherit", "initial", "unset"):
            return ""
        return val

    def _resolve_var(var_str: str) -> str:
        m = re.search(r'var\(\s*(--[a-zA-Z0-9_-]+)(?:\s*,\s*([^)]+))?\)', var_str)
        if not m:
            return _clean_color(var_str)
        var_name = m.group(1)
        fallback = m.group(2)
        def_match = re.search(rf'{re.escape(var_name)}\s*:\s*([^;!}}]+)', html)
        if def_match:
            resolved = _clean_color(def_match.group(1))
            if resolved:
                return resolved
        if fallback:
            return _clean_color(fallback)
        return ""

    # 1. Search for @media print body background
    m_print = re.search(r'@media\s+print\s*\{[^}]*body\s*\{[^}]*background(?:-color)?\s*:\s*([^;!]+)', html, re.I)
    if m_print:
        val = _resolve_var(m_print.group(1))
        if val:
            return val

    # 2. Search for body { ... background(-color): ... }
    m_body = re.search(r'(?:^|[\s{}])body\s*\{[^}]*background(?:-color)?\s*:\s*([^;!]+)', html, re.I)
    if m_body:
        val = _resolve_var(m_body.group(1))
        if val:
            return val

    # 3. Check for :root --bg or --bg-primary or --background
    root_match = re.search(r'(--bg(?:-primary|-color)?|--background)\s*:\s*([^;!}}]+)', html, re.I)
    if root_match:
        val = _clean_color(root_match.group(2))
        if val:
            return val

    # 4. Check inline body style
    inline_match = re.search(r'<body[^>]*style=["\'][^"\']*background(?:-color)?\s*:\s*([^;"\']+)', html, re.I)
    if inline_match:
        val = _clean_color(inline_match.group(1))
        if val:
            return val

    return "#ffffff"


def is_dark_color(color_str: str) -> bool:
    """Determines whether a background color is dark (luminance < 128)."""
    try:
        color = color_str.strip().lower()
        if color.startswith("#"):
            hex_str = color.lstrip("#")
            if len(hex_str) == 3:
                hex_str = "".join(c * 2 for c in hex_str)
            if len(hex_str) == 6:
                r = int(hex_str[0:2], 16)
                g = int(hex_str[2:4], 16)
                b = int(hex_str[4:6], 16)
                lum = 0.299 * r + 0.587 * g + 0.114 * b
                return lum < 128
        elif color.startswith("rgb"):
            nums = re.findall(r'\d+', color)
            if len(nums) >= 3:
                r, g, b = int(nums[0]), int(nums[1]), int(nums[2])
                lum = 0.299 * r + 0.587 * g + 0.114 * b
                return lum < 128
        elif color in ("black", "navy", "darkblue", "midnightblue", "darkslategray"):
            return True
    except Exception:
        pass
    return False


def inject_pagination_css(html: str, layout: dict) -> str:
    """Injects pagination rules and guarantees margins in both HTML screen view and Playwright PDF."""
    page_format = layout.get("page_format", "A4")
    m_top = layout.get("margin_top", 20)
    m_bottom = layout.get("margin_bottom", 20)
    m_left = layout.get("margin_left", 20)
    m_right = layout.get("margin_right", 20)

    doc_bg = detect_background_color(html)
    is_dark = is_dark_color(doc_bg)
    screen_outer_bg = "#07070d" if is_dark else "#f1f5f9"
    screen_shadow = "rgba(0, 0, 0, 0.65)" if is_dark else "rgba(0, 0, 0, 0.12)"

    html = re.sub(r'@page\s*\{[^}]*\}', '', html, flags=re.IGNORECASE)

    safety_css = f"""
    /* --- Hecos Auto-Pagination & Margin Layout --- */
    @page {{
        size: {page_format};
        margin: {m_top}mm {m_right}mm {m_bottom}mm {m_left}mm;
        background: {doc_bg};
    }}
    * {{ box-sizing: border-box; }}

    html {{
        background-color: {doc_bg} !important;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
    }}
    
    @media screen {{
        html {{
            background-color: {screen_outer_bg} !important;
            padding: 24px 0;
        }}
        body {{
            margin: 0 auto;
            padding: {m_top}mm {m_right}mm {m_bottom}mm {m_left}mm;
            max-width: 210mm;
            min-height: 297mm;
            box-sizing: border-box;
            background-color: {doc_bg} !important;
            box-shadow: 0 8px 32px {screen_shadow};
            border-radius: 4px;
        }}
    }}

    @media print {{
        html, body {{
            margin: 0 !important;
            padding: 0 !important;
            background-color: {doc_bg} !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
        }}
    }}

    .page {{
        page-break-after: always;
        width: 100%;
        overflow: hidden;
        position: relative;
        box-sizing: border-box;
    }}
    .page:last-child {{ page-break-after: auto; }}
    img {{ max-width: 100%; height: auto; display: block; margin: 8px auto; }}
    img, figure, .photo-card, .gallery, .photo-grid, .card, table {{
        page-break-inside: avoid;
    }}
    h1, h2, h3, h4 {{
        page-break-after: avoid;
    }}
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        style_tag = soup.find("style")
        if style_tag:
            style_tag.string = (style_tag.string or "") + "\n" + safety_css
        else:
            head = soup.find("head")
            if not head:
                head = soup.new_tag("head")
                if soup.html:
                    soup.html.insert(0, head)
            new_style = soup.new_tag("style")
            new_style.string = safety_css
            head.append(new_style)
        return str(soup)
    except ImportError:
        if "</head>" in html:
            return html.replace("</head>", f"<style>\n{safety_css}\n</style>\n</head>")
        return f"<style>\n{safety_css}\n</style>\n" + html


def adapt_gallery_photos(html: str, v_dict: dict, default_photo_count: int = 0) -> str:
    """Adapts photo gallery in rendered HTML to match requested photos."""
    if not html:
        return html

    img_items = []
    for k in sorted(v_dict.keys()):
        if re.search(r'^(?:img|image|foto|photo)\d+$', k, re.IGNORECASE):
            num_match = re.search(r'\d+', k)
            if num_match:
                num = int(num_match.group())
                img_items.append((num, k, str(v_dict[k])))
    img_items.sort(key=lambda x: x[0])

    req_count = v_dict.get("num_photos") or v_dict.get("photo_count") or default_photo_count
    try:
        req_count = int(req_count)
    except Exception:
        req_count = 0

    target_count = len(img_items)
    if req_count > 0 and (target_count == 0 or req_count != target_count):
        target_count = req_count

    if target_count <= 0:
        return html

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        gallery = soup.find(class_=re.compile(r'\b(?:gallery|photo-grid|grid|photos)\b', re.IGNORECASE))
        if not gallery:
            return html

        cards = gallery.find_all(class_=re.compile(r'\b(?:photo-card|grid-item|card|photo-item)\b', re.IGNORECASE))
        if not cards:
            cards = [child for child in gallery.find_all(recursive=False) if child.find('img')]

        if not cards:
            return html

        blueprint = cards[0]
        current_count = len(cards)

        def _to_roman(n):
            val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
            syb = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
            res = ""
            i = 0
            while n > 0:
                for _ in range(n // val[i]):
                    res += syb[i]
                    n -= val[i]
                i += 1
            return res or str(n)

        if target_count < current_count:
            for card in cards[target_count:]:
                card.decompose()
            remaining_cards = cards[:target_count]
        else:
            remaining_cards = list(cards)
            for i in range(current_count, target_count):
                new_card = BeautifulSoup(str(blueprint), "html.parser").find()
                gallery.append(new_card)
                remaining_cards.append(new_card)

        for i, card in enumerate(remaining_cards):
            slot_idx = i + 1
            img_key = f"img{slot_idx}"
            cap_key = f"caption{slot_idx}"

            img_val = v_dict.get(img_key)
            if not img_val and img_items:
                img_val = img_items[i % len(img_items)][2]

            img_tag = card.find("img")
            if img_tag and img_val:
                img_tag["src"] = str(img_val)
                img_tag["alt"] = f"Scena {slot_idx}"

            cap_val = v_dict.get(cap_key)
            if not cap_val:
                cap_val = v_dict.get("subtitle") or f"Scena {_to_roman(slot_idx)}"

            cap_div = card.find(class_=re.compile(r'\b(?:caption|item-caption|text)\b', re.IGNORECASE))
            if cap_div:
                scene_span = cap_div.find(class_=re.compile(r'\b(?:scene-num|badge|tag|strong)\b', re.IGNORECASE))
                if scene_span:
                    if scene_span.name == "strong":
                        scene_span.string = _to_roman(slot_idx)
                    else:
                        scene_span.string = f"Scena {_to_roman(slot_idx)}"
                    span_html = str(scene_span)
                    cap_div.clear()
                    cap_div.append(BeautifulSoup(span_html, "html.parser"))
                    cap_div.append(f" {cap_val}")
                else:
                    cap_div.string = cap_val

        return str(soup)
    except Exception as e:
        logger.warning(f"[DOCS] Gallery photo adaptation failed: {e}")
        return html
