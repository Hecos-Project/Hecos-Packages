import os
import uuid
import json
import re
import glob
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
                with open(self.config_file, "r", encoding="utf-8") as f:
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
                with open(self.config_file, "r", encoding="utf-8") as f:
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
        
        def resolve_img_path(match):
            path = match.group(2)
            logger.debug(f"[DOCS] Regex intercepted image path: '{path}'")
            
            # Ignore remote and data URIs
            if path.startswith(("http://", "https://", "data:", "file://")):
                logger.debug(f"[DOCS] Skipping remote/data/file URI: '{path}'")
                return match.group(0)

            abs_path = None
            
            # Check if it's already an absolute Windows path
            if os.path.isabs(path) and (path.startswith("C:\\") or path.startswith("C:/")):
                logger.debug(f"[DOCS] Path is already absolute Windows path: '{path}'")
                abs_path = path
                # Even if it's absolute, verify it exists; if not, try finding by basename
                if not os.path.exists(abs_path):
                    fallback = os.path.join(media_images_dir, os.path.basename(path))
                    if os.path.exists(fallback):
                        logger.debug(f"[DOCS] Absolute path not found, found by basename in media/images: '{fallback}'")
                        abs_path = fallback
                    else:
                        # Search all subdirs of media/
                        media_dir = os.path.dirname(media_images_dir)
                        basename = os.path.basename(path)
                        for subdir in os.listdir(media_dir):
                            candidate = os.path.join(media_dir, subdir, basename)
                            if os.path.exists(candidate):
                                logger.debug(f"[DOCS] Found image in media/{subdir}: '{candidate}'")
                                abs_path = candidate
                                break
            
            # Check for API paths
            elif path.startswith("/api/images/"):
                filename = path.replace("/api/images/", "")
                # Try media/images first, then generated_photos
                abs_path = os.path.join(media_images_dir, filename)
                if not os.path.exists(abs_path):
                    abs_path = os.path.join(generated_photos_dir, filename)
                if not os.path.exists(abs_path):
                    # Search all media subdirs
                    media_dir = os.path.dirname(media_images_dir)
                    for subdir in os.listdir(media_dir):
                        candidate = os.path.join(media_dir, subdir, filename)
                        if os.path.exists(candidate):
                            abs_path = candidate
                            break
                logger.debug(f"[DOCS] Resolved API path to: '{abs_path}'")
                    
            else:
                # Resolve relative to hecos root
                clean_path = path.lstrip("/\\")
                
                if clean_path.startswith("media/images/"):
                    abs_path = os.path.join(root_dir, clean_path)
                    logger.debug(f"[DOCS] Resolved media/images path to: '{abs_path}'")
                elif clean_path.startswith("../images/"):
                    # If a relative path is passed like ../images/file.jpg, assume it's relative to media/documents
                    abs_path = os.path.normpath(os.path.join(root_dir, "media/documents", clean_path))
                    # If it doesn't exist there, fallback to media_images_dir
                    if not os.path.exists(abs_path):
                        fallback_path = os.path.join(media_images_dir, os.path.basename(clean_path))
                        logger.debug(f"[DOCS] Relative path {abs_path} doesn't exist, falling back to: '{fallback_path}'")
                        abs_path = fallback_path
                    else:
                        logger.debug(f"[DOCS] Resolved relative path to: '{abs_path}'")
                else:
                    basename = os.path.basename(clean_path)
                    abs_path = os.path.join(media_images_dir, basename)
                    logger.debug(f"[DOCS] Resolved plain filename to: '{abs_path}'")

            if abs_path:
                # Playwright requires file:/// for absolute paths on Windows
                file_url = "file:///" + os.path.normpath(abs_path).replace("\\", "/")
                logger.debug(f"[DOCS] Final mapped URL for Playwright: '{file_url}'")
                return f'{match.group(1)}{file_url}{match.group(3)}'
            
            logger.debug(f"[DOCS] Could not resolve path: '{path}'")
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

    def _inject_pagination_css(self, html: str) -> str:
        """
        Safety net: injects pagination rules to guarantee correct PDF layout.
        Playwright margins handle the outer page margins (15mm), and this CSS
        ensures content inside flows correctly with proper spacing.
        """
        layout = self._get_layout_config()
        page_format = layout["page_format"]
        
        safety_css = f"""
        /* --- Hecos Auto-Pagination Safety Net --- */
        @page {{ size: {page_format}; margin: 0; }}
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; padding: 0; }}
        .page {{
            page-break-after: always;
            width: 100%;
            overflow: hidden;
            padding: 5mm 0;
            position: relative;
        }}
        .page:last-child {{ page-break-after: auto; }}
        img {{ max-width: 100%; height: auto; display: block; margin: 8px auto; }}
        img, figure, .photo-card, .gallery, .photo-grid, .card {{
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

    def DOCS__list_images(self, folder: str = "") -> str:
        """
        Lists available images in the media/images and media/generated_photos directories.
        Use this before generating a document to discover existing images that can be referenced
        with <img src="/api/images/FILENAME"> without regenerating them.
        :param folder: Optional subfolder to filter (e.g. 'generated_photos'). Leave empty to list all.
        """
        root_dir = os.path.dirname(os.path.dirname(self.plugin_dir))
        search_dirs = {
            "images": os.path.join(root_dir, "media", "images"),
            "generated_photos": os.path.join(root_dir, "media", "generated_photos"),
        }
        IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}

        results = []
        for subfolder, dirpath in search_dirs.items():
            if folder and folder.lower() not in subfolder.lower():
                continue
            if not os.path.isdir(dirpath):
                continue
            for fname in sorted(os.listdir(dirpath)):
                ext = os.path.splitext(fname)[1].lower()
                if ext not in IMAGE_EXTS:
                    continue
                size_bytes = os.path.getsize(os.path.join(dirpath, fname))
                size_str = f"{size_bytes / 1024:.1f} KB"
                results.append(f"  /api/images/{fname}  ({subfolder}, {size_str})")

        if not results:
            return "No images found in media/images or media/generated_photos."

        header = f"Found {len(results)} image(s). Use <img src=\"/api/images/FILENAME\"> to reference them:\n"
        return header + "\n".join(results)

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
        if not html_content and not template_id:
            return "Error: You must provide either html_content or template_id."

        try:
            # 1. Resolve HTML content
            final_html = html_content
            if template_id and not html_content:
                from hecos.hpm.libraries.templates.store import list_templates, render_template
                all_tpls = list_templates()
                target = None

                # Fuzzy match template_id
                for t in all_tpls:
                    if t["id"] == template_id or t["name"].lower() == template_id.lower():
                        target = t
                        break
                if not target:
                    query_words = template_id.lower().split()
                    for t in all_tpls:
                        if all(w in t["name"].lower() for w in query_words):
                            target = t
                            break

                if not target:
                    return f"Error: Template '{template_id}' not found."

                # Parse template_vars from JSON
                v_dict = json.loads(template_vars) if template_vars else {}

                # GUARD: If the template defines variables but the LLM didn't provide them,
                # return an error listing the required variables so the LLM re-calls correctly.
                from hecos.hpm.libraries.templates.store import get_template
                tpl_meta = get_template(target["id"])
                required_vars = tpl_meta.get("variables", []) if tpl_meta else []
                if required_vars:
                    missing = [v for v in required_vars if v not in v_dict or not str(v_dict[v]).strip()]
                    if missing and (len(missing) > len(required_vars) * 0.2 or len(missing) >= 3 or not v_dict):
                        vars_list = ", ".join(required_vars)
                        missing_list = ", ".join(missing)
                        return (
                            f"Error: Template '{target['name']}' requires template_vars but you missed some critical ones.\n"
                            f"Missing or empty variables: {missing_list}\n\n"
                            f"You MUST call this tool again with template_vars set to a JSON string containing "
                            f"ALL required keys populated with real, extensive content. DO NOT leave them empty.\n"
                            f"All required variables: {vars_list}\n"
                            f"If you have generated images, embed them inside the content variables using HTML like <img src=\"/api/images/FILENAME\">."
                        )
                    elif missing:
                        logger.warning(f"[DOCS] Template '{target['name']}' has unfilled variables: {missing}")

                rendered = render_template(target["id"], v_dict)
                final_html = rendered["body_html"]

            if not final_html:
                return "Error: Generated HTML is empty."
                
            # 1.b Resolve local image links for Playwright
            final_html = self._resolve_image_paths(final_html)

            # 1.c Auto-inject pagination CSS safety net
            final_html = self._inject_pagination_css(final_html)

            # Get generation defaults
            gen_html = True
            gen_pdf = True
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, "r", encoding="utf-8") as f:
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


# ── Module-level singleton (required by the Hecos plugin dispatcher) ──────────

tools = DocsTools()


def on_load(config):
    """Called by the plugin loader when the plugin is activated."""
    logger.debug("DOCS", "Document Maker plugin loaded.")
