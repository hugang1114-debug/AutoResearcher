from __future__ import annotations

import json
import urllib.parse
import urllib.request

from autoresearcher.models import PaperMetadata

SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
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


def search_semantic_scholar(
    query: str,
    limit: int = 10,
    timeout: float = 20.0,
) -> list[PaperMetadata]:
    """Search Semantic Scholar and return normalized paper metadata."""
    params = urllib.parse.urlencode({"query": query, "limit": limit, "fields": FIELDS})
    request = urllib.request.Request(
        f"{SEMANTIC_SCHOLAR_SEARCH_URL}?{params}",
        headers={"User-Agent": "AutoResearcher/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
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
