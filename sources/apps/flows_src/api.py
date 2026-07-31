"""
Hecos Flows — HPM Package API
================================
Flask routes for the Flows System App.
Wrapped as an HPM plugin entry point: init_plugin_routes(app, cfg_mgr).

All imports from hecos.modules.flows.* are now redirected to
the package's own core_logic module (installed by HPM into hpm/flows/).
"""

import logging
import time
import json

log = logging.getLogger("HecosFlows.Routes")


def init_plugin_routes(app, cfg_mgr, hecos_root=None, logger=None, **kwargs):
    """HPM entry point — register all /flows routes on the Flask app."""
    # If logger is not provided but hecos_root was a logger by mistake (backward compat)
    if hasattr(hecos_root, 'info'):
        logger = hecos_root
    _log = logger or log

    from flask import render_template, jsonify, request, Response, stream_with_context
    from flask_login import login_required, current_user

    # ── Helpers to import from the installed package core_logic ──────────────
    def _flows():
        """Lazy import of the flows core_logic module."""
        try:
            from hecos.modules.flows.core_logic import storage, engine, validator, compiler, registry
            return storage, engine, validator, compiler, registry
        except ImportError:
            # Fallback: still-resident hecos.modules.flows (transition period)
            from hecos.modules import flows as _f_pkg
            from hecos.modules.flows.core_logic import storage, engine, validator, compiler, registry
            return storage, engine, validator, compiler, registry

    # ── Page ─────────────────────────────────────────────────────────────────

    @app.route("/flows")
    @login_required
    def flows_page():
        from hecos.core.i18n.translator import get_translator
        zconfig_data = cfg_mgr.reload()
        translations = get_translator().get_translations()
        return render_template("flows.html", zconfig=zconfig_data, translations=translations)

    # ── REST API ──────────────────────────────────────────────────────────────

    @app.route("/api/flows/list", methods=["GET"])
    @login_required
    def api_flows_list():
        try:
            storage, *_ = _flows()
            return jsonify({"ok": True, "flows": storage.list_flows()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/<flow_id>", methods=["GET"])
    @login_required
    def api_flows_get(flow_id):
        try:
            storage, *_ = _flows()
            data   = storage.get_flow(flow_id)
            yaml_t = storage.get_flow_yaml(flow_id)
            if data is None:
                return jsonify({"ok": False, "error": f"Flow '{flow_id}' not found."}), 404
            return jsonify({"ok": True, "flow": data, "yaml": yaml_t})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/save", methods=["POST"])
    @login_required
    def api_flows_save():
        try:
            payload = request.get_json(force=True)
            yaml_text = payload.get("yaml", "")
            if not yaml_text.strip():
                return jsonify({"ok": False, "error": "Empty YAML."}), 400
            storage, engine, validator, *_ = _flows()
            is_valid, errors, flow_dict = validator.validate_yaml_string(yaml_text)
            if not is_valid:
                return jsonify({"ok": False, "errors": errors}), 422
            flow_id = storage.save_flow(flow_dict, raw_yaml=yaml_text)
            engine.schedule_flow(flow_dict)
            return jsonify({"ok": True, "flow_id": flow_id})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/<flow_id>", methods=["DELETE"])
    @login_required
    def api_flows_delete(flow_id):
        try:
            storage, engine, *_ = _flows()
            engine.unschedule_flow(flow_id)
            ok = storage.delete_flow(flow_id)
            if not ok:
                return jsonify({"ok": False, "error": f"Flow '{flow_id}' not found."}), 404
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/<flow_id>/run", methods=["POST"])
    @login_required
    def api_flows_run(flow_id):
        try:
            storage, engine, *_ = _flows()
            existing = engine.get_active_run(flow_id)
            if existing:
                return jsonify({"ok": False, "error": "already_running", "run_id": existing}), 409
            flow_data = storage.get_flow(flow_id)
            if flow_data is None:
                return jsonify({"ok": False, "error": f"Flow '{flow_id}' not found."}), 404
            pipeline = flow_data.get("pipeline", [])
            start_nodes = [n for n in pipeline if n.get("action") == "CONTROL__start"]
            if not start_nodes:
                return jsonify({"ok": False, "error": "Flow cannot start: missing CONTROL__start node."}), 400
            all_disabled = all(
                n.get("disabled", False) and n.get("disable_mode", "skip") == "stop"
                for n in start_nodes
            )
            if all_disabled:
                return jsonify({"ok": False, "error": "Flow cannot start: CONTROL__start node is stopped."}), 400
            run_id = engine.run_flow_async(flow_data)
            return jsonify({"ok": True, "run_id": run_id})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/<flow_id>/stop", methods=["POST"])
    @login_required
    def api_flows_stop(flow_id):
        try:
            storage, engine, *_ = _flows()
            run_id = engine.get_active_run(flow_id)
            if not run_id:
                return jsonify({"ok": False, "error": "not_running"}), 404
            engine.abort_run(run_id)
            return jsonify({"ok": True, "run_id": run_id})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/run/<run_id>/input", methods=["POST"])
    @login_required
    def api_flows_deliver_input(run_id):
        try:
            storage, engine, *_ = _flows()
            payload = request.get_json(force=True)
            text = str(payload.get("text", "")).strip()
            if not text:
                return jsonify({"ok": False, "error": "Empty input."}), 400
            ok = engine.deliver_user_input(run_id, text)
            if not ok:
                return jsonify({"ok": False, "error": "No flow waiting for input with that run_id."}), 404
            return jsonify({"ok": True, "run_id": run_id})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/pending_inputs", methods=["GET"])
    @login_required
    def api_flows_pending_inputs():
        try:
            storage, engine, *_ = _flows()
            return jsonify({"ok": True, "pending": engine.get_all_pending_input_runs()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/<flow_id>/status", methods=["GET"])
    @login_required
    def api_flows_status(flow_id):
        try:
            storage, engine, *_ = _flows()
            run_id = engine.get_active_run(flow_id)
            return jsonify({"ok": True, "running": run_id is not None, "run_id": run_id})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/running", methods=["GET"])
    @login_required
    def api_flows_all_running():
        try:
            storage, engine, *_ = _flows()
            return jsonify({"ok": True, "running": engine.get_all_active_runs()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/<flow_id>/enable", methods=["POST"])
    @login_required
    def api_flows_enable(flow_id):
        try:
            storage, engine, *_ = _flows()
            if not storage.update_flow_field(flow_id, "enabled", True):
                return jsonify({"ok": False, "error": "Not found."}), 404
            flow_data = storage.get_flow(flow_id)
            if flow_data:
                engine.schedule_flow(flow_data)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/<flow_id>/disable", methods=["POST"])
    @login_required
    def api_flows_disable(flow_id):
        try:
            storage, engine, *_ = _flows()
            if not storage.update_flow_field(flow_id, "enabled", False):
                return jsonify({"ok": False, "error": "Not found."}), 404
            engine.unschedule_flow(flow_id)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/compile", methods=["POST"])
    @login_required
    def api_flows_compile():
        try:
            payload     = request.get_json(force=True)
            description = payload.get("description", "").strip()
            flow_name   = payload.get("flow_name", "").strip() or None
            if not description:
                return jsonify({"ok": False, "error": "No description provided."}), 400
            storage, engine, validator, compiler, *_ = _flows()
            yaml_text, summary, flow_dict = compiler.compile_from_nlp(
                description=description,
                flow_name=flow_name,
                config=cfg_mgr.reload(),
            )
            return jsonify({"ok": True, "yaml": yaml_text, "summary": summary, "flow": flow_dict})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/validate", methods=["POST"])
    @login_required
    def api_flows_validate():
        try:
            payload   = request.get_json(force=True)
            yaml_text = payload.get("yaml", "")
            storage, engine, validator, *_ = _flows()
            is_valid, errors, _ = validator.validate_yaml_string(yaml_text)
            return jsonify({"ok": True, "valid": is_valid, "errors": errors})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/actions/catalog", methods=["GET"])
    @login_required
    def api_flows_catalog():
        try:
            storage, engine, validator, compiler, registry = _flows()
            registry._auto_register_hecos_modules()
            return jsonify({"ok": True, "catalog": registry.get_catalog()})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/variables", methods=["GET"])
    @login_required
    def api_flows_variables():
        try:
            import os
            storage, *_ = _flows()
            flows_dir = storage._get_flows_dir()
            variables = set()
            for fname in sorted(os.listdir(flows_dir)):
                if not fname.endswith(".yaml"):
                    continue
                try:
                    data = storage._load_yaml_file(os.path.join(flows_dir, fname))
                    for node in data.get("pipeline", []):
                        out_as = node.get("output_as")
                        if out_as and isinstance(out_as, str):
                            variables.add(out_as.strip())
                except Exception:
                    pass
            return jsonify({"ok": True, "variables": sorted(list(variables))})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # ── SSE: Real-time execution log ─────────────────────────────────────────

    @app.route("/api/flows/<flow_id>/log/stream", methods=["GET"])
    @login_required
    def api_flows_log_stream(flow_id):
        storage, engine, *_ = _flows()
        run_id = request.args.get("run_id", "latest")
        bus    = engine.get_event_bus()
        queue  = bus.subscribe(run_id)

        def _generate():
            try:
                yield f"data: {json.dumps({'type': 'connected', 'run_id': run_id})}\n\n"
                timeout = time.time() + 300
                while time.time() < timeout:
                    while queue:
                        event = queue.pop(0)
                        yield f"data: {json.dumps(event)}\n\n"
                        if event.get("type") == "stream_end":
                            return
                    time.sleep(0.15)
                yield f"data: {json.dumps({'type': 'timeout'})}\n\n"
            finally:
                bus.unsubscribe(run_id)

        return Response(
            stream_with_context(_generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── Backup / Restore ─────────────────────────────────────────────────────

    @app.route("/api/flows/backup", methods=["GET"])
    def api_flows_backup():
        if not current_user.is_authenticated and request.headers.get("X-Hecos-Internal") != "backup":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        try:
            storage, *_ = _flows()
            summaries = storage.list_flows()
            bundle = [
                {"id": s["id"], "name": s["name"], "yaml": storage.get_flow_yaml(s["id"])}
                for s in summaries if storage.get_flow_yaml(s["id"]) is not None
            ]
            return jsonify({"ok": True, "flows": bundle, "count": len(bundle)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/flows/restore", methods=["POST"])
    def api_flows_restore():
        if not current_user.is_authenticated and request.headers.get("X-Hecos-Internal") != "backup":
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        try:
            import yaml as _yaml
            storage, *_ = _flows()
            data   = request.get_json(force=True) or {}
            bundle = data.get("flows", [])
            mode   = data.get("mode", "merge")
            if not isinstance(bundle, list):
                return jsonify({"ok": False, "error": "Invalid format: expected list of flows"}), 400
            if mode == "replace":
                for existing in storage.list_flows():
                    storage.delete_flow(existing["id"])
            imported = skipped = 0
            for entry in bundle:
                flow_id   = entry.get("id", "").strip()
                yaml_text = entry.get("yaml", "").strip()
                if not flow_id or not yaml_text:
                    continue
                if mode == "merge" and storage.get_flow(flow_id) is not None:
                    skipped += 1
                    continue
                try:
                    parsed = _yaml.safe_load(yaml_text)
                    if not isinstance(parsed, dict):
                        continue
                    parsed["id"] = flow_id
                    storage.save_flow(parsed, raw_yaml=yaml_text)
                    imported += 1
                except Exception as exc:
                    log.warning(f"[Flows.Restore] Failed to import flow '{flow_id}': {exc}")
            return jsonify({"ok": True, "imported": imported, "skipped": skipped}), 201
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    _log.info("[Flows HPM] Routes registered.")
