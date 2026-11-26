"""
Smart Media & Document Path Resolver for Hecos Messenger (v2.2).
Resolves:
  - Absolute paths ('C:/Hecos/...') and file:/// URIs
  - ImageGen tags ('[[IMG:gen_...png]]', '/api/images/gen_...png') and '/snapshots/...'
  - Bare filenames ('gen_...png', 'report.pdf') across Hecos media folders
  - Automatic 'latest' / empty image_path resolution to recently generated binary images
  - Magic-byte binary image verification to block fake text files written by EXECUTOR
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Optional


_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})
_LATEST_TOKENS = frozenset({"", "latest", "last", "recent", "ultima", "ultimo", "selfie"})

_IMG_TAG_RE = re.compile(r"\[\[IMG:([^\]]+)\]\]", re.IGNORECASE)
_MD_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _get_hecos_dir() -> Path:
    try:
        from hecos.core.constants import HECOS_DIR
        return Path(HECOS_DIR).resolve()
    except Exception:
        # .../hecos/hpm/messenger/core/media_resolver.py -> parents[3] == .../hecos
        return Path(__file__).resolve().parents[3]


def _candidate_media_dirs() -> list[Path]:
    hecos_dir = _get_hecos_dir()
    media_root = hecos_dir / "media"
    subdirs = (
        "images",
        "generated",
        "generated_photos",
        "documents",
        "snapshots",
        "screenshots",
        "Hecos_screenshots",
        "downloads",
        "audio",
        "video",
        "workspace",
    )
    dirs: list[Path] = []
    try:
        from hecos.core.constants import IMAGES_DIR
        p_img = Path(IMAGES_DIR).resolve()
        if p_img.is_dir():
            dirs.append(p_img)
    except Exception:
        pass

    for name in subdirs:
        cand = (media_root / name).resolve()
        if cand.is_dir() and cand not in dirs:
            dirs.append(cand)
    return dirs


def is_valid_binary_image(file_path: str | Path) -> tuple[bool, str]:
    """
    Verifies that `file_path` is a genuine binary image file on disk via magic bytes
    (rejecting directories, empty files, or plain-text descriptions written by EXECUTOR).
    """
    p = Path(file_path)
    if p.is_dir():
        return False, f"'{p}' is a directory, not an image file."
    if not p.is_file():
        return False, f"Image file not found: '{p}'."

    try:
        size = p.stat().st_size
        if size < 64:
            return False, (
                f"File '{p.name}' ({size} bytes) is too small/corrupt to be a real image. "
                "NEVER use EXECUTOR__write_file to create fake image files — use IMAGE_GEN__generate_image!"
            )
        with open(p, "rb") as fh:
            header = fh.read(32)
    except Exception as exc:
        return False, f"Cannot read image file '{p}': {exc}"

    if (
        header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"\xff\xd8\xff")
        or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
        or header.startswith((b"GIF87a", b"GIF89a"))
        or header.startswith(b"BM")
    ):
        return True, ""

    return False, (
        f"File '{p.name}' contains plain text or non-image data instead of real image pixels! "
        "NEVER use EXECUTOR (write_file / read_file / run_aider_task) to fake photos. "
        "Call IMAGE_GEN__generate_image(prompt='...') first, then call MESSENGER__send_photo(image_path='latest', ...)."
    )


def find_latest_generated_image(max_age_seconds: float = 900.0) -> Optional[str]:
    """
    Finds the most recently generated valid binary image in Hecos's active turn trace
    or in `hecos/media/images` within `max_age_seconds` (default 15 minutes).
    """
    # 1. Check active TraceSession steps if an image was just generated in this exact turn
    try:
        from hecos.core.agent.trace_session import get_active_session
        sess = get_active_session()
        if sess and getattr(sess, "steps", None):
            for step in reversed(sess.steps):
                preview = str(step.get("result_preview") or "") + " " + str(step.get("detail") or "")
                for m in _IMG_TAG_RE.finditer(preview):
                    resolved = _locate_existing_file(m.group(1).strip())
                    if resolved:
                        ok, _ = is_valid_binary_image(resolved)
                        if ok:
                            return resolved
    except Exception:
        pass

    # 2. Scan primary generated images folders for newest valid binary image within max_age_seconds
    now = time.time()
    best_path: Optional[Path] = None
    best_mtime: float = 0.0

    hecos_dir = _get_hecos_dir()
    gen_dirs = [
        hecos_dir / "media" / "images",
        hecos_dir / "media" / "generated",
        hecos_dir / "media" / "generated_photos",
        hecos_dir / "media" / "snapshots",
    ]
    for d in gen_dirs:
        if not d.is_dir():
            continue
        try:
            for entry in d.iterdir():
                if not entry.is_file() or entry.suffix.lower() not in _IMAGE_EXTENSIONS:
                    continue
                mtime = entry.stat().st_mtime
                if max_age_seconds > 0 and (now - mtime) > max_age_seconds:
                    continue
                if mtime > best_mtime:
                    ok, _ = is_valid_binary_image(entry)
                    if ok:
                        best_mtime = mtime
                        best_path = entry
        except Exception:
            continue

    return str(best_path.resolve()) if best_path else None


def _clean_raw_reference(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""

    m_tag = _IMG_TAG_RE.search(s)
    if m_tag:
        s = m_tag.group(1).strip()
    else:
        m_md = _MD_LINK_RE.search(s)
        if m_md:
            s = m_md.group(1).strip()

    s = s.strip("\"'` ")
    if s.lower().startswith("file:///"):
        s = s[8:]
    elif s.lower().startswith("file://"):
        s = s[7:]

    for web_prefix in ("/api/images/", "api/images/", "/snapshots/", "snapshots/", "/hecos/media/", "hecos/media/"):
        if s.lower().startswith(web_prefix):
            s = s[len(web_prefix):]
            break

    return s.strip()


def _locate_existing_file(cleaned: str) -> Optional[str]:
    if not cleaned:
        return None

    direct = Path(cleaned)
    if direct.is_file():
        return str(direct.resolve())

    hecos_dir = _get_hecos_dir()
    rel_hecos = hecos_dir / cleaned
    if rel_hecos.is_file():
        return str(rel_hecos.resolve())

    rel_root = hecos_dir.parent / cleaned
    if rel_root.is_file():
        return str(rel_root.resolve())

    basename = os.path.basename(cleaned)
    if basename:
        for mdir in _candidate_media_dirs():
            cand = mdir / basename
            if cand.is_file():
                return str(cand.resolve())

    return None


def resolve_photo_path(raw_path: str, recent_fallback_sec: float = 900.0) -> tuple[Optional[str], Optional[str]]:
    """
    Resolves an image reference into `(abs_file_path, error_message)`.
    Supports 'latest'/'last'/empty fallback to recent generated images and validates binary headers.
    """
    cleaned = _clean_raw_reference(raw_path)

    if cleaned.lower() in _LATEST_TOKENS:
        latest = find_latest_generated_image(max_age_seconds=recent_fallback_sec)
        if latest:
            return latest, None
        return None, (
            "No recent generated image found from the last 15 minutes. "
            "Call IMAGE_GEN__generate_image(prompt='...') first to create a real photo, "
            "then call MESSENGER__send_photo(to=..., image_path='latest', platform=...). "
            "Do NOT use EXECUTOR tools to create fake .jpg files!"
        )

    located = _locate_existing_file(cleaned)
    if located:
        ext = os.path.splitext(located)[1].lower()
        if ext in _IMAGE_EXTENSIONS:
            ok, err = is_valid_binary_image(located)
            if not ok:
                # If LLM passed a corrupt workspace file (e.g. fake selfie.jpg), check if a real generated image exists!
                if "workspace" in located.lower():
                    latest = find_latest_generated_image(max_age_seconds=recent_fallback_sec)
                    if latest:
                        return latest, None
                return None, err
        return located, None

    # If the LLM guessed a non-existent selfie filename (e.g. 'Urania_selfie.jpg') right after generating an image,
    # check if there is a very recent (< 5 min) generated image in media/images!
    if "workspace" in cleaned.lower() or "selfie" in cleaned.lower() or "urania" in cleaned.lower():
        latest_very_recent = find_latest_generated_image(max_age_seconds=300.0)
        if latest_very_recent:
            return latest_very_recent, None

    return None, (
        f"Image file '{raw_path}' was not found on disk. "
        "If you want to send a new photo/selfie, call IMAGE_GEN__generate_image(prompt='...') first "
        "and pass its [[IMG:filename]] (or image_path='latest') to MESSENGER__send_photo. "
        "NEVER use EXECUTOR__write_file to create fake image files!"
    )


def resolve_attachment_path(raw_path: str) -> tuple[Optional[str], Optional[str]]:
    """
    Resolves a general attachment/document path (PDF, HTML, DOCX, ZIP, audio, video, image)
    into `(abs_file_path, error_message)`.
    """
    cleaned = _clean_raw_reference(raw_path)
    if not cleaned:
        return None, "Parameter 'file_path' is required (pass the path or filename of the document/file to send)."

    if cleaned.lower() in ("latest", "last"):
        # Check newest PDF/HTML in hecos/media/documents first, else newest image
        hecos_dir = _get_hecos_dir()
        doc_dir = hecos_dir / "media" / "documents"
        if doc_dir.is_dir():
            docs = [
                f for f in doc_dir.iterdir()
                if f.is_file() and (time.time() - f.stat().st_mtime) <= 900.0
            ]
            if docs:
                newest_doc = max(docs, key=lambda p: p.stat().st_mtime)
                return str(newest_doc.resolve()), None

    located = _locate_existing_file(cleaned)
    if not located:
        return None, (
            f"Document/attachment file '{raw_path}' was not found on disk. "
            "Verify the exact file path (e.g. from DOCS__generate_pdf output) before calling MESSENGER."
        )

    ext = os.path.splitext(located)[1].lower()
    if ext in _IMAGE_EXTENSIONS:
        ok, err = is_valid_binary_image(located)
        if not ok:
            return None, err

    return located, None
