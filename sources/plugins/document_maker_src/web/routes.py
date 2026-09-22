"""
Autonomous routes for document_maker package.
Handles config persistence for the web UI.
"""
from flask import request, jsonify, send_from_directory, send_file
import os
import json

def init_plugin_routes(app, cfg_mgr, root_dir, logger, get_sm=None):
    plugin_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_file = os.path.join(plugin_path, "docs_config.json")

    def get_config():
        if os.path.exists(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[DOCS] Error reading config: {e}")
        return {"pdf_save_path": "media/documents"}

    def save_config(data):
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"[DOCS] Error writing config: {e}")
            return False

    @app.route("/hecos/api/plugins/document_maker/config", methods=["GET"])
    def get_docs_config_api():
        return jsonify(get_config())

    @app.route("/hecos/api/plugins/document_maker/config", methods=["POST"])
    def post_docs_config_api():
        try:
            incoming = request.get_json(force=True)
            if not isinstance(incoming, dict):
                return jsonify({"ok": False, "error": "Invalid payload"}), 400
            
            current_config = get_config()
            current_config.update(incoming)
            
            if save_config(current_config):
                return jsonify({"ok": True})
            return jsonify({"ok": False, "error": "Save failed"}), 500
        except Exception as exc:
            logger.error(f"[DOCS] POST config error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/hecos/api/plugins/document_maker/preview", methods=["GET"])
    def get_docs_preview():
        path = request.args.get("path")
        if not path or not os.path.exists(path):
            return jsonify({"ok": False, "error": "File not found"}), 404
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return jsonify({"ok": True, "html": content})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/hecos/api/plugins/document_maker/preview", methods=["POST"])
    def post_docs_preview():
        try:
            data = request.get_json(force=True)
            path = data.get("path")
            html = data.get("html")
            if not path or not html:
                return jsonify({"ok": False, "error": "Missing path or html"}), 400
                
            # Salva l'HTML
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
                
            # Rigenera il PDF (se la path e' un file html)
            if path.endswith(".html"):
                pdf_path = path[:-5] + ".pdf"
                from hecos.hpm.document_maker.main import DocsTools
                dt = DocsTools()
                processed_html = dt._resolve_image_paths(html)
                processed_html = dt._inject_pagination_css(processed_html)
                res = dt._generate_pdf_from_html(processed_html, pdf_path)
                if not res:
                    return jsonify({"ok": False, "error": "PDF regeneration failed (Playwright error)"}), 500
                    
            return jsonify({"ok": True})
        except Exception as e:
            logger.error(f"[DOCS] POST preview error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/hecos/api/plugins/document_maker/static/<path:filename>")
    def get_docs_static(filename):
        static_folder = os.path.join(plugin_path, "web", "static")
        return send_from_directory(static_folder, filename)

    @app.route("/docs/editor")
    def docs_visual_editor():
        """Serve the GrapeJS visual editor page."""
        editor_path = os.path.join(plugin_path, "web", "templates", "docs_editor.html")
        if os.path.exists(editor_path):
            return send_file(editor_path)
        return "Editor template not found", 404

    @app.route("/hecos/api/plugins/document_maker/file", methods=["GET"])
    def get_docs_file():
        """Read a document file and return its HTML content."""
        path = request.args.get("path")
        if not path or not os.path.exists(path):
            return jsonify({"ok": False, "error": "File not found"}), 404
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return jsonify({"ok": True, "html": content})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/hecos/api/plugins/document_maker/generate_pdf_from_html", methods=["POST"])
    def docs_generate_pdf_from_editor():
        """Save edited HTML and regenerate the PDF."""
        try:
            data = request.get_json(force=True)
            filepath = data.get("filepath")
            html = data.get("html")
            if not filepath or not html:
                return jsonify({"ok": False, "error": "Missing filepath or html"}), 400

            # Save the HTML
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"[DOCS] Editor saved HTML: {filepath}")

            # Regenerate PDF
            pdf_path = filepath.rsplit(".", 1)[0] + ".pdf"
            from hecos.hpm.document_maker.main import DocsTools
            dt = DocsTools()
            resolved_html = dt._resolve_image_paths(html)
            resolved_html = dt._inject_pagination_css(resolved_html)
            result = dt._generate_pdf_from_html(resolved_html, pdf_path)

            if result and os.path.exists(result):
                pdf_url = f"/api/local_file?path={os.path.normpath(result).replace(os.sep, '/')}"
                return jsonify({"ok": True, "pdf_url": pdf_url})
            else:
                return jsonify({"ok": False, "error": "PDF generation failed (Playwright unavailable)"}), 500
        except Exception as e:
            logger.error(f"[DOCS] Editor PDF generation error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
