import os
import uuid
import json
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

    def generate_pdf(self, html_content: str = None, template_id: str = None, template_vars: str = None, filename: str = None) -> str:
        """
        Generates a PDF from HTML content or a template.
        Uses the Playwright engine from browser_automation core module.
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

                v_dict = json.loads(template_vars) if template_vars else {}
                rendered = render_template(target["id"], v_dict)
                final_html = rendered["body_html"]

            if not final_html:
                return "Error: Generated HTML is empty."
                
            # 1.b Resolve local image links for Playwright
            # Convert <img src="file.png"> and background-image urls
            import re
            root_dir = os.path.dirname(os.path.dirname(self.plugin_dir))
            media_images_dir = os.path.join(root_dir, "media", "images")
            
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
                
                # Check for API paths
                elif path.startswith("/api/images/"):
                    filename = path.replace("/api/images/", "")
                    abs_path = os.path.join(media_images_dir, filename)
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
            final_html = re.sub(img_pattern, resolve_img_path, final_html)

            # Match background-image: url('filename.png')
            bg_pattern = r'(url\([\'"]?)(.*?)([\'"]?\))'
            final_html = re.sub(bg_pattern, resolve_img_path, final_html)

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
                    with open(html_output_path, "w", encoding="utf-8") as f:
                        f.write(final_html)
                    results.append(f"HTML: {html_output_path}")
                except Exception as e:
                    logger.error(f"[DOCS] Failed to save HTML: {e}")

            if gen_pdf:
                # 3. Call browser_automation engine
                try:
                    from hecos.modules.browser_automation.plugin import engine
                except ImportError:
                    return "Error: browser_automation core module is required for PDF generation."

                # Define the task to run on the browser thread
                def _pdf_task():
                    # Make sure browser is running. 
                    # Since we are on the browser thread, we can't call public engine.launch() which uses queue.
                    if not engine._state.get("browser") or not engine._state["browser"].is_connected():
                        # We must launch manually since engine._launch_internal() might be broken
                        from playwright.sync_api import sync_playwright
                        if not engine._state.get("pw_instance"):
                            engine._state["pw_instance"] = sync_playwright().start()
                        engine._state["browser"] = engine._state["pw_instance"].chromium.launch(headless=True)
                    
                    # Get the browser and create a new temporary page directly
                    browser = engine._state["browser"]
                    context = browser.new_context()
                    page = context.new_page()
                    
                    try:
                        import tempfile
                        temp_html_path = None
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as tmp:
                            tmp.write(final_html)
                            temp_html_path = tmp.name

                        # Use file:/// URL for the temp file to allow local file access
                        file_url = "file:///" + os.path.normpath(temp_html_path).replace("\\", "/")
                        page.goto(file_url, wait_until="networkidle")
                        
                        # Generate PDF with backgrounds and standard margins
                        page.pdf(path=pdf_output_path, format="A4", print_background=True)
                    finally:
                        if temp_html_path and os.path.exists(temp_html_path):
                            try:
                                os.remove(temp_html_path)
                            except Exception as e:
                                logger.error(f"[DOCS] Failed to delete temp HTML: {e}")
                        page.close()
                        context.close()
                    return pdf_output_path

                # Run the task on the dedicated browser thread
                result_path = engine._run_on_browser_thread(_pdf_task)
                
                logger.info(f"[DOCS] Generated PDF successfully at {result_path}")
                results.append(f"PDF: {result_path}")

            if not results:
                return "Error: Neither HTML nor PDF generation was enabled, or generation failed."

            return "\n".join(results)

        except Exception as e:
            logger.error(f"[DOCS] Failed to generate PDF: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return f"Error generating PDF: {str(e)}"


# ── Module-level singleton (required by the Hecos plugin dispatcher) ──────────

tools = DocsTools()


def on_load(config):
    """Called by the plugin loader when the plugin is activated."""
    logger.debug("DOCS", "Document Maker plugin loaded.")
