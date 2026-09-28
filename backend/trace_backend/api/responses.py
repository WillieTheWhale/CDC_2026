# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""JSON response class that survives clients which do not assume UTF-8.

Starlette's JSONResponse sends raw UTF-8 with `Content-Type: application/json` (no charset). Clients that fall back
to ISO-8859-1 / cp1252 without a charset (Windows PowerShell 5.1 Invoke-RestMethod, some proxies and scrapers) then
turn an en dash (UTF-8 bytes E2 80 93) into the mojibake "â€“". This class names the charset and escapes every
non-ASCII character (\\u2013), so the body is pure ASCII and decodes identically under any of those encodings.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi.responses import JSONResponse


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

    def render(self, content: Any) -> bytes:
        return json.dumps(content, ensure_ascii=True, allow_nan=False, indent=None,
                          separators=(",", ":")).encode("ascii")
