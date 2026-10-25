"""
Hecos Document Reader — Main Plugin Entry Point (main.py)
Provides LLM tools and HDCS Direct Slash Commands for opening documents in the browser reader.
The actual reading logic is 100% client-side (Web Speech API + Hecos Local TTS + PDF.js visual canvas).

LLM Tools & Direct Slash Commands:
  - /read [file_or_query]     → read_document(path)
  - /stop_reading             → stop_reading()
  - /read_list                → list_documents(folder)
"""

import os
import sys
import re
from typing import Optional, List, Tuple

try:
    from hecos.core.logging import logger
except ImportError:
    class _L:
        def info(self, *a): print("[DOCUMENT_READER]", *a)
        def error(self, *a): print("[DOCUMENT_READER ERR]", *a)
        def debug(self, *a, **kw): pass
        def warning(self, *a): print("[DOCUMENT_READER WARN]", *a)
    logger = _L()


TAG = "DOCUMENT_READER"
SUPPORTED_EXTS = (".pdf", ".txt", ".md", ".html", ".htm", ".docx")


class DocumentReaderTools:
    tag      = TAG
    desc     = "Universal document reader with TTS. Fullscreen reading mode, visual PDF canvas, word-by-word highlighting."
    icon     = "📖"
    category = "DOCUMENTS"

    def __new__(cls, *args, **kwargs):
        if not hasattr(sys, "_hecos_docreader_tools"):
            instance = super(DocumentReaderTools, cls).__new__(cls)
            instance._is_initialized = False
            setattr(sys, "_hecos_docreader_tools", instance)
        return getattr(sys, "_hecos_docreader_tools")

    def __init__(self, config=None):
        if getattr(self, "_is_initialized", False):
            if config:
                self._cfg.update(config)
            return
        self._is_initialized = True
        self._cfg = config or {}

        # ── HDCS Direct Slash Commands ──────────────────────────────────────
        self.slash_commands = [
            {
                "id": "read",
                "aliases": ["/read", "/leggi", "/reader", "/docreader", "/leggi_documento"],
                "description": "Apre e legge un documento con voce sintetizzata nel Document Reader",
                "usage": "/read [percorso o nome file]",
                "example": "/read fotoromanzo",
                "icon": "📖",
                "category": "DOCUMENTS",
                "method": "read_document",
                "requires_args": False,
            },
            {
                "id": "stop_reading",
                "aliases": ["/stop_reading", "/ferma_lettura", "/stop_doc", "/stop_reader"],
                "description": "Interrompe la lettura vocale attiva nel Document Reader",
                "usage": "/stop_reading",
                "example": "/stop_reading",
                "icon": "⏹️",
                "category": "DOCUMENTS",
                "method": "stop_reading",
                "requires_args": False,
            },
            {
                "id": "read_list",
                "aliases": ["/read_list", "/doc_list", "/lista_lettura"],
                "description": "Elenca i documenti disponibili da leggere con il Document Reader",
                "usage": "/read_list",
                "example": "/read_list",
                "icon": "📑",
                "category": "DOCUMENTS",
                "method": "list_documents",
                "requires_args": False,
            }
        ]

    def __call__(self):
        """Allows tools instance to be called directly if framework expects a callable factory."""
        return self

    # ── Folder & Path Discovery ──────────────────────────────────────────────
    def _get_candidate_folders(self) -> List[str]:
        """Returns standard directories where documents might be stored in Hecos."""
        candidates = []
        seen = set()

        def _add(p):
            if not p:
                return
            norm = os.path.normcase(os.path.abspath(p))
            if norm not in seen and os.path.isdir(norm):
                seen.add(norm)
                candidates.append(p)
        
        # 1. Configured path if present
        _add(self._cfg.get("documents_dir"))

        # 2. Base Hecos workspace documents (standard path)
        base_hecos = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
        _add(os.path.join(base_hecos, "hecos", "media", "documents"))

        # 3. Direct documents folder
        _add(os.path.join(base_hecos, "documents"))

        # 4. Fallback hardcoded standard paths
        _add(r"C:\Hecos\hecos\media\documents")

        # 5. Legacy modules fallback if present
        _add(os.path.join(base_hecos, "hecos", "modules", "media", "documents"))
        _add(r"C:\Hecos\hecos\modules\media\documents")

        return candidates

    def _resolve_document_path(self, query: str = "") -> Tuple[Optional[str], List[str]]:
        """
        Smart path and document resolver.
        Accepts:
          - Direct absolute/relative file path
          - Partial filename (e.g. 'fotoromanzo', 'fotoromanzo numero 1')
          - Natural language query
        Returns:
          (best_matching_filepath, all_candidate_filenames)
        """
        query = (query or "").strip()
        all_files = []
        folders = self._get_candidate_folders()

        # Collect all available document files from candidate folders
        seen_fnames = set()
        for folder in folders:
            if not os.path.isdir(folder):
                continue
            for fname in os.listdir(folder):
                f_lower = fname.lower()
                if f_lower in seen_fnames:
                    continue
                if any(f_lower.endswith(ext) for ext in SUPPORTED_EXTS):
                    seen_fnames.add(f_lower)
                    all_files.append((folder, fname))

        if not query:
            return None, [fname for _, fname in all_files]

        # 1. Direct file existence check
        clean_q = query.strip("\"' ")
        if os.path.isfile(clean_q):
            return os.path.abspath(clean_q), [fname for _, fname in all_files]

        # 2. Check direct filename in candidate folders
        for folder, fname in all_files:
            if fname.lower() == clean_q.lower():
                return os.path.join(folder, fname), [fn for _, fn in all_files]

        # 3. Substring match
        q_lower = clean_q.lower()
        for folder, fname in all_files:
            if q_lower in fname.lower():
                return os.path.join(folder, fname), [fn for _, fn in all_files]

        # 4. Token-based matching (strip Italian/English stop words)
        stop_words = {
            'il', 'lo', 'la', 'i', 'gli', 'le', 'un', 'uno', 'una', 
            'di', 'a', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra', 
            'del', 'dello', 'della', 'dei', 'degli', 'delle', 
            'numero', 'n', 'num', 'leggi', 'leggimi', 'apri', 'entra', 
            'cartella', 'documento', 'file', 'read', 'open', 'the', 'and', 'in'
        }
        tokens = [t for t in re.split(r'[\s_\-\.]+', q_lower) if t and t not in stop_words]

        scored = []
        for folder, fname in all_files:
            f_norm = fname.lower()
            score = 0
            for t in tokens:
                if t in f_norm:
                    score += 10
            if score > 0:
                scored.append((score, os.path.join(folder, fname)))

        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            return scored[0][1], [fn for _, fn in all_files]

        return None, [fn for _, fn in all_files]

    # ── LLM Tool / Slash Command: list_documents ─────────────────────────────
    def list_documents(self, folder: str = "") -> str:
        """
        List all readable documents available in the documents library.
        Use this when the user asks to see what documents are available to read.
        """
        folders = [folder] if folder and os.path.isdir(folder) else self._get_candidate_folders()
        all_found = []

        seen_fnames = set()
        for fld in folders:
            if not os.path.isdir(fld):
                continue
            for fname in os.listdir(fld):
                f_lower = fname.lower()
                if f_lower in seen_fnames:
                    continue
                if any(f_lower.endswith(ext) for ext in SUPPORTED_EXTS):
                    seen_fnames.add(f_lower)
                    full_p = os.path.join(fld, fname)
                    try:
                        sz = os.path.getsize(full_p)
                        sz_str = f"{sz / 1024:.1f} KB" if sz < 1048576 else f"{sz / 1048576:.1f} MB"
                    except Exception:
                        sz_str = "N/A"
                    ext = os.path.splitext(fname)[1].upper().replace(".", "")
                    all_found.append((fname, ext, sz_str, full_p))

        if not all_found:
            return "📁 Nessun documento trovato nella cartella documenti (`hecos/media/documents`)."

        lines = [
            "### 📁 Documenti Disponibili per la Lettura\n",
            "| Documento | Formato | Dimensione |",
            "| :--- | :---: | :---: |"
        ]
        for fname, ext, sz_str, _ in sorted(all_found, key=lambda x: x[0].lower()):
            lines.append(f"| **{fname}** | `{ext}` | {sz_str} |")

        lines.append(
            "\n💡 *Per leggerne uno, digita `/read <nome>` o chiedimi ad esempio: \"leggimi il fotoromanzo\".*"
        )
        return "\n".join(lines)

    # ── LLM Tool / Slash Command: read_document ──────────────────────────────
    def read_document(self, path: str = "") -> str:
        """
        Open a document in the fullscreen Document Reader with TTS capabilities.
        Accepts a full path, relative path, or search query (e.g. 'fotoromanzo', 'fotoromanzo numero 1').
        If path is omitted, displays available documents and opens the document picker.
        """
        query = (path or "").strip()

        # If no path provided, show document list and trigger picker
        if not query:
            listing = self.list_documents()
            return (
                f"{listing}\n\n"
                f"<docreader-picker></docreader-picker>"
            )

        resolved_path, candidates = self._resolve_document_path(query)

        if not resolved_path:
            listing = self.list_documents()
            return (
                f"❌ Documento non trovato per la ricerca: **\"{query}\"**.\n\n"
                f"{listing}"
            )

        ext = os.path.splitext(resolved_path)[1].lower()
        if ext not in SUPPORTED_EXTS:
            return f"❌ Formato non supportato: `{ext}`. Formati compatibili: PDF, TXT, MD, HTML, DOCX."

        filename = os.path.basename(resolved_path)
        safe_path = resolved_path.replace("\\", "/")

        return (
            f"📖 Sto aprendo **{filename}** nel Document Reader con sintesi vocale.\n\n"
            f"<docreader-open path=\"{safe_path}\"></docreader-open>\n"
            f"[DOCREADER:open:{safe_path}]"
        )

    # ── LLM Tool / Slash Command: stop_reading ───────────────────────────────
    def stop_reading(self) -> str:
        """Stop the current TTS reading session."""
        return (
            "⏹️ Lettura del Document Reader interrotta.\n\n"
            "<docreader-stop></docreader-stop>\n"
            "[DOCREADER:stop]"
        )


