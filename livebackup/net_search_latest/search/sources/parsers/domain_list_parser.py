"""
search/sources/parsers/domain_list_parser.py
High-throughput parser for bare domain lists, hosts files (0.0.0.0 / 127.0.0.1),
and Adblock-style (||domain.com^) domain compilations.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


_ADBLOCK_RE = re.compile(r"^\|\|([a-z0-9.-]+\.[a-z]{2,63})\^?", re.IGNORECASE)
_DOMAIN_TOKEN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.IGNORECASE)


def parse_domain_list(raw_bytes: bytes, source_url: str = "") -> List[Dict[str, Any]]:
    text = raw_bytes.decode("utf-8", errors="replace")
    if not text.strip():
        return []

    hint = (source_url or "").lower()
    if "allow" in hint or "whitelist" in hint:
        role = "domain_allowlist"
    elif "block" in hint or "porn" in hint or "ads" in hint or "hosts" in hint:
        role = "domain_blocklist"
    else:
        role = "domain_blocklist"

    candidates: List[Dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "!", "//", ";", "[")):
            continue

        # Strip inline comments
        if " #" in line:
            line = line.split(" #", 1)[0].strip()

        m_ab = _ADBLOCK_RE.match(line)
        if m_ab:
            dom = m_ab.group(1).lower()
            candidates.append({"host": dom, "domain": dom, "kind": "domain", "target_pool": role})
            continue

        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("0.0.0.0", "127.0.0.1", "::", "::1"):
            dom = parts[1].lower().strip(".")
            if dom not in ("localhost", "localhost.localdomain", "broadcasthost") and _DOMAIN_TOKEN_RE.match(dom):
                candidates.append({"host": dom, "domain": dom, "kind": "domain", "target_pool": role})
            continue

        token = parts[0].lower().strip(".")
        if "://" in token:
            continue
        if _DOMAIN_TOKEN_RE.match(token) and not token.endswith(".onion"):
            candidates.append({"host": token, "domain": token, "kind": "domain", "target_pool": role})

    return candidates

