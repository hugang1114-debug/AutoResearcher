from __future__ import annotations

import math
import re

from autoresearcher.models import PaperMetadata, normalize_text


def rank_papers(topic: str, papers: list[PaperMetadata]) -> list[PaperMetadata]:
    """Rank papers using token overlap plus recency and citation signals."""
    topic_terms = _tokenize(topic)
    for paper in papers:
        paper.relevance_score = score_paper(topic_terms, paper)
    return sorted(
        papers,
        key=lambda paper: (
            paper.relevance_score,
            paper.year or 0,
            paper.citation_count or 0,
        ),
        reverse=True,
    )


def score_paper(topic_terms: set[str], paper: PaperMetadata) -> float:
    haystack = f"{paper.title} {paper.abstract}"
    paper_terms = _tokenize(haystack)
    if not topic_terms:
        overlap_score = 0.0
    else:
        overlap_score = len(topic_terms & paper_terms) / len(topic_terms)
    title_terms = _tokenize(paper.title)
    title_bonus = 0.25 * len(topic_terms & title_terms)
    recency_bonus = _recency_bonus(paper.year)
    citation_bonus = math.log1p(paper.citation_count or 0) / 20.0
    return round(overlap_score + title_bonus + recency_bonus + citation_bonus, 4)


def _tokenize(value: str) -> set[str]:
    text = normalize_text(value)
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9-]*", text)
        if len(token) > 2 and token not in STOPWORDS
    }


def _recency_bonus(year: int | None) -> float:
    if year is None:
        return 0.0
    if year >= 2024:
        return 0.2
    if year >= 2020:
        return 0.1
    return 0.0


STOPWORDS = {
    "and",
    "are",
    "for",
    "from",
    "how",
    "into",
    "its",
    "the",
    "their",
    "this",
    "that",
    "using",
    "with",
}
