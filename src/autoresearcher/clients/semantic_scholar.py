from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from autoresearcher.models import PaperMetadata

SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_API_KEY_ENV = "SEMANTIC_SCHOLAR_API_KEY"
DEFAULT_RATE_LIMIT_SECONDS = 1.0
DEFAULT_MAX_RETRIES = 3
FIELDS = ",".join(
    [
        "paperId",
        "title",
        "authors",
        "abstract",
        "url",
        "year",
        "citationCount",
        "venue",
        "externalIds",
        "openAccessPdf",
        "publicationDate",
    ]
)
_rate_limit_lock = threading.Lock()
_last_request_at = 0.0


def search_semantic_scholar(
    query: str,
    limit: int = 10,
    timeout: float = 20.0,
    api_key: str | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    rate_limit_seconds: float = DEFAULT_RATE_LIMIT_SECONDS,
) -> list[PaperMetadata]:
    """Search Semantic Scholar and return normalized paper metadata."""
    params = urllib.parse.urlencode({"query": query, "limit": limit, "fields": FIELDS})
    request = urllib.request.Request(
        f"{SEMANTIC_SCHOLAR_SEARCH_URL}?{params}",
        headers=_build_headers(api_key),
    )
    payload = _fetch_json_with_retries(
        request,
        timeout=timeout,
        max_retries=max_retries,
        rate_limit_seconds=rate_limit_seconds,
    )
    return parse_semantic_scholar_response(payload)


def parse_semantic_scholar_response(payload: dict) -> list[PaperMetadata]:
    papers: list[PaperMetadata] = []
    for item in payload.get("data", []):
        external_ids = item.get("externalIds") or {}
        open_access_pdf = item.get("openAccessPdf") or {}
        authors = [
            author.get("name", "").strip()
            for author in item.get("authors", [])
            if author.get("name")
        ]
        paper = PaperMetadata(
            title=(item.get("title") or "").strip(),
            authors=authors,
            abstract=(item.get("abstract") or "").strip(),
            url=item.get("url") or "",
            source="semantic_scholar",
            paper_id=item.get("paperId"),
            doi=external_ids.get("DOI"),
            arxiv_id=external_ids.get("ArXiv"),
            published_at=item.get("publicationDate"),
            year=item.get("year"),
            citation_count=item.get("citationCount"),
            venue=item.get("venue"),
            pdf_url=open_access_pdf.get("url"),
            raw=item,
        )
        if paper.title:
            papers.append(paper)
    return papers


def _build_headers(api_key: str | None = None) -> dict[str, str]:
    headers = {"User-Agent": "AutoResearcher/0.1"}
    resolved_api_key = (
        api_key if api_key is not None else os.getenv(SEMANTIC_SCHOLAR_API_KEY_ENV, "")
    ).strip()
    if resolved_api_key:
        headers["x-api-key"] = resolved_api_key
    return headers


def _fetch_json_with_retries(
    request: urllib.request.Request,
    timeout: float,
    max_retries: int,
    rate_limit_seconds: float,
) -> dict:
    for attempt in range(max_retries + 1):
        _respect_rate_limit(rate_limit_seconds)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt >= max_retries:
                raise
            time.sleep(_retry_delay_seconds(exc, attempt))
    raise RuntimeError("Semantic Scholar request retry loop exited unexpectedly.")


def _respect_rate_limit(rate_limit_seconds: float) -> None:
    if rate_limit_seconds <= 0:
        return
    global _last_request_at
    with _rate_limit_lock:
        now = time.monotonic()
        wait_seconds = _last_request_at + rate_limit_seconds - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        _last_request_at = time.monotonic()


def _retry_delay_seconds(exc: urllib.error.HTTPError, attempt: int) -> float:
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass
    return min(8.0, 2.0**attempt)
