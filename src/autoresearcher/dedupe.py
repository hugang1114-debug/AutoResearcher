from __future__ import annotations

import re

from autoresearcher.models import PaperMetadata, normalize_text


def deduplicate_papers(papers: list[PaperMetadata]) -> list[PaperMetadata]:
    """Deduplicate papers while preserving the best metadata-rich record."""
    by_key: dict[str, PaperMetadata] = {}
    for paper in papers:
        keys = _dedupe_keys(paper)
        existing_key = next((key for key in keys if key in by_key), None)
        if existing_key is None:
            for key in keys:
                by_key[key] = paper
            continue
        winner = _prefer_richer_record(by_key[existing_key], paper)
        merged_keys = {*keys, *(_dedupe_keys(by_key[existing_key]))}
        for key in merged_keys:
            by_key[key] = winner
    unique: list[PaperMetadata] = []
    seen_ids: set[int] = set()
    for paper in by_key.values():
        object_id = id(paper)
        if object_id not in seen_ids:
            seen_ids.add(object_id)
            unique.append(paper)
    return unique


def _dedupe_keys(paper: PaperMetadata) -> list[str]:
    keys: list[str] = []
    if paper.doi:
        keys.append(f"doi:{normalize_text(paper.doi)}")
    if paper.arxiv_id:
        keys.append(f"arxiv:{_strip_arxiv_version(paper.arxiv_id).casefold()}")
    if paper.url:
        keys.append(f"url:{paper.url.rstrip('/').casefold()}")
    keys.append(f"title:{_normalize_title(paper.title)}")
    return keys


def _normalize_title(title: str) -> str:
    text = normalize_text(title)
    return re.sub(r"[^a-z0-9 ]+", "", text)


def _strip_arxiv_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id.strip(), flags=re.IGNORECASE)


def _prefer_richer_record(left: PaperMetadata, right: PaperMetadata) -> PaperMetadata:
    left_score = _metadata_score(left)
    right_score = _metadata_score(right)
    if right_score > left_score:
        right.relevance_score = max(left.relevance_score, right.relevance_score)
        return right
    left.relevance_score = max(left.relevance_score, right.relevance_score)
    return left


def _metadata_score(paper: PaperMetadata) -> int:
    return sum(
        [
            bool(paper.abstract),
            bool(paper.authors),
            bool(paper.pdf_url),
            bool(paper.doi),
            bool(paper.arxiv_id),
            bool(paper.citation_count),
            bool(paper.venue),
        ]
    )
