"""
Hecos Playbooks - HPM Package API
"""

import logging
import traceback
from flask import render_template, jsonify, request
from flask_login import login_required

log = logging.getLogger("HecosPlaybooks.Routes")

def init_plugin_routes(app, cfg_mgr, hecos_root=None, logger=None, **kwargs):
    if hasattr(hecos_root, 'info'):
        logger = hecos_root
    _log = logger or log

    def _playbooks():
        try:
            from hecos.modules.playbooks.playbooks import storage
            return storage
        except ImportError:
            try:
                from hecos.hpm.playbooks import storage
                return storage
            except ImportError:
                from playbooks import storage
                return storage

    @app.route("/api/ext/presenter/playbooks", methods=["GET"])
    @login_required
    def api_playbooks_list():
        try:
            storage = _playbooks()
            return jsonify({"ok": True, "playbooks": storage.list_playbooks()})
        except Exception as e:
            _log.error(f"Error listing playbooks: {e}\n{traceback.format_exc()}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/ext/presenter/playbooks", methods=["POST"])
    @login_required
    def api_playbooks_create():
        try:
            storage = _playbooks()
            data = request.json or {}
            res = storage.create_playbook(
                name=data.get("name", "New Playbook"),
                description=data.get("description", ""),
                icon=data.get("icon", "fa-book-open")
            )
            return jsonify({"ok": True, "playbook": res})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/ext/presenter/playbooks/<playbook_id>", methods=["GET"])
    @login_required
    def api_playbooks_get(playbook_id):
        try:
            storage = _playbooks()
            pb = storage.get_playbook(playbook_id)
            if not pb:
                return jsonify({"ok": False, "error": "Playbook not found"}), 404
            return jsonify({"ok": True, "playbook": pb})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/ext/presenter/playbooks/<playbook_id>", methods=["PUT"])
    @login_required
    def api_playbooks_update(playbook_id):
        try:
            storage = _playbooks()
            data = request.json or {}
            res = storage.update_playbook(playbook_id, **data)
            return jsonify({"ok": True, "playbook": res})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/ext/presenter/playbooks/<playbook_id>", methods=["DELETE"])
    @login_required
    def api_playbooks_delete(playbook_id):
        try:
            storage = _playbooks()
            storage.delete_playbook(playbook_id)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/ext/presenter/playbooks/<playbook_id>/tabs", methods=["POST"])
    @login_required
    def api_playbooks_add_tab(playbook_id):
        try:
            storage = _playbooks()
            data = request.json or {}
            res = storage.add_tab(
                playbook_id=playbook_id,
                name=data.get("name", "New Tab"),
                content=data.get("content", "")
            )
            return jsonify({"ok": True, "tab": res})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/ext/presenter/playbooks/<playbook_id>/tabs/<tab_id>", methods=["PUT"])
    @login_required
    def api_playbooks_update_tab(playbook_id, tab_id):
        try:
            storage = _playbooks()
            data = request.json or {}
            res = storage.update_tab(playbook_id, tab_id, **data)
            return jsonify({"ok": True, "tab": res})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/ext/presenter/playbooks/<playbook_id>/tabs/<tab_id>", methods=["DELETE"])
    @login_required
    def api_playbooks_delete_tab(playbook_id, tab_id):
        try:
            storage = _playbooks()
            storage.delete_tab(playbook_id, tab_id)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/ext/presenter/playbooks/<playbook_id>/reorder", methods=["POST"])
    @login_required
    def api_playbooks_reorder(playbook_id):
        try:
            storage = _playbooks()
            data = request.json or {}
            ordered_ids = data.get("ordered_ids", [])
            storage.reorder_tabs(playbook_id, ordered_ids)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/ext/presenter/playbooks/context", methods=["GET"])
    @login_required
    def api_playbooks_context():
        try:
            storage = _playbooks()
            tokens = int(request.args.get("max_tokens", 2000))
            ctx = storage.get_active_playbook_context(max_tokens=tokens)
            return jsonify({"ok": True, "context": ctx, "approx_tokens": len(ctx) // 4})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/ext/presenter/playbooks/template", methods=["POST"])
    @login_required
    def api_playbooks_template():
        try:
            storage = _playbooks()
            data = request.json or {}
            tpl_type = data.get("template", "english")
            
            if tpl_type == "english":
                pb = storage.create_playbook("English Teacher & Coach", "Educational training material, grammar rules, and conversational scenarios for English learning.", "fa-graduation-cap")
                pid = pb["meta"]["id"]
                storage.add_tab(pid, "Grammar Rules", "DIRECTIVES:\n- You are an expert and supportive English teacher.\n- Analyze the student's grammar, vocabulary usage, and flow.\n- Whenever an error occurs, provide a gentle correction and an explanation with 2 examples.\n- Reinforce active vocabulary and natural idioms.")
                storage.add_tab(pid, "Roleplay Scenarios", "SCENARIO 1: Coffee Shop in London\nYou are a barista at a specialty cafe. Prompt the customer politely, suggest pastries, and engage in warm small talk.\n\nSCENARIO 2: Job Interview\nYou are the hiring manager interviewing a candidate for a technical project lead role. Ask about teamwork and handling difficult deadlines.")
            elif tpl_type == "sales":
                pb = storage.create_playbook("Sales Masterclass", "Sales methodologies, objection handling frameworks, and persuasion guidelines.", "fa-chart-line")
                pid = pb["meta"]["id"]
                storage.add_tab(pid, "Objection Handling", "OBJECTION: 'Your solution is too expensive.'\nRESPONSE: Reframe value: 'I understand budget is crucial. Many of our current partners initially felt the same until they saw how much manual time was saved within the first 30 days. Let\\'s look at the ROI breakdown.'\n\nOBJECTION: 'We need more time to think.'\nRESPONSE: Uncover the real friction: 'Totally understand. To help you reflect, what specific question or concern is top of mind right now?'")
                storage.add_tab(pid, "Power Words & Rules", "RULES:\n- Never say 'To be honest' or 'Cheap'.\n- Use high-impact terms: 'Scalable', 'Proven', 'Empower', 'Streamlined', 'Predictable results'.\n- Focus on outcomes, not features.")
            else:
                pb = storage.create_playbook("Custom Directives", "Custom behavioral guidelines, domain knowledge, and reference instructions for the Presenter.", "fa-book-open")
                pid = pb["meta"]["id"]
                storage.add_tab(pid, "Knowledge Base", "# Custom Directives\nEnter reference guidelines, teaching material, or roleplay scripts for the Presenter here.")

            return jsonify({"ok": True, "playbook": pb})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
