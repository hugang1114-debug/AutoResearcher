from __future__ import annotations

from pathlib import Path

from autoresearcher.models import PaperMetadata


def export_markdown_report(topic: str, papers: list[PaperMetadata], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown_report(topic, papers), encoding="utf-8")
    return path


def build_markdown_report(topic: str, papers: list[PaperMetadata]) -> str:
    lines: list[str] = [
        f"# AutoResearcher Report: {topic}",
        "",
        "## Summary",
        "",
        f"- Papers analyzed: {len(papers)}",
        "- Sources: arXiv and Semantic Scholar",
        "",
        "## Top Papers",
        "",
    ]
    for index, paper in enumerate(papers, start=1):
        lines.extend(_paper_section(index, paper))
    lines.extend(
        [
            "## Research Idea Cards",
            "",
            *build_research_idea_cards(topic, papers),
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_research_idea_cards(topic: str, papers: list[PaperMetadata]) -> list[str]:
    if not papers:
        return [
            "### Idea 1: Build a focused survey baseline",
            "",
            f"- Topic: {topic}",
            "- Motivation: No papers were retrieved, so start by refining search terms.",
            "- Next step: Try broader synonyms and rerun AutoResearcher.",
            "",
        ]
    top_titles = [paper.title for paper in papers[:3]]
    return [
        "### Idea 1: Compare assumptions across top papers",
        "",
        f"- Topic: {topic}",
        f"- Evidence: {', '.join(top_titles)}",
        "- Hypothesis: The top papers may optimize for different evaluation settings.",
        "- Next step: Extract datasets, metrics, and baselines into a comparison table.",
        "",
        "### Idea 2: Identify a narrow replication target",
        "",
        f"- Topic: {topic}",
        "- Evidence: Prioritize papers with open PDFs, recent publication years, and clear methods.",
        "- Hypothesis: A small reproduction can reveal hidden implementation constraints.",
        "- Next step: Select one high-ranked paper and map required data, code, and compute.",
        "",
    ]


def _paper_section(index: int, paper: PaperMetadata) -> list[str]:
    authors = ", ".join(paper.authors[:5]) if paper.authors else "Unknown authors"
    if len(paper.authors) > 5:
        authors += ", et al."
    metadata = [
        f"Source: {paper.source or 'unknown'}",
        f"Score: {paper.relevance_score:.4f}",
    ]
    if paper.year:
        metadata.append(f"Year: {paper.year}")
    if paper.citation_count is not None:
        metadata.append(f"Citations: {paper.citation_count}")
    if paper.venue:
        metadata.append(f"Venue: {paper.venue}")
    abstract = paper.abstract or "No abstract available."
    if len(abstract) > 700:
        abstract = abstract[:697].rstrip() + "..."
    lines = [
        f"### {index}. {paper.title}",
        "",
        f"- Authors: {authors}",
        f"- {'; '.join(metadata)}",
    ]
    if paper.url:
        lines.append(f"- URL: {paper.url}")
    if paper.pdf_url:
        lines.append(f"- PDF: {paper.pdf_url}")
    lines.extend(["", abstract, ""])
    return lines