# ── Module-level exports required by Hecos plugin loader ────────────────────

_instance = None

def get_plugin():
    global _instance
    if _instance is None:
        _instance = DocumentReaderTools()
    return _instance

# Module attribute 'tools' serves both as singleton instance and factory
tools = get_plugin()

def on_load(cfg_mgr=None, **kwargs):
    config = {}
    if cfg_mgr:
        try:
            config = cfg_mgr.get_plugin_config(TAG) or {}
        except Exception:
            pass
    global _instance, tools
    _instance = DocumentReaderTools(config)
    tools = _instance
    
    # Register Flask routes (self-injection into chat page)
    try:
        app = getattr(sys, "hecos_flask_app", None)
        if app:
            from .web.routes import init_plugin_routes
            init_plugin_routes(app, cfg_mgr, os.path.dirname(os.path.abspath(__file__)), logger)
    except Exception as e:
        logger.debug(f"[DocReader] Route registration in on_load deferred: {e}")
    
    logger.info("[DocReader] Plugin loaded.")
    return _instance

def info():
    return {
        "tag": TAG,
        "name": "Hecos Document Reader",
        "version": "1.0.0",
        "description": "Universal document reader with TTS. Fullscreen reading mode with audiobook-style controls and visual PDF rendering.",
    }

def status():
    return {"ok": True, "tag": TAG}
