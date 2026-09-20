"""
Autonomous routes for document_maker package.
Handles config persistence for the web UI.
"""
from flask import request, jsonify
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

    @app.route("/docs/editor")
    def docs_editor_view():
        from flask import render_template_string
        template_path = os.path.join(plugin_path, "web", "templates", "docs_editor.html")
        if not os.path.exists(template_path):
            return "Editor template not found", 404
        with open(template_path, "r", encoding="utf-8") as f:
            return render_template_string(f.read())

    @app.route("/hecos/api/plugins/document_maker/file", methods=["GET"])
    def get_docs_file_api():
        file_path = request.args.get("path")
        if not file_path:
            return jsonify({"ok": False, "error": "Missing path"}), 400
        # Prevent directory traversal
        if ".." in file_path:
            return jsonify({"ok": False, "error": "Invalid path"}), 400
        
        abs_path = os.path.join(root_dir, file_path)
        if not os.path.exists(abs_path):
            return jsonify({"ok": False, "error": "File not found"}), 404
            
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
            return jsonify({"ok": True, "html": content})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/hecos/api/plugins/document_maker/generate_pdf_from_html", methods=["POST"])
    def post_generate_pdf_from_html():
        try:
            incoming = request.get_json(force=True)
            file_path = incoming.get("filepath")
            html_content = incoming.get("html")
            
            if not file_path or not html_content:
                return jsonify({"ok": False, "error": "Missing filepath or html"}), 400
                
            abs_path = os.path.join(root_dir, file_path)
            
            # Save the updated HTML
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            # Call DocsTools to generate PDF
            import sys
            if root_dir not in sys.path:
                sys.path.insert(0, root_dir)
            from hecos.hpm.document_maker.main import DocsTools
            
            docs_tool = DocsTools()
            pdf_path = docs_tool.generate_pdf(html_content=html_content, filename=os.path.basename(abs_path).replace(".html", ".pdf"))
            
            if pdf_path and pdf_path != "None":
                # Convert absolute path to relative URL
                rel_url = pdf_path.replace(root_dir, "").replace("\\", "/")
                if not rel_url.startswith("/"):
                    rel_url = "/" + rel_url
                return jsonify({"ok": True, "pdf_url": rel_url})
            else:
                return jsonify({"ok": False, "error": "Playwright generation failed"}), 500
                
        except Exception as exc:
            logger.error(f"[DOCS] Visual Editor Generate Error: {exc}")
            return jsonify({"ok": False, "error": str(exc)}), 500
