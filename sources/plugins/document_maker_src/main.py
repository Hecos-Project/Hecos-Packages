import os
import uuid
import json
import re
import glob
import random
from hecos.core.logging import logger
from hecos.app.config import ConfigManager


class DocsTools:
    def __init__(self):
        self.config = ConfigManager().config
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_file = os.path.join(self.plugin_dir, "docs_config.json")

    def _get_save_dir(self):
        default_path = "media/documents"
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                    default_path = data.get("pdf_save_path", default_path)
            except Exception as e:
                logger.error(f"[DOCS] Failed to read config: {e}")
        
        # Resolve path relative to hecos root (workspace)
        root_dir = os.path.dirname(os.path.dirname(self.plugin_dir))
        full_path = os.path.join(root_dir, os.path.normpath(default_path))
        os.makedirs(full_path, exist_ok=True)
        return full_path

    def _get_layout_config(self):
        default_config = {
            "page_format": "A4",
            "ai_optimization": "hybrid",
            "margin_top": 20,
            "margin_bottom": 20,
            "margin_left": 20,
            "margin_right": 20
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                    default_config.update({k: data[k] for k in default_config.keys() if k in data})
            except Exception as e:
                logger.error(f"[DOCS] Failed to read config: {e}")
        return default_config

    def _resolve_image_paths(self, html_content: str) -> str:
        """Resolves local image paths to file:/// URLs for Playwright rendering."""
        root_dir = os.path.dirname(os.path.dirname(self.plugin_dir))
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
                # If file:/// points to a non-existent file, extract basename and re-resolve
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

            # 6. Safety fallback: If still not resolved or does not exist on disk,
            # map to the latest generated batch so there are never broken image links in the document.
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

    def _generate_pdf_from_html(self, final_html: str, pdf_output_path: str) -> str:
        """Generates a PDF from HTML using Playwright. Returns path or error string."""
        try:
            from hecos.modules.browser_automation.plugin import engine
        except ImportError:
            return self._generate_pdf_fallback(final_html, pdf_output_path)

        def _pdf_task():
            # Make sure browser is running
            if not engine._state.get("browser") or not engine._state["browser"].is_connected():
                from playwright.sync_api import sync_playwright
                if not engine._state.get("pw_instance"):
                    engine._state["pw_instance"] = sync_playwright().start()
                engine._state["browser"] = engine._state["pw_instance"].chromium.launch(headless=True)
            
            browser = engine._state["browser"]
            context = browser.new_context()
            page = context.new_page()
            
            try:
                import tempfile
                temp_html_path = None
                with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as tmp:
                    tmp.write(final_html)
                    temp_html_path = tmp.name

                file_url = "file:///" + os.path.normpath(temp_html_path).replace("\\", "/")
                layout = self._get_layout_config()
                page.goto(file_url, wait_until="networkidle")
                page.pdf(
                    path=pdf_output_path, 
                    format=layout["page_format"], 
                    print_background=True, 
                    margin={
                        "top": f"{layout['margin_top']}mm", 
                        "right": f"{layout['margin_right']}mm", 
                        "bottom": f"{layout['margin_bottom']}mm", 
                        "left": f"{layout['margin_left']}mm"
                    }
                )
            finally:
                if temp_html_path and os.path.exists(temp_html_path):
                    try:
                        os.remove(temp_html_path)
                    except Exception as e:
                        logger.error(f"[DOCS] Failed to delete temp HTML: {e}")
                page.close()
                context.close()
            return pdf_output_path

        try:
            result_path = engine._run_on_browser_thread(_pdf_task)
            if result_path and os.path.exists(result_path):
                return result_path
            else:
                logger.warning(f"[DOCS] Playwright returned path but file not found: {result_path}")
                return None
        except Exception as e:
            logger.error(f"[DOCS] Playwright PDF generation failed: {e}")
            return None

    def _generate_pdf_fallback(self, final_html: str, pdf_output_path: str) -> str:
        """Tries standalone Playwright when browser_automation module is unavailable."""
        try:
            from playwright.sync_api import sync_playwright
            import tempfile

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()
                
                temp_html_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as tmp:
                        tmp.write(final_html)
                        temp_html_path = tmp.name

                    file_url = "file:///" + os.path.normpath(temp_html_path).replace("\\", "/")
                    layout = self._get_layout_config()
                    page.goto(file_url, wait_until="networkidle")
                    page.pdf(
                        path=pdf_output_path, 
                        format=layout["page_format"], 
                        print_background=True, 
                        margin={
                            "top": f"{layout['margin_top']}mm", 
                            "right": f"{layout['margin_right']}mm", 
                            "bottom": f"{layout['margin_bottom']}mm", 
                            "left": f"{layout['margin_left']}mm"
                        }
                    )
                finally:
                    if temp_html_path and os.path.exists(temp_html_path):
                        try:
                            os.remove(temp_html_path)
                        except Exception:
                            pass
                    page.close()
                    context.close()
                    browser.close()

            if os.path.exists(pdf_output_path):
                return pdf_output_path
            return None
        except ImportError:
            logger.error("[DOCS] Playwright is not installed. PDF generation unavailable. "
                         "Install with: pip install playwright && python -m playwright install chromium")
            return None
        except Exception as e:
            logger.error(f"[DOCS] Standalone Playwright PDF failed: {e}")
            return None

    def _detect_background_color(self, html: str) -> str:
        """
        Detects the document background color (solid color) from CSS variables,
        body rules, inline styles, or @media print rules.
        Falls back to '#ffffff' if light or not found.
        """
        def _clean_color(val: str) -> str:
            if not val:
                return ""
            val = val.strip().rstrip(";")
            val = re.sub(r'\s*!important', '', val, flags=re.I).strip()
            # If linear-gradient / radial-gradient, extract first or dominant hex/rgb color
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

        # 3. Check for :root --bg or --bg-primary or --background or --bg-color
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

    def _is_dark_color(self, color_str: str) -> bool:
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

    def _inject_pagination_css(self, html: str) -> str:
        """
        Safety net: injects pagination rules and guarantees margins in both
        HTML screen view and Playwright PDF rendering, matching the document's
        background color so borders are never unprinted white.
        """
        layout = self._get_layout_config()
        page_format = layout.get("page_format", "A4")
        m_top = layout.get("margin_top", 20)
        m_bottom = layout.get("margin_bottom", 20)
        m_left = layout.get("margin_left", 20)
        m_right = layout.get("margin_right", 20)

        doc_bg = self._detect_background_color(html)
        is_dark = self._is_dark_color(doc_bg)
        screen_outer_bg = "#07070d" if is_dark else "#f1f5f9"
        screen_shadow = "rgba(0, 0, 0, 0.65)" if is_dark else "rgba(0, 0, 0, 0.12)"

        # 1. Clean existing @page rules to prevent conflicting margins or missing backgrounds
        html = re.sub(
            r'@page\s*\{[^}]*\}',
            '',
            html,
            flags=re.IGNORECASE
        )

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
        
        /* Clean screen viewing with configured margins and matching background */
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

        /* Print / PDF rendering uses Playwright & @page margins cleanly with full bleed background */
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
            
            # Check if there's already a style tag
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
            # Fallback string manipulation if bs4 isn't available
            if "</head>" in html:
                return html.replace("</head>", f"<style>\n{safety_css}\n</style>\n</head>")
            return f"<style>\n{safety_css}\n</style>\n" + html

    def _adapt_gallery_photos(self, html: str, v_dict: dict, default_photo_count: int = 0) -> str:
        """
        Dynamically adapts the photo gallery in the rendered HTML to match
        the exact number of requested photos (from 2 up to 20+).
        Expands or contracts the gallery cards while maintaining layout integrity.
        """
        if not html:
            return html

        # Discover all image entries in v_dict
        img_items = []
        for k in sorted(v_dict.keys()):
            if re.search(r'^(?:img|image|foto|photo)\d+$', k, re.IGNORECASE):
                num_match = re.search(r'\d+', k)
                if num_match:
                    num = int(num_match.group())
                    img_items.append((num, k, str(v_dict[k])))
        img_items.sort(key=lambda x: x[0])

        # Also support explicit num_photos request or config default
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

            # Roman numeral conversion helper
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

            # Populate images and captions
            for i, card in enumerate(remaining_cards):
                slot_idx = i + 1
                img_key = f"img{slot_idx}"
                cap_key = f"caption{slot_idx}"

                # Image source resolution
                img_val = v_dict.get(img_key)
                if not img_val and img_items:
                    img_val = img_items[i % len(img_items)][2]

                img_tag = card.find("img")
                if img_tag and img_val:
                    img_tag["src"] = str(img_val)
                    img_tag["alt"] = f"Scena {slot_idx}"

                # Caption resolution
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

    def list_images(self, folder: str = "", limit: int = 10, sort: str = "recent", random_pick: bool = False) -> str:
        """
        Lists available images in media/images, media/generated_photos, or any specified folder.
        Use this before generating a document when the user asks to reuse existing photos without generating new ones.

        :param folder: Optional folder or subfolder name to scan (e.g. 'images', 'generated_photos', or relative/absolute path).
        :param limit: Maximum number of images to return (default: 10, max: 50).
        :param sort: Sorting order: 'recent' (newest first, default), 'oldest', 'name' (alphabetical), or 'random'.
        :param random_pick: If True, randomly picks 'limit' images from the available images.
        """
        root_dir = os.path.dirname(os.path.dirname(self.plugin_dir))
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

    DOCS__list_images = list_images

    def generate_pdf(self, html_content: str = None, template_id: str = None, template_vars: str = None, filename: str = None) -> str:
        """
        Generates a document (HTML + PDF) from raw HTML content or a template.
        Returns the absolute paths of the generated files.

        WORKFLOW: When creating a document with AI-generated images:
        1. First generate all images with IMAGE_GEN__generate_image
        2. Collect the filenames from [[IMG:filename]] tags in the results
        3. Then call this tool with html_content using <img src="/api/images/FILENAME"> for each image
        4. ALWAYS complete the full workflow — never stop after generating images without producing the document.

        :param html_content: Raw HTML content to convert to a document. Use <img src="/api/images/FILENAME"> for generated images.
        :param template_id: The ID of an existing template to render.
        :param template_vars: JSON string of variables to inject into the template.
        :param filename: Desired name for the output file (e.g. 'magazine.pdf'). A random name is used if omitted.
        """
        # Check config for defaults
        config_data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8-sig") as f:
                    config_data = json.load(f)
            except Exception as e:
                logger.error(f"[DOCS] Failed to read config: {e}")

        default_tpl = config_data.get("default_template_id", "").strip()
        force_default_tpl = config_data.get("force_default_template", False)

        # Resolve template_id aliases ('default', 'predefinito')
        if template_id and template_id.lower() in ("default", "predefinito"):
            template_id = default_tpl

        # Fallback to default_template_id if template_id is missing and default is configured
        if not template_id and default_tpl:
            if force_default_tpl or template_vars or not html_content:
                template_id = default_tpl

        if not html_content and not template_id:
            return "Error: You must provide either html_content or template_id."

        try:
            # 1. Resolve HTML content
            final_html = html_content

            # Template resolution: template takes priority if template_id is given
            # or if force_default_template is enabled.
            if template_id:
                from hecos.hpm.libraries.templates.store import list_templates, render_template, get_template
                all_tpls = list_templates()
                target = None

                # 1. Exact match by ID or Name
                for t in all_tpls:
                    if t["id"] == template_id or t["name"].lower() == template_id.lower():
                        target = t
                        break

                # 2. Fuzzy match by keywords
                if not target:
                    clean_query = template_id.lower().replace("_", " ").replace("-", " ")
                    query_words = clean_query.split()
                    for t in all_tpls:
                        t_name_lower = t["name"].lower()
                        t_id_lower = t["id"].lower()
                        if all(w in t_name_lower or w in t_id_lower for w in query_words):
                            target = t
                            break

                # 3. Partial keyword match
                if not target:
                    kw_list = [w for w in clean_query.split() if len(w) >= 4 and w not in ("foto", "documento", "template", "modello")]
                    if kw_list:
                        for t in all_tpls:
                            t_name_lower = t["name"].lower()
                            t_id_lower = t["id"].lower()
                            if any(w in t_name_lower or w in t_id_lower for w in kw_list):
                                target = t
                                break

                if not target:
                    return f"Error: Template '{template_id}' not found."

                # Parse template_vars safely (accepts dict or JSON string)
                if isinstance(template_vars, dict):
                    v_dict = dict(template_vars)
                elif isinstance(template_vars, str) and template_vars.strip():
                    try:
                        v_dict = json.loads(template_vars)
                    except Exception as _je:
                        logger.warning(f"[DOCS] Failed to parse template_vars JSON: {_je}")
                        v_dict = {}
                else:
                    v_dict = {}

                tpl_meta = get_template(target["id"])
                required_vars = tpl_meta.get("variables", []) if tpl_meta else []

                # Guard: If model passed template_id AND html_content, but forgot template_vars:
                # Inform the model that template content must be supplied in template_vars, not html_content.
                if not v_dict and html_content and not force_default_tpl:
                    vars_list = ", ".join(required_vars)
                    return (
                        f"Error: You specified template_id='{target['name']}' ({target['id']}) but passed content in "
                        f"'html_content' instead of 'template_vars'.\n"
                        f"To render this template, call DOCS__generate_pdf with:\n"
                        f"- template_id: '{target['id']}'\n"
                        f"- template_vars: JSON string with populated variables: {vars_list}\n"
                        f"- Leave 'html_content' empty when using a template.\n"
                        f"(If you intended to use custom raw HTML without any template, omit template_id entirely)."
                    )

                # Clean and sanitize image variables: if value is <img src="...">, extract just the URL
                for k, v in list(v_dict.items()):
                    if isinstance(v, str):
                        if re.search(r'^(?:img|image|foto|photo)\d*$', k, re.IGNORECASE) or k.lower().startswith('img'):
                            m_src = re.search(r'src=["\']([^"\']+)["\']', v)
                            if m_src:
                                v_dict[k] = m_src.group(1)

                # Collect available existing images in media folder for automatic fallback or keyword resolution
                root_dir = os.path.dirname(os.path.dirname(self.plugin_dir))
                root_media_dirs = [
                    os.path.join(root_dir, "media", "images"),
                    os.path.join(root_dir, "media", "generated_photos")
                ]
                existing_imgs_pool = []
                for fld in root_media_dirs:
                    if os.path.isdir(fld):
                        for f in os.listdir(fld):
                            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                                existing_imgs_pool.append(os.path.join(fld, f))
                existing_imgs_pool.sort(key=lambda p: os.path.getmtime(p), reverse=True)

                # Resolve special image keywords in v_dict ('random', 'casual', 'latest', 'recent')
                for k in list(v_dict.keys()):
                    val = str(v_dict[k]).strip().lower()
                    if val in ("random", "casual", "a caso", "/api/images/random", "random.png"):
                        if existing_imgs_pool:
                            pick = random.choice(existing_imgs_pool)
                            v_dict[k] = f"/api/images/{os.path.basename(pick)}"
                    elif val in ("latest", "recent", "/api/images/latest", "latest.png"):
                        if existing_imgs_pool:
                            v_dict[k] = f"/api/images/{os.path.basename(existing_imgs_pool[0])}"

                # Graceful handling for templates with multiple image slots (e.g. img1..img6):
                tpl_img_keys = [v for v in required_vars if re.search(r'^(?:img|image|foto|photo)\d*$', v, re.IGNORECASE) or v.startswith('img')]
                provided_imgs = [v_dict[k] for k in tpl_img_keys if k in v_dict and str(v_dict[k]).strip()]
                if not provided_imgs:
                    provided_imgs = [str(v) for v in v_dict.values() if isinstance(v, str) and '/api/images/' in v]

                # AUTO-LOAD EXISTING PHOTOS IF NONE SUPPLIED:
                # When user requests a document reusing existing photos without binding them manually,
                # auto-populate empty image slots with the latest photos from media/images.
                if not provided_imgs and tpl_img_keys and existing_imgs_pool:
                    logger.info(f"[DOCS] Caller provided no image bindings; auto-loading {len(tpl_img_keys)} existing photos from media/images.")
                    for i, img_k in enumerate(tpl_img_keys):
                        sel_f = existing_imgs_pool[i % len(existing_imgs_pool)]
                        v_dict[img_k] = f"/api/images/{os.path.basename(sel_f)}"
                        provided_imgs.append(v_dict[img_k])
                        cap_k = img_k.replace('img', 'caption').replace('foto', 'caption').replace('photo', 'caption')
                        if cap_k in required_vars and (cap_k not in v_dict or not str(v_dict[cap_k]).strip()):
                            ref_cap = v_dict.get('caption1') or v_dict.get('subtitle') or 'Scena'
                            v_dict[cap_k] = f"{ref_cap} #{i + 1}"

                if provided_imgs and tpl_img_keys:
                    for i, img_key in enumerate(tpl_img_keys):
                        if img_key not in v_dict or not str(v_dict[img_key]).strip():
                            v_dict[img_key] = provided_imgs[i % len(provided_imgs)]
                            cap_key = img_key.replace('img', 'caption').replace('foto', 'caption').replace('photo', 'caption')
                            if cap_key in required_vars and (cap_key not in v_dict or not str(v_dict[cap_key]).strip()):
                                ref_cap = v_dict.get('caption1') or v_dict.get('subtitle') or 'Illustrazione'
                                v_dict[cap_key] = f"{ref_cap} #{i + 1}"

                # Validate missing critical text variables
                if required_vars:
                    # Ignore image keys from fatal missing list if at least one image was provided
                    critical_vars = [v for v in required_vars if not (provided_imgs and (v in tpl_img_keys or 'caption' in v))]
                    missing = [v for v in critical_vars if v not in v_dict or not str(v_dict[v]).strip()]
                    if missing and (len(missing) > len(critical_vars) * 0.3 or len(missing) >= 3 or not v_dict):
                        vars_list = ", ".join(required_vars)
                        missing_list = ", ".join(missing)
                        return (
                            f"Error: Template '{target['name']}' requires template_vars but you missed some critical ones.\n"
                            f"Missing or empty variables: {missing_list}\n\n"
                            f"You MUST call this tool again with template_vars set to a JSON string containing "
                            f"ALL required keys populated with real, extensive content. DO NOT leave them empty.\n"
                            f"All required variables: {vars_list}\n"
                            f"For image variables (img1, img2...), pass the path string like '/api/images/FILENAME.png'."
                        )
                    elif missing:
                        logger.warning(f"[DOCS] Template '{target['name']}' has unfilled variables: {missing}")

                rendered = render_template(target["id"], v_dict)
                final_html = rendered["body_html"]

            if not final_html:
                return "Error: Generated HTML is empty."
                
            # 1.a Adapt gallery photos dynamically based on provided images / requested photo count
            if 'v_dict' in locals() and v_dict:
                final_html = self._adapt_gallery_photos(final_html, v_dict, config_data.get("default_photo_count", 0))

            # 1.b Resolve local image links for Playwright
            final_html = self._resolve_image_paths(final_html)

            # 1.c Auto-inject pagination CSS safety net
            final_html = self._inject_pagination_css(final_html)

            # Get generation defaults
            gen_html = True
            gen_pdf = True
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, "r", encoding="utf-8-sig") as f:
                        data = json.load(f)
                        gen_html = data.get("generate_html", True)
                        gen_pdf = data.get("generate_pdf", True)
                except Exception as e:
                    logger.error(f"[DOCS] Failed to read config defaults: {e}")

            # 2. Determine output path
            if not filename:
                filename = f"document_{uuid.uuid4().hex[:8]}"
            else:
                if filename.lower().endswith(".pdf") or filename.lower().endswith(".html"):
                    filename = filename.rsplit(".", 1)[0]
            
            output_dir = self._get_save_dir()
            pdf_output_path = os.path.join(output_dir, filename + ".pdf")
            html_output_path = os.path.join(output_dir, filename + ".html")

            results = []

            # Generate HTML if requested
            if gen_html:
                try:
                    try:
                        from hecos.core.agent.traces import AgentTracer
                        AgentTracer.emit(None, "Generating HTML...", level="tool")
                    except Exception:
                        pass
                        
                    with open(html_output_path, "w", encoding="utf-8") as f:
                        f.write(final_html)
                    results.append(f"HTML: {html_output_path}")
                    logger.info(f"[DOCS] HTML saved: {html_output_path}")
                except Exception as e:
                    logger.error(f"[DOCS] Failed to save HTML: {e}")

            if gen_pdf:
                try:
                    from hecos.core.agent.traces import AgentTracer
                    AgentTracer.emit(None, "Generating PDF with Playwright...", level="tool")
                except Exception:
                    pass
                    
                pdf_result = self._generate_pdf_from_html(final_html, pdf_output_path)
                if pdf_result and os.path.exists(pdf_result):
                    logger.info(f"[DOCS] Generated PDF successfully at {pdf_result}")
                    results.append(f"PDF: {pdf_result}")
                else:
                    warning = (
                        "⚠️ PDF generation failed (Playwright unavailable or Chromium not installed). "
                        "The HTML version was saved successfully. "
                        "To enable PDF: pip install playwright && python -m playwright install chromium"
                    )
                    results.append(warning)
                    logger.warning(f"[DOCS] {warning}")

            if not results:
                return "Error: Neither HTML nor PDF generation was enabled, or generation failed."

            return "\n".join(results)

        except Exception as e:
            logger.error(f"[DOCS] Failed to generate document: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return f"Error generating document: {str(e)}"

    def list_documents(self, search: str = "") -> str:
        """
        Lists all documents in the documents folder. Optionally filters by name.
        Use this to find existing documents before modifying them.
        Returns filename, size, and a preview of each matching document.
        :param search: Optional search term to filter documents by filename.
        """
        try:
            output_dir = self._get_save_dir()
            files = []
            
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
                        # Extract title if present
                        title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
                        title = title_match.group(1) if title_match else ""
                        
                        # Count images
                        img_count = len(re.findall(r'<img\s', content, re.IGNORECASE))
                        
                        # Extract text preview (strip HTML tags)
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
                
                # Make the filename a markdown link using the absolute path so the UI file card processor catches it
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

    def modify_document(self, file_path: str, operation: str, content: str, target_selector: str = "") -> str:
        """
        Modifies an existing HTML document in media/documents.
        After modification, the PDF is automatically regenerated.

        Operations:
        - 'add_images': Inserts <img> tags. If target_selector is set, replaces matching placeholder text.
          Otherwise appends images to the first .gallery, .photo-gallery, or main container.
        - 'replace_section': Replaces the element matching target_selector with the new content.
        - 'change_layout': Applies CSS layout changes. content should be CSS rules (e.g. '.gallery { grid-template-columns: repeat(3, 1fr); }').
        - 'append': Appends content before </body>.
        - 'patch': Finds target_selector as literal text in the HTML and replaces it with content.

        :param file_path: Path or filename of the document to modify. If just a name, searches in media/documents.
        :param operation: One of: add_images, replace_section, change_layout, append, patch
        :param content: The HTML content, images, or CSS to inject.
        :param target_selector: CSS selector (for replace_section) or text pattern (for patch/add_images) to target.
        """
        try:
            # Resolve file path
            resolved_path = self._resolve_document_path(file_path)
            if not resolved_path:
                return f"Error: Document not found: '{file_path}'. Use list_documents to see available files."

            # Read existing content
            with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
                original_html = f.read()

            modified_html = original_html
            operation = operation.lower().strip()

            if operation == "add_images":
                modified_html = self._op_add_images(modified_html, content, target_selector)

            elif operation == "replace_section":
                if not target_selector:
                    return "Error: replace_section requires target_selector (CSS selector to find the element to replace)."
                modified_html = self._op_replace_section(modified_html, content, target_selector)

            elif operation == "change_layout":
                modified_html = self._op_change_layout(modified_html, content)

            elif operation == "append":
                modified_html = self._op_append(modified_html, content)

            elif operation == "patch":
                if not target_selector:
                    return "Error: patch requires target_selector (the exact text to find and replace)."
                if target_selector not in original_html:
                    preview = original_html[:400].replace('\n', '↵')
                    return f"Error: Text to replace not found in document. File starts with: {preview}..."
                modified_html = original_html.replace(target_selector, content, 1)

            else:
                return f"Error: Unknown operation '{operation}'. Use: add_images, replace_section, change_layout, append, or patch."

            if modified_html == original_html:
                return "Warning: No changes were made to the document. The target may not have been found."

            # Save modified HTML
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(modified_html)
            logger.info(f"[DOCS] Document modified: {resolved_path}")

            results = [f"✅ Document modified successfully: {resolved_path}"]

            # Auto-regenerate PDF
            pdf_path = resolved_path.rsplit(".", 1)[0] + ".pdf"
            resolved_for_pdf = self._resolve_image_paths(modified_html)
            pdf_result = self._generate_pdf_from_html(resolved_for_pdf, pdf_path)
            if pdf_result and os.path.exists(pdf_result):
                results.append(f"✅ PDF regenerated: {pdf_result}")
            else:
                results.append("⚠️ PDF regeneration failed (Playwright unavailable). HTML was updated successfully.")

            return "\n".join(results)

        except Exception as e:
            logger.error(f"[DOCS] Failed to modify document: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return f"Error modifying document: {e}"

    def _resolve_document_path(self, file_path: str) -> str:
        """Resolves a document path — accepts absolute paths, relative names, or partial matches."""
        # Absolute path
        if os.path.isabs(file_path) and os.path.exists(file_path):
            return file_path

        output_dir = self._get_save_dir()

        # Exact filename match
        if not file_path.endswith((".html", ".pdf")):
            file_path_html = file_path + ".html"
        else:
            file_path_html = file_path

        exact = os.path.join(output_dir, os.path.basename(file_path_html))
        if os.path.exists(exact):
            return exact

        # Fuzzy search
        search_term = os.path.basename(file_path).replace(".html", "").replace(".pdf", "").lower()
        for f in os.listdir(output_dir):
            if search_term in f.lower() and f.endswith(".html"):
                return os.path.join(output_dir, f)

        return None

    def _op_add_images(self, html: str, content: str, target_selector: str) -> str:
        """Adds images to the document. content is HTML with <img> tags."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # If target_selector is specified, find and replace placeholder text
            if target_selector:
                # Find elements containing the target text
                for element in soup.find_all(string=lambda text: text and target_selector in text):
                    new_content = BeautifulSoup(content, "html.parser")
                    element.replace_with(new_content)
                return str(soup)

            # Otherwise, find the gallery container and append
            gallery = (
                soup.select_one(".gallery") or
                soup.select_one(".photo-gallery") or
                soup.select_one(".photo-grid") or
                soup.select_one("main") or
                soup.find("body")
            )
            if gallery:
                new_content = BeautifulSoup(content, "html.parser")
                gallery.append(new_content)
            
            return str(soup)
        except ImportError:
            # Fallback without BeautifulSoup — append before </body>
            return self._op_append(html, content)

    def _op_replace_section(self, html: str, content: str, selector: str) -> str:
        """Replaces the first element matching the CSS selector with new content."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            target = soup.select_one(selector)
            if target:
                new_content = BeautifulSoup(content, "html.parser")
                target.replace_with(new_content)
                return str(soup)
            else:
                logger.warning(f"[DOCS] CSS selector '{selector}' not found in document.")
                return html
        except ImportError:
            return html

    def _op_change_layout(self, html: str, css_content: str) -> str:
        """Injects CSS rules into the document's <style> block."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            
            style_tag = soup.find("style")
            if style_tag:
                style_tag.string = (style_tag.string or "") + "\n/* --- Layout Override --- */\n" + css_content
            else:
                head = soup.find("head")
                if not head:
                    head = soup.new_tag("head")
                    if soup.html:
                        soup.html.insert(0, head)
                new_style = soup.new_tag("style")
                new_style.string = css_content
                head.append(new_style)
            
            return str(soup)
        except ImportError:
            # Fallback: inject style tag via regex
            if "</head>" in html:
                return html.replace("</head>", f"<style>\n{css_content}\n</style>\n</head>")
            return f"<style>\n{css_content}\n</style>\n" + html

    def _op_append(self, html: str, content: str) -> str:
        """Appends content before </body>."""
        if "</body>" in html:
            return html.replace("</body>", f"\n{content}\n</body>")
        return html + f"\n{content}"
    def DOCS__optimize_layout(self, document_id: str) -> str:
        """
        Calculates page breaks for a document and returns a report of elements split across pages.
        Used to analyze pagination and determine where manual page breaks are needed.
        """
        output_dir = self._get_save_dir()
        if not document_id.endswith(".html"):
            document_id += ".html"
        
        file_path = os.path.join(output_dir, document_id)
        if not os.path.exists(file_path):
            file_path = self._find_document(document_id)
            if not file_path:
                return f"Error: Document {document_id} not found."
                
        # Only support mathematical bounding box extraction via Playwright for now
        from hecos.core.modules import engine
        if not engine.get_module("browser_automation"):
            return "Error: browser_automation module is required for layout optimization."
            
        def _optimization_task():
            if not engine._state.get("browser") or not engine._state["browser"].is_connected():
                from playwright.sync_api import sync_playwright
                if not engine._state.get("pw_instance"):
                    engine._state["pw_instance"] = sync_playwright().start()
                engine._state["browser"] = engine._state["pw_instance"].chromium.launch(headless=True)
            
            browser = engine._state["browser"]
            context = browser.new_context()
            page = context.new_page()
            
            try:
                file_url = "file:///" + os.path.normpath(file_path).replace("\\", "/")
                page.goto(file_url, wait_until="networkidle")
                
                # Extract layout issues
                issues = page.evaluate('''() => {
                    const pageHeight = 1122.5; // A4 height at 96 DPI
                    const elements = document.querySelectorAll('h1, h2, h3, img, p, div.card, div.photo-card, div.gallery');
                    const issues = [];
                    elements.forEach((el, index) => {
                        const rect = el.getBoundingClientRect();
                        const top = rect.top + window.scrollY;
                        const bottom = rect.bottom + window.scrollY;
                        
                        const startPage = Math.floor(top / pageHeight);
                        const endPage = Math.floor(bottom / pageHeight);
                        
                        if (startPage !== endPage && bottom - top > 0) {
                            let snippet = el.outerHTML;
                            if (snippet.length > 80) snippet = snippet.substring(0, 80) + '...';
                            issues.push(`Pagina ${startPage+1}->${endPage+1}: Elemento tagliato a meta -> ${snippet}`);
                        } else if (endPage > startPage && top % pageHeight > pageHeight - 80 && el.tagName.match(/^H[1-6]/)) {
                            issues.push(`Pagina ${startPage+1}: Titolo isolato a fine pagina -> ${el.textContent.substring(0,40)}`);
                        }
                    });
                    return issues;
                }''')
                return issues
            except Exception as e:
                logger.error(f"[DOCS] Layout optimization failed: {e}")
                return [f"Error calculating layout: {str(e)}"]
            finally:
                page.close()
                context.close()
                
        issues = engine._run_on_browser_thread(_optimization_task)
        if not issues:
            return "✅ L'impaginazione sembra corretta, non ci sono elementi importanti tagliati a metà."
        
        report = "⚠️ ATTENZIONE: Sono stati rilevati i seguenti errori di impaginazione:\n\n"
        for issue in issues:
            report += f"- {issue}\n"
        report += "\nUsa `DOCS__modify_document` per inserire `<div style=\"page-break-before: always;\"></div>` prima degli elementi tagliati."
        return report

    # Bidirectional aliases for native and prefixed dispatcher invocation
    DOCS__generate_pdf = generate_pdf
    DOCS__list_documents = list_documents
    DOCS__modify_document = modify_document


# ── Module-level singleton (required by the Hecos plugin dispatcher) ──────────

tools = DocsTools()


def on_load(config):
    """Called by the plugin loader when the plugin is activated."""
    logger.debug("DOCS", "Document Maker plugin loaded.")
