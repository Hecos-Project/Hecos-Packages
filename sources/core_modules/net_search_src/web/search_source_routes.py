"""
web/search_source_routes.py
Dedicated Flask API routes for automated & manual search engine compilation sources
(JSON, CSV, YAML, SQLite, OpenSearch XML, GitHub, and Tor .onion lists).
"""
from __future__ import annotations

import json
import logging
from flask import Response, jsonify, request
from flask_login import login_required

try:
    from hecos.modules.net_search.search.config import get_search_config, update_search_config
    from hecos.modules.net_search.search.endpoints_config import get_endpoints
    from hecos.modules.net_search.search.sources import (
        add_or_update_source,
        get_preset_sources,
        import_raw_content,
        list_sources,
        preview_ad_hoc_source,
        remove_source,
        sync_all_sources,
        sync_source,
        toggle_source,
    )
    from hecos.modules.net_search.search.sources.domain_store import (
        get_summary as get_domain_summary,
        set_source_role,
    )
except (ImportError, ValueError):
    from ..search.config import get_search_config, update_search_config
    from ..search.endpoints_config import get_endpoints
    from ..search.sources import (
        add_or_update_source,
        get_preset_sources,
        import_raw_content,
        list_sources,
        preview_ad_hoc_source,
        remove_source,
        sync_all_sources,
        sync_source,
        toggle_source,
    )
    from ..search.sources.domain_store import (
        get_summary as get_domain_summary,
        set_source_role,
    )

try:
    from hecos.core.logging import logger as hecos_logger
except (ImportError, ValueError):
    hecos_logger = logging.getLogger("net_search.web.sources")


