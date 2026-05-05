from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from autoresearcher.clients.arxiv import search_arxiv
from autoresearcher.clients.semantic_scholar import search_semantic_scholar
from autoresearcher.dedupe import deduplicate_papers
from autoresearcher.models import PaperMetadata
from autoresearcher.ranking import rank_papers
from autoresearcher.report import export_markdown_report
from autoresearcher.storage import PaperStore


@dataclass(slots=True)
class PipelineResult:
    topic: str
    papers: list[PaperMetadata]
    db_path: Path
    report_path: Path
    errors: list[str] = field(default_factory=list)


def run_research_pipeline(
    topic: str,
    limit: int = 10,
    db_path: str | Path = "data/autoresearcher.sqlite",
    report_path: str | Path = "reports/research_report.md",
) -> PipelineResult:
    """Run the v0.1 search, ranking, persistence, and report pipeline."""
    errors: list[str] = []
    papers: list[PaperMetadata] = []
    for source_name, search in (
        ("arXiv", search_arxiv),
        ("Semantic Scholar", search_semantic_scholar),
    ):
        try:
            papers.extend(search(topic, limit=limit))
        except Exception as exc:  # pragma: no cover - integration resilience
            errors.append(f"{source_name}: {exc}")

    unique_papers = deduplicate_papers(papers)
    ranked_papers = rank_papers(topic, unique_papers)[:limit]

    db = Path(db_path)
    report = Path(report_path)
    with PaperStore(db) as store:
        store.upsert_papers(ranked_papers)
    export_markdown_report(topic, ranked_papers, report)

    return PipelineResult(
        topic=topic,
        papers=ranked_papers,
        db_path=db,
        report_path=report,
        errors=errors,
    )
