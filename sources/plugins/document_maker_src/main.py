import os
import uuid
import json
import re
import random
from hecos.core.logging import logger
from hecos.app.config import ConfigManager

from .layout_engine import (
    get_save_dir,
    get_layout_config,
    resolve_image_paths,
    detect_background_color,
    is_dark_color,
    inject_pagination_css,
    adapt_gallery_photos,
)
from .pdf_renderer import (
    generate_pdf_from_html,
    generate_pdf_fallback,
    calculate_layout_issues,
)
from .doc_modifier import (
    resolve_document_path,
    modify_document_content,
)
from .doc_explorer import (
    list_images,
    list_documents,
)


class DocsTools:
    def __init__(self):
        self.config = ConfigManager().config
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_file = os.path.join(self.plugin_dir, "docs_config.json")

    def _get_save_dir(self):
        return get_save_dir(self.plugin_dir, self.config_file)

    def _get_layout_config(self):
        return get_layout_config(self.config_file)

    def _resolve_image_paths(self, html_content: str) -> str:
        return resolve_image_paths(self.plugin_dir, html_content)

    def _generate_pdf_from_html(self, final_html: str, pdf_output_path: str) -> str:
        layout = self._get_layout_config()
        return generate_pdf_from_html(final_html, pdf_output_path, layout)

    def _generate_pdf_fallback(self, final_html: str, pdf_output_path: str) -> str:
        layout = self._get_layout_config()
        return generate_pdf_fallback(final_html, pdf_output_path, layout)

    def _detect_background_color(self, html: str) -> str:
        return detect_background_color(html)

    def _is_dark_color(self, color_str: str) -> bool:
        return is_dark_color(color_str)

    def _inject_pagination_css(self, html: str) -> str:
        layout = self._get_layout_config()
        return inject_pagination_css(html, layout)

    def _adapt_gallery_photos(self, html: str, v_dict: dict, default_photo_count: int = 0) -> str:
        return adapt_gallery_photos(html, v_dict, default_photo_count)

    def list_images(self, folder: str = "", limit: int = 10, sort: str = "recent", random_pick: bool = False) -> str:
        return list_images(self.plugin_dir, folder, limit, sort, random_pick)

    DOCS__list_images = list_images

    def list_documents(self, search: str = "") -> str:
        output_dir = self._get_save_dir()
        return list_documents(output_dir, search)

    DOCS__list_documents = list_documents

    def _resolve_document_path(self, file_path: str) -> str:
        output_dir = self._get_save_dir()
        return resolve_document_path(file_path, output_dir)

    def modify_document(self, file_path: str, operation: str, content: str, target_selector: str = "") -> str:
        """
        Modifies an existing HTML document in media/documents and auto-regenerates its PDF.
        """
        try:
            resolved_path = self._resolve_document_path(file_path)
            if not resolved_path:
                return f"Error: Document not found: '{file_path}'. Use list_documents to see available files."

            with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
                original_html = f.read()

            modified_html, err = modify_document_content(original_html, operation, content, target_selector)
            if err:
                return err

            if modified_html == original_html:
                return "Warning: No changes were made to the document. The target may not have been found."

            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(modified_html)
            logger.info(f"[DOCS] Document modified: {resolved_path}")

            results = [
                f"✅ Document modified successfully: {resolved_path}",
                f"HTML: {resolved_path}"
            ]

            pdf_path = resolved_path.rsplit(".", 1)[0] + ".pdf"
            resolved_for_pdf = self._resolve_image_paths(modified_html)
            pdf_result = self._generate_pdf_from_html(resolved_for_pdf, pdf_path)
            if pdf_result and os.path.exists(pdf_result):
                results.append(f"✅ PDF regenerated: {pdf_result}")
                results.append(f"PDF: {pdf_result}")
            else:
                results.append("⚠️ PDF regeneration failed (Playwright unavailable). HTML was updated successfully.")

            return "\n".join(results)

        except Exception as e:
            logger.error(f"[DOCS] Failed to modify document: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return f"Error modifying document: {e}"

    DOCS__modify_document = modify_document

    def DOCS__optimize_layout(self, document_id: str) -> str:
        """
        Calculates page breaks for a document and returns a report of elements split across pages.
        """
        output_dir = self._get_save_dir()
        if not document_id.endswith(".html"):
            document_id += ".html"
        
        file_path = os.path.join(output_dir, document_id)
        if not os.path.exists(file_path):
            file_path = self._resolve_document_path(document_id)
            if not file_path:
                return f"Error: Document {document_id} not found."
                
        return calculate_layout_issues(file_path)

    optimize_layout = DOCS__optimize_layout

    def generate_pdf(self, html_content: str = None, template_id: str = None, template_vars: str = None, filename: str = None) -> str:
        """
        Generates a document (HTML + PDF) from raw HTML content or a template.
        """
        config_data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8-sig") as f:
                    config_data = json.load(f)
            except Exception as e:
                logger.error(f"[DOCS] Failed to read config: {e}")

        default_tpl = config_data.get("default_template_id", "").strip()
        force_default_tpl = config_data.get("force_default_template", False)

        if template_id and template_id.lower() in ("default", "predefinito"):
            template_id = default_tpl

        if not template_id and default_tpl:
            if force_default_tpl or template_vars or not html_content:
                template_id = default_tpl

        if not html_content and not template_id:
            return "Error: You must provide either html_content or template_id."

        try:
            final_html = html_content

            if template_id:
                from hecos.hpm.libraries.templates.store import list_templates, render_template, get_template
                all_tpls = list_templates()
                target = None

                for t in all_tpls:
                    if t["id"] == template_id or t["name"].lower() == template_id.lower():
                        target = t
                        break

                if not target:
                    clean_query = template_id.lower().replace("_", " ").replace("-", " ")
                    query_words = clean_query.split()
                    for t in all_tpls:
                        t_name_lower = t["name"].lower()
                        t_id_lower = t["id"].lower()
                        if all(w in t_name_lower or w in t_id_lower for w in query_words):
                            target = t
                            break

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

                for k, v in list(v_dict.items()):
                    if isinstance(v, str):
                        if re.search(r'^(?:img|image|foto|photo)\d*$', k, re.IGNORECASE) or k.lower().startswith('img'):
                            m_src = re.search(r'src=["\']([^"\']+)["\']', v)
                            if m_src:
                                v_dict[k] = m_src.group(1)

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

                for k in list(v_dict.keys()):
                    val = str(v_dict[k]).strip().lower()
                    if val in ("random", "casual", "a caso", "/api/images/random", "random.png"):
                        if existing_imgs_pool:
                            pick = random.choice(existing_imgs_pool)
                            v_dict[k] = f"/api/images/{os.path.basename(pick)}"
                    elif val in ("latest", "recent", "/api/images/latest", "latest.png"):
                        if existing_imgs_pool:
                            v_dict[k] = f"/api/images/{os.path.basename(existing_imgs_pool[0])}"

                tpl_img_keys = [v for v in required_vars if re.search(r'^(?:img|image|foto|photo)\d*$', v, re.IGNORECASE) or v.startswith('img')]
                provided_imgs = [v_dict[k] for k in tpl_img_keys if k in v_dict and str(v_dict[k]).strip()]
                if not provided_imgs:
                    provided_imgs = [str(v) for v in v_dict.values() if isinstance(v, str) and '/api/images/' in v]

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

                if required_vars:
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
                
            if 'v_dict' in locals() and v_dict:
                final_html = self._adapt_gallery_photos(final_html, v_dict, config_data.get("default_photo_count", 0))

            final_html = self._resolve_image_paths(final_html)
            final_html = self._inject_pagination_css(final_html)

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

            if not filename:
                filename = f"document_{uuid.uuid4().hex[:8]}"
            else:
                filename = os.path.basename(str(filename).strip())
                if filename.lower().endswith(".pdf") or filename.lower().endswith(".html"):
                    filename = filename.rsplit(".", 1)[0]
            
            output_dir = self._get_save_dir()
            pdf_output_path = os.path.join(output_dir, filename + ".pdf")
            html_output_path = os.path.join(output_dir, filename + ".html")

            results = []

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

    pdf = generate_pdf
    DOCS__generate_pdf = generate_pdf


tools = DocsTools()


def on_load(config):
    """Called by the plugin loader when the plugin is activated."""
    logger.debug("DOCS", "Document Maker plugin loaded.")