def register_source_routes(app, logger=None):
    """Registers compilation source ingestion and sync routes on the Flask app."""
    if "api_search_sources_list" in app.view_functions:
        return
    log = logger or hecos_logger
    log.info("[DeepSearch] Registering automated source compilation routes...")

    @app.route("/api/hsearch/sources", methods=["GET"])
    @login_required
    def api_search_sources_list():
        cfg = get_search_config()
        return jsonify({
            "ok": True,
            "sources": list_sources(),
            "presets": get_preset_sources(),
            "auto_update_enabled": bool(cfg.get("sources_auto_update", True)),
            "domain_summary": get_domain_summary(),
        })

    @app.route("/api/hsearch/domains/role", methods=["POST"])
    @login_required
    def api_search_domains_role():
        """Switch a domain compilation source's active SQLite role (directory | blocklist | allowlist)."""
        data = request.get_json(force=True) or {}
        source_id = str(data.get("source_id") or "").strip()
        role = str(data.get("role") or "").strip().lower()
        if not source_id or role not in ("directory", "blocklist", "allowlist"):
            return jsonify({"ok": False, "error": "Invalid source_id or role"}), 400
        existing = next((s for s in list_sources() if s.get("id") == source_id), None)
        if not existing:
            return jsonify({"ok": False, "error": "Source not found"}), 404
        source = add_or_update_source({"id": source_id, "target_pool": f"domain_{role}"})
        count = set_source_role(source_id, role)
        return jsonify({
            "ok": True,
            "source_id": source_id,
            "role": role,
            "count": count,
            "source": source,
            "domain_summary": get_domain_summary(),
        })

    @app.route("/api/hsearch/sources", methods=["POST"])
    @login_required
    def api_search_sources_save():
        data = request.get_json(force=True) or {}
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "Invalid JSON payload"}), 400
        if not str(data.get("location") or "").strip() and not data.get("id"):
            return jsonify({"ok": False, "error": "Source URL or file path is required"}), 400

        source = add_or_update_source(data)
        tpool = source.get("target_pool", "auto")
        if tpool in ("domain_blocklist", "domain_allowlist", "domain_directory"):
            set_source_role(source["id"], tpool.replace("domain_", "", 1))

        sync_res = None
        if data.get("sync_now", True) and source.get("enabled", True):
            sync_res = sync_source(source["id"], force=bool(data.get("force", True)))
            source = sync_res.get("source") or source

        return jsonify({
            "ok": True,
            "source": source,
            "sync": sync_res,
            "domain_summary": get_domain_summary(),
        })

    @app.route("/api/hsearch/sources/settings", methods=["POST"])
    @login_required
    def api_search_sources_settings():
        data = request.get_json(force=True) or {}
        if "auto_update_enabled" in data:
            ok = update_search_config({"sources_auto_update": bool(data["auto_update_enabled"])})
            return jsonify({"ok": ok})
        return jsonify({"ok": False, "error": "No valid settings supplied"}), 400

    @app.route("/api/hsearch/sources/<source_id>", methods=["DELETE"])
    @login_required
    def api_search_sources_delete(source_id: str):
        res = remove_source(source_id)
        code = 200 if res.get("ok") else 404
        log.info(f"[DeepSearch] Source delete id={source_id} -> ok={res.get('ok')}")
        return jsonify(res), code

    @app.route("/api/hsearch/sources/<source_id>/toggle", methods=["POST"])
    @login_required
    def api_search_sources_toggle(source_id: str):
        data = request.get_json(silent=True) or {}
        enabled = data.get("enabled") if "enabled" in data else None
        res = toggle_source(source_id, enabled=enabled)
        code = 200 if res.get("ok") else 404
        log.info(f"[DeepSearch] Source toggle id={source_id} enabled={res.get('enabled')} -> ok={res.get('ok')}")
        return jsonify(res), code

    @app.route("/api/hsearch/sources/<source_id>/sync", methods=["POST"])
    @login_required
    def api_search_sources_sync_one(source_id: str):
        data = request.get_json(silent=True) or {}
        dry_run = bool(data.get("dry_run", False))
        res = sync_source(
            source_id,
            force=bool(data.get("force", True)),
            dry_run=dry_run,
        )
        log.info(
            f"[DeepSearch] Source sync id={source_id} dry_run={dry_run} -> ok={res.get('ok')} "
            f"added={res.get('added', 0)} error={res.get('error', '')}"
        )
        return jsonify(res)

    @app.route("/api/hsearch/sources/sync_all", methods=["POST"])
    @login_required
    def api_search_sources_sync_all():
        data = request.get_json(silent=True) or {}
        res = sync_all_sources(force=bool(data.get("force", False)), only_due=False)
        log.info(f"[DeepSearch] Source sync_all -> ok={res.get('ok')} synced={res.get('synced', 0)}")
        return jsonify(res)

    @app.route("/api/hsearch/sources/preview", methods=["POST"])
    @login_required
    def api_search_sources_preview():
        if request.files and "file" in request.files:
            up = request.files["file"]
            raw_bytes = up.read()
            fmt = request.form.get("format", "auto")
            target_pool = request.form.get("target_pool", "auto")
            res = import_raw_content(
                raw_bytes,
                fmt=fmt,
                filename=up.filename or "",
                target_pool=target_pool,
                dry_run=True,
            )
            return jsonify(res)

        data = request.get_json(force=True) or {}
        if data.get("content"):
            res = import_raw_content(
                data["content"],
                fmt=data.get("format", "auto"),
                filename=data.get("filename", ""),
                target_pool=data.get("target_pool", "auto"),
                dry_run=True,
            )
            return jsonify(res)

        location = str(data.get("location") or "").strip()
        if not location:
            return jsonify({"ok": False, "error": "Location or content required for preview"}), 400
        res = preview_ad_hoc_source(
            location=location,
            fmt=data.get("format", "auto"),
            target_pool=data.get("target_pool", "auto"),
            use_tor=bool(data.get("use_tor", False)),
        )
        return jsonify(res)

    @app.route("/api/hsearch/sources/import", methods=["POST"])
    @login_required
    def api_search_sources_import():
        try:
            if request.files and "file" in request.files:
                up = request.files["file"]
                raw_bytes = up.read()
                fmt = request.form.get("format", "auto")
                target_pool = request.form.get("target_pool", "auto")
                source_name = request.form.get("name") or up.filename or "File Import"
                dry_run = str(request.form.get("dry_run", "")).lower() in ("1", "true", "yes")
                res = import_raw_content(
                    raw_bytes,
                    fmt=fmt,
                    filename=up.filename or "",
                    target_pool=target_pool,
                    source_name=source_name,
                    dry_run=dry_run,
                )
                log.info(
                    f"[DeepSearch] File import name={source_name} fmt={fmt} pool={target_pool} "
                    f"dry_run={dry_run} -> ok={res.get('ok')} stats={res.get('stats')}"
                )
                return jsonify(res)

            data = request.get_json(force=True) or {}
            content = data.get("content", "")
            if not content:
                return jsonify({"ok": False, "error": "No file or content provided"}), 400
            res = import_raw_content(
                content,
                fmt=data.get("format", "auto"),
                filename=data.get("filename", ""),
                target_pool=data.get("target_pool", "auto"),
                source_name=data.get("name") or "Manual Import",
                dry_run=bool(data.get("dry_run", False)),
            )
            log.info(f"[DeepSearch] Manual import -> ok={res.get('ok')} stats={res.get('stats')}")
            return jsonify(res)
        except Exception as e:
            log.exception(f"[DeepSearch] Source import failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 400

    # ── Compatibility Routes Referenced by Search Dashboard Modals ────────────
    @app.route("/api/hsearch/engines/import", methods=["POST"])
    @login_required
    def api_search_engines_import():
        try:
            data = request.get_json(force=True) or {}
            content = data.get("content", "")
            if not content:
                return jsonify({"ok": False, "error": "Empty import content"}), 400
            res = import_raw_content(
                content,
                fmt=data.get("format", "auto"),
                target_pool=data.get("target_pool", "auto"),
                source_name="Dashboard Import",
                dry_run=False,
            )
            st = res.get("stats") or {}
            total_eng = len(get_endpoints().get("searxng", {}).get("engines", []))
            log.info(f"[DeepSearch] Engines import -> ok={res.get('ok')} added={st.get('added', 0)} total_engines={total_eng}")
            return jsonify({
                "ok": bool(res.get("ok")),
                "added": st.get("added", 0),
                "updated": 0,
                "skipped_duplicates": st.get("skipped_duplicates", 0),
                "total_engines": total_eng,
                "stats": st,
            })
        except Exception as e:
            log.exception(f"[DeepSearch] Engines import failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 400

    @app.route("/api/hsearch/engines/export", methods=["GET"])
    @login_required
    def api_search_engines_export():
        endpoints = get_endpoints()
        payload = json.dumps({"endpoints": endpoints, "sources": list_sources()}, indent=2, ensure_ascii=False)
        return Response(
            payload,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=hecos_netsearch_endpoints.json"},
        )

    @app.route("/api/hsearch/engines/sync", methods=["POST"])
    @login_required
    def api_search_engines_sync():
        try:
            try:
                from hecos.modules.net_search.search.components.searxng_component import update_searxng_engines
            except (ImportError, ValueError):
                from ..search.components.searxng_component import update_searxng_engines
            engines = get_endpoints().get("searxng", {}).get("engines", [])
            ok = update_searxng_engines(engines)
            return jsonify({"ok": ok, "total_synced": len(engines)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

