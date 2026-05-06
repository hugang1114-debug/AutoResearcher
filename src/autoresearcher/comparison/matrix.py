from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field

from autoresearcher.analyzers.llm_client import NOT_SPECIFIED
from autoresearcher.analyzers.paper_analyzer import (
    ANALYSIS_CLAIM_FIELDS,
    EvidenceBackedClaim,
    PaperAnalysisResult,
    PaperCard,
)

NOT_COMPARABLE = "not comparable"

COMPARISON_DIMENSIONS = {
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


class ComparisonCell(BaseModel):
    """One paper's value for one comparison dimension."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    paper_title: str
    value: str = NOT_SPECIFIED
    evidence_count: int = 0
    evidence: list[str] = Field(default_factory=list)


class ComparisonRow(BaseModel):
    """Comparison data for one dimension across all papers."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    dimension: str
    label: str
    cells: list[ComparisonCell]
    comparability: str


class ComparisonMatrix(BaseModel):
    """Multi-paper comparison matrix."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    paper_titles: list[str]
    rows: list[ComparisonRow]


def build_comparison_matrix(
    paper_cards: Sequence[PaperCard | PaperAnalysisResult],
) -> ComparisonMatrix:
    """Build a deterministic comparison matrix from v0.2 paper cards."""
    cards = [_normalize_card(item) for item in paper_cards]
    if len(cards) < 2:
        raise ValueError("At least two paper cards are required for comparison.")
    rows = [
        _build_row(field, cards)
        for field in ANALYSIS_CLAIM_FIELDS
        if field in COMPARISON_DIMENSIONS
    ]
    return ComparisonMatrix(
        paper_titles=[card.analysis.title for card in cards],
        rows=rows,
    )


def build_comparison_markdown(matrix: ComparisonMatrix) -> str:
    lines = [
        "# Multi-paper Comparison Matrix",
        "",
        "## Papers",
        "",
    ]
    lines.extend(f"- {title}" for title in matrix.paper_titles)
    lines.extend(
        [
            "",
            "## Matrix",
            "",
            _matrix_table(matrix),
            "",
            "## Evidence Notes",
            "",
        ]
    )
    for row in matrix.rows:
        lines.extend(_evidence_note_lines(row))
    return "\n".join(lines).rstrip() + "\n"


def export_comparison_json(matrix: ComparisonMatrix, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(matrix.model_dump_json(indent=2), encoding="utf-8")
    return path


def export_comparison_markdown(matrix: ComparisonMatrix, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_comparison_markdown(matrix), encoding="utf-8")
    return path


def load_paper_card_json(path: str | Path) -> PaperCard:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return paper_card_from_json_payload(payload)


def paper_card_from_json_payload(payload: dict[str, Any]) -> PaperCard:
    if "analysis" in payload:
        return PaperCard.model_validate(payload)
    return PaperCard(analysis=PaperAnalysisResult.model_validate(payload))


def _build_row(field: str, cards: list[PaperCard]) -> ComparisonRow:
    cells = [_build_cell(card, field) for card in cards]
    return ComparisonRow(
        dimension=field,
        label=COMPARISON_DIMENSIONS[field],
        cells=cells,
        comparability=_comparability(cells),
    )


def _build_cell(card: PaperCard, field: str) -> ComparisonCell:
    claim: EvidenceBackedClaim = getattr(card.analysis, field)
    value = claim.claim
    return ComparisonCell(
        paper_title=card.analysis.title,
        value=value,
        evidence_count=len(claim.evidence),
        evidence=[
            f"[{span.source_section}] {span.text} Reason: {span.reason}"
            for span in claim.evidence
        ],
    )


def _comparability(cells: list[ComparisonCell]) -> str:
    specified = [cell.value for cell in cells if cell.value != NOT_SPECIFIED]
    if len(specified) < 2:
        return NOT_COMPARABLE
    unique_values = {value.casefold() for value in specified}
    if len(unique_values) == 1:
        return "comparable: same reported value"
    return "comparable: different reported values"


def _normalize_card(item: PaperCard | PaperAnalysisResult) -> PaperCard:
    if isinstance(item, PaperCard):
        return item
    return PaperCard(analysis=item)


def _matrix_table(matrix: ComparisonMatrix) -> str:
    headers = ["Dimension", *matrix.paper_titles, "Comparability"]
    separator = ["---"] * len(headers)
    lines = [
        "| " + " | ".join(_escape_table(header) for header in headers) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in matrix.rows:
        values = [row.label, *[cell.value for cell in row.cells], row.comparability]
        lines.append("| " + " | ".join(_escape_table(value) for value in values) + " |")
    return "\n".join(lines)


def _evidence_note_lines(row: ComparisonRow) -> list[str]:
    lines = [f"### {row.label}", "", f"- Comparability: {row.comparability}"]
    for cell in row.cells:
        lines.append(f"- {cell.paper_title}: {cell.value}")
        if cell.evidence:
            for evidence in cell.evidence:
                lines.append(f"  - Evidence: {evidence}")
        else:
            lines.append(f"  - Evidence: {NOT_SPECIFIED}")
    lines.append("")
    return lines


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")
