from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from autoresearcher.analyzers.llm_client import NOT_SPECIFIED
from autoresearcher.comparison.matrix import (
    NOT_COMPARABLE,
    ComparisonCell,
    ComparisonMatrix,
    ComparisonRow,
)
from autoresearcher.review.outline import LiteratureReviewOutline

GapCategory = Literal[
    "missing_information",
    "not_comparable",
    "evaluation_mismatch",
    "baseline_gap",
    "stated_limitation",
    "extension_direction",
]
GapConfidence = Literal["low", "medium"]
GapEvidenceSource = Literal["comparison_matrix", "review_outline"]


class GapEvidence(BaseModel):
    """Evidence that justifies one candidate research-gap card."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source: GapEvidenceSource
    dimension: str
    paper_title: str = NOT_SPECIFIED
    text: str
    reason: str


class ResearchGapCard(BaseModel):
    """A candidate gap grounded in comparison/review artifacts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    gap_id: str
    category: GapCategory
    title: str
    description: str
    related_papers: list[str] = Field(default_factory=list)
    source_dimensions: list[str] = Field(default_factory=list)
    evidence: list[GapEvidence] = Field(default_factory=list)
    confidence: GapConfidence = "low"


class GapExtractionResult(BaseModel):
    """Structured output for v0.8 research-gap extraction."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    paper_titles: list[str]
    gaps: list[ResearchGapCard] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def extract_research_gaps(
    matrices: Sequence[ComparisonMatrix],
    review_outlines: Sequence[LiteratureReviewOutline] | None = None,
) -> GapExtractionResult:
    """Extract evidence-backed gap candidates without proposing final ideas."""
    if not matrices:
        raise ValueError("At least one comparison matrix is required.")

    gaps: list[ResearchGapCard] = []
    for matrix in matrices:
        for row in matrix.rows:
            gaps.extend(_gaps_from_row(row))

    outlines = list(review_outlines or [])
    if outlines:
        _attach_or_add_outline_gaps(gaps, outlines)

    gaps = _assign_gap_ids(_dedupe_gaps(gaps))
    return GapExtractionResult(
        paper_titles=_paper_titles(matrices, outlines),
        gaps=gaps,
        limitations=_result_limitations(gaps, outlines),
    )


def build_research_gap_markdown(result: GapExtractionResult) -> str:
    """Render gap candidates as a review-friendly Markdown report."""
    lines = [
        "# Research Gap Candidates",
        "",
        "## Papers",
        "",
    ]
    if result.paper_titles:
        lines.extend(f"- {title}" for title in result.paper_titles)
    else:
        lines.append(f"- {NOT_SPECIFIED}")

    lines.extend(["", "## Gap Cards", ""])
    if not result.gaps:
        lines.append(f"- {NOT_SPECIFIED}")
    for gap in result.gaps:
        lines.extend(_gap_markdown_lines(gap))

    lines.extend(["## Extraction Limitations", ""])
    lines.extend(f"- {item}" for item in result.limitations)
    return "\n".join(lines).rstrip() + "\n"


def export_research_gap_json(result: GapExtractionResult, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path


def export_research_gap_markdown(result: GapExtractionResult, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_research_gap_markdown(result), encoding="utf-8")
    return path


def load_literature_review_outline_json(path: str | Path) -> LiteratureReviewOutline:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return LiteratureReviewOutline.model_validate(payload)


def _gaps_from_row(row: ComparisonRow) -> list[ResearchGapCard]:
    gaps: list[ResearchGapCard] = []
    specified = _specified_cells(row)

    if len(specified) < 2 or row.comparability == NOT_COMPARABLE:
        gaps.append(_missing_or_not_comparable_gap(row, specified))

    if row.dimension in {"datasets", "metrics"} and _is_different_comparison(row):
        gaps.append(_evaluation_mismatch_gap(row, specified))

    if row.dimension == "baselines" and specified and (
        row.comparability == NOT_COMPARABLE or _is_different_comparison(row)
    ):
        gaps.append(_baseline_gap(row, specified))

    if row.dimension == "limitations":
        gaps.extend(_stated_limitation_gap(row, cell) for cell in specified)

    if row.dimension == "possible_extensions":
        gaps.extend(_extension_direction_gap(row, cell) for cell in specified)

    return gaps


def _missing_or_not_comparable_gap(
    row: ComparisonRow,
    specified: list[ComparisonCell],
) -> ResearchGapCard:
    category: GapCategory = "not_comparable" if row.comparability == NOT_COMPARABLE else "missing_information"
    specified_count = len(specified)
    description = (
        f"The comparison matrix cannot support a substantive cross-paper conclusion for "
        f"{row.label} because {specified_count} paper(s) provide specified values. "
        "Treat this as a reporting or extraction gap, not as a proposed method."
    )
    return ResearchGapCard(
        gap_id="pending",
        category=category,
        title=f"Insufficient comparable evidence for {row.label}",
        description=description,
        related_papers=_dedupe([cell.paper_title for cell in row.cells]),
        source_dimensions=[row.label],
        evidence=_row_evidence(row, row.cells),
        confidence="low",
    )


def _evaluation_mismatch_gap(
    row: ComparisonRow,
    specified: list[ComparisonCell],
) -> ResearchGapCard:
    return ResearchGapCard(
        gap_id="pending",
        category="evaluation_mismatch",
        title=f"Different reported {row.label.lower()} across papers",
        description=(
            f"The compared papers report different {row.label.lower()}, so their "
            "evaluation setups may not be directly comparable. This card only records "
            "the observed mismatch."
        ),
        related_papers=_dedupe([cell.paper_title for cell in specified]),
        source_dimensions=[row.label],
        evidence=_row_evidence(row, specified),
        confidence=_confidence_from_cells(specified),
    )


def _baseline_gap(
    row: ComparisonRow,
    specified: list[ComparisonCell],
) -> ResearchGapCard:
    return ResearchGapCard(
        gap_id="pending",
        category="baseline_gap",
        title="Baseline reporting or comparison gap",
        description=(
            "The comparison matrix shows baseline information that is incomplete or "
            "reported differently across papers. This limits direct comparison until "
            "the original papers are checked."
        ),
        related_papers=_dedupe([cell.paper_title for cell in row.cells]),
        source_dimensions=[row.label],
        evidence=_row_evidence(row, row.cells),
        confidence="low" if row.comparability == NOT_COMPARABLE else _confidence_from_cells(specified),
    )


def _stated_limitation_gap(row: ComparisonRow, cell: ComparisonCell) -> ResearchGapCard:
    return ResearchGapCard(
        gap_id="pending",
        category="stated_limitation",
        title=f"Stated limitation in {cell.paper_title}",
        description=(
            f"The paper card reports this limitation: {cell.value} "
            "This is a candidate gap only because it is stated in the source card."
        ),
        related_papers=[cell.paper_title],
        source_dimensions=[row.label],
        evidence=_cell_evidence(row, cell),
        confidence=_confidence_from_cells([cell]),
    )


def _extension_direction_gap(row: ComparisonRow, cell: ComparisonCell) -> ResearchGapCard:
    return ResearchGapCard(
        gap_id="pending",
        category="extension_direction",
        title=f"Grounded extension direction from {cell.paper_title}",
        description=(
            f"The paper card reports this possible extension: {cell.value} "
            "This records an observed follow-up direction, not a validated plan."
        ),
        related_papers=[cell.paper_title],
        source_dimensions=[row.label],
        evidence=_cell_evidence(row, cell),
        confidence=_confidence_from_cells([cell]),
    )


def _attach_or_add_outline_gaps(
    gaps: list[ResearchGapCard],
    outlines: Sequence[LiteratureReviewOutline],
) -> None:
    for outline in outlines:
        for section in outline.sections:
            for item in section.missing_or_not_comparable:
                dimension = _dimension_from_outline_item(item)
                evidence = GapEvidence(
                    source="review_outline",
                    dimension=dimension,
                    text=item,
                    reason=(
                        "The literature review outline explicitly marks this "
                        "dimension as missing or not comparable."
                    ),
                )
                existing = _find_matching_gap(gaps, dimension)
                if existing is not None:
                    existing.evidence.append(evidence)
                    existing.related_papers = _dedupe([*existing.related_papers, *outline.paper_titles])
                    continue
                gaps.append(
                    ResearchGapCard(
                        gap_id="pending",
                        category="not_comparable",
                        title=f"Outline-level missing comparison for {dimension}",
                        description=(
                            f"The review outline reports: {item} "
                            "This is a review-planning gap, not a proposed method."
                        ),
                        related_papers=outline.paper_titles,
                        source_dimensions=[dimension],
                        evidence=[evidence],
                        confidence="low",
                    )
                )


def _find_matching_gap(gaps: list[ResearchGapCard], dimension: str) -> ResearchGapCard | None:
    for gap in gaps:
        if (
            dimension in gap.source_dimensions
            and gap.category in {"missing_information", "not_comparable", "baseline_gap"}
        ):
            return gap
    return None


def _dimension_from_outline_item(item: str) -> str:
    return item.split(":", 1)[0].strip() or "unknown"


def _specified_cells(row: ComparisonRow) -> list[ComparisonCell]:
    return [cell for cell in row.cells if _is_specified(cell.value)]


def _is_specified(value: str) -> bool:
    return value.strip().casefold() != NOT_SPECIFIED


def _is_different_comparison(row: ComparisonRow) -> bool:
    return row.comparability == "comparable: different reported values"


def _row_evidence(row: ComparisonRow, cells: Sequence[ComparisonCell]) -> list[GapEvidence]:
    evidence: list[GapEvidence] = []
    for cell in cells:
        evidence.extend(_cell_evidence(row, cell))
    return evidence


def _cell_evidence(row: ComparisonRow, cell: ComparisonCell) -> list[GapEvidence]:
    if cell.evidence:
        return [
            GapEvidence(
                source="comparison_matrix",
                dimension=row.label,
                paper_title=cell.paper_title,
                text=text,
                reason=f"The comparison matrix cites this evidence for {row.label}.",
            )
            for text in cell.evidence
        ]
    reason = (
        f"The paper card does not provide specified information for {row.label}."
        if not _is_specified(cell.value)
        else f"The comparison matrix reports a value for {row.label} without a source span."
    )
    return [
        GapEvidence(
            source="comparison_matrix",
            dimension=row.label,
            paper_title=cell.paper_title,
            text=cell.value,
            reason=reason,
        )
    ]


def _confidence_from_cells(cells: Sequence[ComparisonCell]) -> GapConfidence:
    if cells and all(cell.evidence_count > 0 or cell.evidence for cell in cells):
        return "medium"
    return "low"


def _dedupe_gaps(gaps: list[ResearchGapCard]) -> list[ResearchGapCard]:
    deduped: list[ResearchGapCard] = []
    seen: set[tuple[str, str, str, tuple[str, ...]]] = set()
    for gap in gaps:
        key = (
            gap.category,
            gap.title.casefold(),
            gap.description.casefold(),
            tuple(sorted(gap.source_dimensions)),
        )
        if key in seen:
            continue
        seen.add(key)
        gap.related_papers = _dedupe(gap.related_papers)
        gap.source_dimensions = _dedupe(gap.source_dimensions)
        gap.evidence = _dedupe_evidence(gap.evidence)
        deduped.append(gap)
    return deduped


def _dedupe_evidence(evidence: Sequence[GapEvidence]) -> list[GapEvidence]:
    deduped: list[GapEvidence] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in evidence:
        key = (item.source, item.dimension, item.paper_title, item.text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _assign_gap_ids(gaps: list[ResearchGapCard]) -> list[ResearchGapCard]:
    return [
        gap.model_copy(update={"gap_id": f"GAP-{index:03d}"})
        for index, gap in enumerate(gaps, start=1)
    ]


def _paper_titles(
    matrices: Sequence[ComparisonMatrix],
    outlines: Sequence[LiteratureReviewOutline],
) -> list[str]:
    return _dedupe(
        [
            title
            for source in [*[matrix.paper_titles for matrix in matrices], *[outline.paper_titles for outline in outlines]]
            for title in source
        ]
    )


def _result_limitations(
    gaps: Sequence[ResearchGapCard],
    outlines: Sequence[LiteratureReviewOutline],
) -> list[str]:
    limitations = [
        "Gap extraction only uses comparison matrices and optional literature review outlines.",
        "Candidate gaps require manual validation against the original papers.",
        "This output does not generate proposed methods, experiments, or final research ideas.",
    ]
    if any(gap.confidence == "low" for gap in gaps):
        limitations.append("Low-confidence gaps usually indicate missing or weak evidence.")
    if not outlines:
        limitations.append("No literature review outline was provided for additional context.")
    return limitations


def _gap_markdown_lines(gap: ResearchGapCard) -> list[str]:
    lines = [
        f"### {gap.gap_id}: {gap.title}",
        "",
        f"- category: {gap.category}",
        f"- related_papers: {_join_or_not_specified(gap.related_papers)}",
        f"- source_dimensions: {_join_or_not_specified(gap.source_dimensions)}",
        f"- confidence: {gap.confidence}",
        f"- description: {gap.description}",
        "",
        "| Source | Dimension | Paper | Evidence | Reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    if gap.evidence:
        for evidence in gap.evidence:
            lines.append(
                "| "
                + " | ".join(
                    _escape_table(value)
                    for value in [
                        evidence.source,
                        evidence.dimension,
                        evidence.paper_title,
                        evidence.text,
                        evidence.reason,
                    ]
                )
                + " |"
            )
    else:
        lines.append(f"| {NOT_SPECIFIED} | {NOT_SPECIFIED} | {NOT_SPECIFIED} | {NOT_SPECIFIED} | {NOT_SPECIFIED} |")
    lines.append("")
    return lines


def _join_or_not_specified(values: Sequence[str]) -> str:
    return ", ".join(values) if values else NOT_SPECIFIED


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))
