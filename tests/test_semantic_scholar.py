import io
import urllib.error

import pytest

from autoresearcher.clients import semantic_scholar
from autoresearcher.clients.semantic_scholar import (
    SEMANTIC_SCHOLAR_API_KEY_ENV,
    parse_semantic_scholar_response,
    search_semantic_scholar,
)


def test_parse_semantic_scholar_response_normalizes_metadata():
    payload = {
        "data": [
            {
                "paperId": "abc123",
                "title": "RAG Evaluation",
                "authors": [{"name": "Ada Lovelace"}],
                "abstract": "A paper about evaluation.",
                "url": "https://www.semanticscholar.org/paper/abc123",
                "year": 2024,
                "citationCount": 42,
                "venue": "TestConf",
                "externalIds": {"DOI": "10.1000/example", "ArXiv": "2401.00001"},
                "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                "publicationDate": "2024-01-01",
            }
        ]
    }

    papers = parse_semantic_scholar_response(payload)

    assert len(papers) == 1
    assert papers[0].source == "semantic_scholar"
    assert papers[0].paper_id == "abc123"
    assert papers[0].doi == "10.1000/example"
    assert papers[0].arxiv_id == "2401.00001"
    assert papers[0].citation_count == 42
    assert papers[0].pdf_url == "https://example.com/paper.pdf"


def test_search_semantic_scholar_uses_api_key_header(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["api_key"] = dict(request.header_items()).get("X-api-key")
        captured["timeout"] = timeout
        return FakeResponse({"data": []})

    monkeypatch.setenv(SEMANTIC_SCHOLAR_API_KEY_ENV, "test-key")
    monkeypatch.setattr(semantic_scholar.urllib.request, "urlopen", fake_urlopen)

    papers = search_semantic_scholar("rag", timeout=7, rate_limit_seconds=0)

    assert papers == []
    assert captured == {"api_key": "test-key", "timeout": 7}


def test_search_semantic_scholar_retries_429_with_retry_after(monkeypatch):
    calls = {"count": 0}
    sleeps = []

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.HTTPError(
                url=request.full_url,
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "0.25"},
                fp=io.BytesIO(b""),
            )
        return FakeResponse({"data": [{"paperId": "p1", "title": "RAG Evaluation"}]})

    monkeypatch.setattr(semantic_scholar.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(semantic_scholar.time, "sleep", lambda seconds: sleeps.append(seconds))

    papers = search_semantic_scholar("rag", max_retries=1, rate_limit_seconds=0)

    assert calls["count"] == 2
    assert sleeps == [0.25]
    assert papers[0].title == "RAG Evaluation"


def test_semantic_scholar_rate_limit_waits_between_requests(monkeypatch):
    monotonic_values = iter([10.0, 10.0, 10.2, 11.2])
    sleeps = []
    monkeypatch.setattr(semantic_scholar.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(semantic_scholar.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(semantic_scholar, "_last_request_at", 0.0)

    semantic_scholar._respect_rate_limit(1.0)
    semantic_scholar._respect_rate_limit(1.0)

    assert sleeps == pytest.approx([0.8])


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def read(self):
        import json

        return json.dumps(self.payload).encode("utf-8")
