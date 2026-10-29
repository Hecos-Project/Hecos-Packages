"""
search/extract/cleaner.py
Cleans raw HTML into dense, readable text / markdown tailored for LLM processing.
Prioritizes trafilatura if installed, with a robust BeautifulSoup/lxml fallback.
"""
from __future__ import annotations

import re
import logging
from typing import Dict, Any

logger = logging.getLogger("browser.search.cleaner")

try:
    from hecos.core.logging import logger as hecos_logger
except (ImportError, ValueError):
    hecos_logger = logger


def clean_html(html_content: str, max_chars: int = 5000) -> Dict[str, Any]:
    """
    Extracts title, meta description, and cleaned text body from HTML.
    Returns: {"title": str, "description": str, "text": str, "method": str}
    """
    if not html_content:
        return {"title": "", "description": "", "text": "", "method": "none"}

    title = ""
    description = ""
    text_content = ""
    method = "fallback"

    # Try trafilatura first if available
    try:
        import trafilatura
        extracted = trafilatura.extract(
            html_content,
            include_comments=False,
            include_tables=True,
            no_fallback=False
        )
        if extracted:
            text_content = extracted.strip()
            method = "trafilatura"
            # Extract metadata
            meta = trafilatura.extract_metadata(html_content)
            if meta:
                title = meta.title or ""
                description = meta.description or ""
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Trafilatura extraction error: {e}")

    # Fallback to BeautifulSoup if trafilatura wasn't available or returned empty
    if not text_content:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, "lxml")

            # Extract title
            if not title:
                t_tag = soup.find("title")
                if t_tag and t_tag.string:
                    title = t_tag.string.strip()

            # Extract meta description
            if not description:
                meta_desc = soup.find("meta", attrs={"name": re.compile(r"description", re.I)}) or \
                            soup.find("meta", attrs={"property": "og:description"})
                if meta_desc and meta_desc.get("content"):
                    description = meta_desc["content"].strip()

            # Remove noise elements
            for tag in soup(["script", "style", "noscript", "iframe", "svg", "header", "footer", "nav", "aside"]):
                tag.decompose()

            # Prefer main article container if found
            main_container = soup.find("article") or soup.find("main") or soup.find(id=re.compile(r"content|main", re.I))
            target = main_container if main_container else soup.body or soup

            raw_text = target.get_text(separator="\n", strip=True)
            # Collapse excess whitespace/newlines
            lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
            text_content = "\n".join(lines)
            method = "bs4_lxml"
        except Exception as e:
            logger.debug(f"BeautifulSoup parsing fallback failed: {e}")
            # Regex raw text fallback
            text_content = re.sub(r"<[^>]+>", " ", html_content)
            text_content = re.sub(r"\s+", " ", text_content).strip()
            method = "regex"

    # Truncate if exceeding max_chars
    if len(text_content) > max_chars:
        text_content = text_content[:max_chars] + f"\n\n[... truncated at {max_chars} characters ...]"

    hecos_logger.debug(f"[CLEANER] HTML cleaned using method '{method}' ({len(text_content)} chars)")

    return {
        "title": title,
        "description": description,
        "text": text_content,
        "method": method
    }
