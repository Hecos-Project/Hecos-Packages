/**
 * Hecos Drive — Search Module
 * Provides live filename search with debounce against /drive/api/search.
 */

(function () {
  "use strict";

  const DEBOUNCE_MS = 350;
  let _debounceTimer = null;
  let _lastQuery = "";
  let _active = false;

  /* ── DOM refs (resolved after DOMContentLoaded) ─────────── */
  let inp, panel, body, countEl, scopeLabel, clearBtn;

  function _init() {
    inp        = document.getElementById("search-input");
    panel      = document.getElementById("search-results-panel");
    body       = document.getElementById("search-results-body");
    countEl    = document.getElementById("search-results-count");
    scopeLabel = document.getElementById("search-scope-label");
    clearBtn   = document.getElementById("search-clear");

    if (!inp) return;

    inp.addEventListener("input", () => {
      clearTimeout(_debounceTimer);
      const q = inp.value.trim();
      if (q.length < 2) {
        if (_active) _hide();
        return;
      }
      _debounceTimer = setTimeout(() => _run(q), DEBOUNCE_MS);
    });

    inp.addEventListener("keydown", (e) => {
      if (e.key === "Escape") clearSearch();
    });

    _updateScopeLabel();
  }

  function _updateScopeLabel() {
    if (!scopeLabel) return;
    const cur = typeof currentPath !== "undefined" ? currentPath : "";
    scopeLabel.textContent = cur ? `in: /${cur}` : "in: / (root)";
  }

  async function _run(q) {
    if (q === _lastQuery && _active) return;
    _lastQuery = q;
    _active = true;

    const cur = typeof currentPath !== "undefined" ? currentPath : "";
    const url = `/drive/api/search?q=${encodeURIComponent(q)}&path=${encodeURIComponent(cur)}&limit=100`;

    // Show loading state
    panel.classList.remove("hidden");
    body.innerHTML = `<div class="search-loading"><i class="fas fa-spinner fa-spin"></i> Searching…</div>`;
    countEl.textContent = "";

    try {
      const res  = await fetch(url);
      const data = await res.json();

      if (!data.ok) {
        body.innerHTML = `<div class="search-error"><i class="fas fa-exclamation-triangle"></i> ${data.error || "Error"}</div>`;
        return;
      }

      _renderResults(data.results, q);
      countEl.textContent = data.count === 100
        ? "100+ results"
        : `${data.count} result${data.count !== 1 ? "s" : ""}`;

    } catch (err) {
      body.innerHTML = `<div class="search-error"><i class="fas fa-wifi-slash"></i> Network error</div>`;
    }
  }

  function _highlight(text, q) {
    const idx = text.toLowerCase().indexOf(q.toLowerCase());
    if (idx === -1) return _esc(text);
    return _esc(text.slice(0, idx))
      + `<mark>${_esc(text.slice(idx, idx + q.length))}</mark>`
      + _esc(text.slice(idx + q.length));
  }

  function _esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function _fmtSize(bytes) {
    if (bytes == null) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
    return `${(bytes / 1073741824).toFixed(2)} GB`;
  }

  function _fmtDate(ts) {
    if (!ts) return "";
    return new Date(ts * 1000).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  function _renderResults(results, q) {
    if (!results.length) {
      body.innerHTML = `<div class="search-empty"><i class="fas fa-search"></i> No results for "<strong>${_esc(q)}</strong>"</div>`;
      return;
    }

    const folders = results.filter(r => r.is_dir);
    const files   = results.filter(r => !r.is_dir);

    let html = "";

    if (folders.length) {
      html += `<div class="search-group-title"><i class="fas fa-folder"></i> Folders (${folders.length})</div>`;
      folders.forEach(r => {
        html += `
          <div class="search-row" onclick="searchNavigate('${_esc(r.path)}')">
            <span class="sr-icon"><i class="fas fa-folder" style="color:var(--accent)"></i></span>
            <span class="sr-name">${_highlight(r.name, q)}</span>
            <span class="sr-path" title="${_esc(r.path)}">${_esc(r.path)}</span>
            <span class="sr-meta">${_fmtDate(r.modified)}</span>
          </div>`;
      });
    }

    if (files.length) {
      html += `<div class="search-group-title"><i class="fas fa-file"></i> Files (${files.length})</div>`;
      files.forEach(r => {
        const ext = r.name.split(".").pop().toLowerCase();
        const icon = _fileIcon(ext);
        const parentPath = r.path.includes("/") ? r.path.substring(0, r.path.lastIndexOf("/")) : "";
        html += `
          <div class="search-row" onclick="searchOpenFile('${_esc(r.path)}', '${_esc(r.name)}')">
            <span class="sr-icon"><i class="${icon}"></i></span>
            <span class="sr-name">${_highlight(r.name, q)}</span>
            <span class="sr-path" title="${_esc(r.path)}">${_esc(parentPath || "/")}</span>
            <span class="sr-meta">${_fmtSize(r.size)}</span>
            <span class="sr-actions">
              <button class="sr-btn" onclick="event.stopPropagation(); searchNavigate('${_esc(parentPath)}')" title="Go to folder"><i class="fas fa-folder-open"></i></button>
              <button class="sr-btn" onclick="event.stopPropagation(); window.location='/drive/api/download?path=${encodeURIComponent(r.path)}'" title="Download"><i class="fas fa-download"></i></button>
            </span>
          </div>`;
      });
    }

    body.innerHTML = html;
  }

  function _fileIcon(ext) {
    const map = {
      pdf: "fas fa-file-pdf", doc: "fas fa-file-word", docx: "fas fa-file-word",
      xls: "fas fa-file-excel", xlsx: "fas fa-file-excel",
      ppt: "fas fa-file-powerpoint", pptx: "fas fa-file-powerpoint",
      jpg: "fas fa-file-image", jpeg: "fas fa-file-image", png: "fas fa-file-image",
      gif: "fas fa-file-image", webp: "fas fa-file-image", svg: "fas fa-file-image",
      mp4: "fas fa-file-video", avi: "fas fa-file-video", mkv: "fas fa-file-video",
      mp3: "fas fa-file-audio", wav: "fas fa-file-audio",
      zip: "fas fa-file-archive", rar: "fas fa-file-archive", "7z": "fas fa-file-archive",
      py: "fas fa-file-code", js: "fas fa-file-code", ts: "fas fa-file-code",
      html: "fas fa-file-code", css: "fas fa-file-code", json: "fas fa-file-code",
      yaml: "fas fa-file-code", yml: "fas fa-file-code",
      txt: "fas fa-file-alt", md: "fas fa-file-alt", log: "fas fa-file-alt",
    };
    return map[ext] || "fas fa-file";
  }

  function _hide() {
    _active = false;
    _lastQuery = "";
    if (panel) panel.classList.add("hidden");
    if (body)  body.innerHTML = "";
  }

  /* ── Public API ──────────────────────────────────────────── */
  window.clearSearch = function () {
    if (inp) inp.value = "";
    _hide();
    inp && inp.focus();
  };

  window.searchNavigate = function (path) {
    clearSearch();
    if (typeof loadDir === "function") loadDir(path);
  };

  window.searchOpenFile = function (path, name) {
    // Try to preview viewable files, otherwise download
    const ext = name.split(".").pop().toLowerCase();
    const previewable = ["jpg","jpeg","png","gif","webp","svg","mp4","webm","mp3","wav","ogg","pdf","txt","md","log","json","yaml","yml","py","js","html","css"];
    if (previewable.includes(ext) && typeof previewFile === "function") {
      clearSearch();
      previewFile(path, name);
    } else {
      window.location = `/drive/api/download?path=${encodeURIComponent(path)}`;
    }
  };

  /** Call this after navigation to update the scope label */
  window.searchUpdateScope = function () {
    _updateScopeLabel();
    // Reset search if active on dir change
    if (_active) clearSearch();
  };

  document.addEventListener("DOMContentLoaded", _init);
})();
