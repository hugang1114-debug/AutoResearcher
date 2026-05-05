from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PaperMetadata:
    """Normalized metadata shared by all paper sources."""

    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    url: str = ""
    source: str = ""
    paper_id: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    published_at: str | None = None
    year: int | None = None
    citation_count: int | None = None
    venue: str | None = None
    pdf_url: str | None = None
    relevance_score: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    def source_key(self) -> str:
        """Return a stable key for storage and deduplication."""
        if self.doi:
            return f"doi:{self.doi.lower()}"
        if self.arxiv_id:
            return f"arxiv:{self.arxiv_id.lower()}"
        if self.paper_id:
            return f"{self.source}:{self.paper_id}".lower()
        if self.url:
            return f"url:{self.url.lower()}"
        return f"title:{normalize_text(self.title)}"

    def to_record(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key(),
            "title": self.title,
            "authors": "\n".join(self.authors),
            "abstract": self.abstract,
            "url": self.url,
            "source": self.source,
            "paper_id": self.paper_id,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "published_at": self.published_at,
            "year": self.year,
            "citation_count": self.citation_count,
            "venue": self.venue,
            "pdf_url": self.pdf_url,
            "relevance_score": self.relevance_score,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "PaperMetadata":
        authors = record.get("authors") or ""
        return cls(
            title=record["title"],
            authors=[author for author in authors.split("\n") if author],
            abstract=record.get("abstract") or "",
            url=record.get("url") or "",
            source=record.get("source") or "",
            paper_id=record.get("paper_id"),
            doi=record.get("doi"),
            arxiv_id=record.get("arxiv_id"),
            published_at=record.get("published_at"),
            year=record.get("year"),
            citation_count=record.get("citation_count"),
            venue=record.get("venue"),
            pdf_url=record.get("pdf_url"),
            relevance_score=float(record.get("relevance_score") or 0.0),
        )


def normalize_text(value: str) -> str:
    return " ".join(value.casefold().strip().split())
