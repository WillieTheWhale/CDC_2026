# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""World Bank Indicators API v2 client (follows skills/world-bank-indicators-api/SKILL.md).

- Always `format=json` and an explicit `source` for indicator calls.
- Reads every page reported by the response metadata (`pages`); never assumes one page is complete.
- Keeps `null` observations (never coerced to zero) and the `lastupdated` metadata.
- Bounded retries with backoff for transient failures; detects JSON error bodies returned with HTTP 200.
- On-disk cache of raw pages so reruns are reproducible and polite.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

BASE = "https://api.worldbank.org/v2"
log = logging.getLogger(__name__)


class WorldBankError(RuntimeError):
    pass


@dataclass
class FetchResult:
    url: str
    records: list[dict]
    lastupdated: str | None
    sourceid: str | None
    total: int
    pages: int
    retrieved_at: str
    from_cache: bool = False
    page_urls: list[str] = field(default_factory=list)


class WorldBankClient:
    def __init__(self, cache_dir: Path | None = None, timeout: float = 60, retries: int = 4,
                 per_page: int = 20000, refresh: bool = False, session: requests.Session | None = None):
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.retries = retries
        self.per_page = per_page
        self.refresh = refresh
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "TRACE/0.1 (CDC 2026 research project)"})

    # ------------------------------------------------------------------ low level
    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir:
            return None
        h = hashlib.sha1(url.encode()).hexdigest()[:16]
        return self.cache_dir / f"{h}.json"

    def get_json(self, path: str, params: dict[str, Any]) -> tuple[Any, bool, str]:
        params = {**params, "format": "json"}
        url = f"{BASE}/{path.lstrip('/')}?{urlencode(params)}"
        cp = self._cache_path(url)
        if cp and cp.exists() and not self.refresh:
            payload = json.loads(cp.read_text(encoding="utf-8"))
            return payload["body"], True, payload["retrieved_at"]
        last_exc: Exception | None = None
        for attempt in range(self.retries):
            try:
                r = self.session.get(url, timeout=self.timeout)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise WorldBankError(f"HTTP {r.status_code}")
                r.raise_for_status()
                ctype = r.headers.get("content-type", "")
                if "json" not in ctype and not r.text.lstrip().startswith("["):
                    raise WorldBankError(f"non-JSON response ({ctype}): {r.text[:200]}")
                body = r.json()
                # Error bodies arrive with HTTP 200 as [{"message": [...]}]
                if isinstance(body, list) and body and isinstance(body[0], dict) and "message" in body[0]:
                    raise WorldBankError(f"API error for {url}: {body[0]['message']}")
                retrieved = datetime.now(UTC).isoformat(timespec="seconds")
                if cp:
                    cp.parent.mkdir(parents=True, exist_ok=True)
                    cp.write_text(json.dumps({"url": url, "retrieved_at": retrieved, "body": body}), encoding="utf-8")
                return body, False, retrieved
            except WorldBankError as exc:
                if "API error" in str(exc):
                    raise
                last_exc = exc
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
            wait = 2 ** attempt
            log.warning("World Bank request failed (%s), retry %d/%d in %ss: %s", last_exc, attempt + 1,
                        self.retries, wait, url)
            time.sleep(wait)
        raise WorldBankError(f"giving up on {url}: {last_exc}")

    def fetch_all(self, path: str, params: dict[str, Any]) -> FetchResult:
        page, pages, records, urls = 1, 1, [], []
        first_meta: dict = {}
        all_cached, retrieved_at = True, None
        while page <= pages:
            p = {**params, "per_page": self.per_page, "page": page}
            body, cached, retrieved = self.get_json(path, p)
            all_cached &= cached
            retrieved_at = retrieved_at or retrieved
            urls.append(f"{BASE}/{path.lstrip('/')}?{urlencode({**p, 'format': 'json'})}")
            if not isinstance(body, list) or len(body) < 2:
                meta = body[0] if isinstance(body, list) and body else {}
                if int(meta.get("total", 0) or 0) == 0:
                    break
                raise WorldBankError(f"unexpected payload shape for {path}: {str(body)[:200]}")
            meta, rows = body[0], body[1] or []
            if page == 1:
                first_meta = meta
            pages = int(meta.get("pages", 1) or 1)
            records.extend(rows)
            page += 1
        total = int(first_meta.get("total", len(records)) or 0)
        if total and len(records) != total:
            raise WorldBankError(f"pagination mismatch for {path}: got {len(records)} of {total}")
        return FetchResult(url=urls[0] if urls else f"{BASE}/{path}", records=records,
                           lastupdated=first_meta.get("lastupdated"), sourceid=first_meta.get("sourceid"),
                           total=total, pages=pages, retrieved_at=retrieved_at or "", from_cache=all_cached,
                           page_urls=urls)

    # ------------------------------------------------------------------ high level
    def indicator(self, code: str, source_id: int, date: str) -> FetchResult:
        return self.fetch_all(f"country/all/indicator/{code}", {"source": source_id, "date": date})

    def countries(self) -> FetchResult:
        return self.fetch_all("country", {})

    def indicator_metadata(self, code: str, source_id: int) -> dict:
        body, _, _ = self.get_json(f"indicator/{code}", {"source": source_id})
        if isinstance(body, list) and len(body) > 1 and body[1]:
            return body[1][0]
        return {}
