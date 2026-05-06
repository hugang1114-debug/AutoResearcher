from __future__ import annotations

from pathlib import Path

from autoresearcher.analyzers.llm_client import NOT_SPECIFIED
from autoresearcher.analyzers.paper_analyzer import (
    ANALYSIS_CLAIM_FIELDS,
    EvidenceBackedClaim,
    PaperCard,
)


SECTION_TITLES = {
    "problem": "Research Problem",
    "motivation": "Motivation",
    "method": "Method",
    "datasets": "Datasets",
    "metrics": "Metrics",
    "baselines": "Baselines",
    "main_results": "Main Results",
    "limitations": "Limitations",
    "reproduction_notes": "Reproduction Notes",
    "possible_extensions": "Possible Extensions",
}


def build_paper_card_markdown(card: PaperCard) -> str:
    analysis = card.analysis
    lines = [
        f"# Paper Card: {analysis.title}",
        "",
        "## Basic Information",
        "",
        *(_metadata_lines(card) or ["- not specified"]),
        "",
    ]
    for field in ANALYSIS_CLAIM_FIELDS:
        lines.extend(_claim_section(SECTION_TITLES[field], getattr(analysis, field)))
    lines.extend(
        [
            "## Evidence Table",
            "",
            "| Field | Source Section | Evidence | Reason |",
            "| --- | --- | --- | --- |",
        ]
    )
    evidence_rows = _evidence_rows(card)
    lines.extend(evidence_rows or [f"| {NOT_SPECIFIED} | unknown | {NOT_SPECIFIED} | {NOT_SPECIFIED} |"])
    lines.extend(
        [
            "",
            "## Confidence and Missing Information",
            "",
            f"- Level: {analysis.confidence.level}",
            f"- Score: {analysis.confidence.score:.2f}",
            f"- Rationale: {analysis.confidence.rationale}",
            "- Missing information: "
            + (
                ", ".join(analysis.confidence.missing_information)
                if analysis.confidence.missing_information
                else NOT_SPECIFIED
            ),
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def export_paper_card_markdown(card: PaperCard, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_paper_card_markdown(card), encoding="utf-8")
    return path


def _metadata_lines(card: PaperCard) -> list[str]:
    metadata = {key: value for key, value in card.metadata.items() if value not in (None, "")}
    lines = [f"- Title: {card.analysis.title}"]
    for key in sorted(metadata):
        if key == "title":
            continue
        lines.append(f"- {key}: {metadata[key]}")
    return lines


def _claim_section(title: str, claim: EvidenceBackedClaim) -> list[str]:
    return [
        f"## {title}",
        "",
        claim.claim,
        "",
    ]


def _evidence_rows(card: PaperCard) -> list[str]:
    rows: list[str] = []
    for field in ANALYSIS_CLAIM_FIELDS:
        claim = getattr(card.analysis, field)
        for evidence in claim.evidence:
            rows.append(
                "| "
                + " | ".join(
                    [
                        _escape_table(SECTION_TITLES[field]),
                        _escape_table(evidence.source_section),
                        _escape_table(evidence.text),
                        _escape_table(evidence.reason),
                    ]
                )
                + " |"
            )
    return rows


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")
