from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from autoresearcher.analyzers.llm_client import NOT_SPECIFIED
from autoresearcher.comparison.matrix import (
    NOT_COMPARABLE,
    ComparisonMatrix,
    ComparisonRow,
)


class ReviewPoint(BaseModel):
    """One outline point grounded in comparison-matrix content."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    dimension: str
    text: str
    related_papers: list[str] = Field(default_factory=list)


class ReviewSection(BaseModel):
    """Review-oriented section containing grounded comparison points."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str
    purpose: str
    points: list[ReviewPoint] = Field(default_factory=list)
    missing_or_not_comparable: list[str] = Field(default_factory=list)


class ReviewCluster(BaseModel):
    """A shared-value cluster grounded in one comparison dimension."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    dimension: str
    value: str
    papers: list[str]


class LiteratureReviewOutline(BaseModel):
    """A deterministic literature review outline built from comparison matrices."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = "Literature Review Outline"
    paper_titles: list[str]
    sections: list[ReviewSection]
    clusters: list[ReviewCluster] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def build_literature_review_outline(
    matrices: Sequence[ComparisonMatrix],
    title: str = "Literature Review Outline",
) -> LiteratureReviewOutline:
    if not matrices:
        raise ValueError("At least one comparison matrix is required.")
    rows = _rows_by_dimension(matrices)
    sections = [
        _build_section(
            "Problem Framing",
            "Use this section to describe what the compared papers study and why it matters.",
            ["problem", "motivation"],
            rows,
        ),
        _build_section(
            "Method Families",
            "Use this section to organize the methods explicitly reported in the paper cards.",
            ["method"],
            rows,
        ),
        _build_section(
            "Evaluation Setup",
            "Use this section to summarize datasets, metrics, and baselines.",
            ["datasets", "metrics", "baselines"],
            rows,
        ),
        _build_section(
            "Findings and Limitations",
            "Use this section to summarize reported results and stated limitations.",
            ["main_results", "limitations"],
            rows,
        ),
        _build_section(
            "Reproduction and Follow-up Notes",
            "Use this section to preserve reproduction notes and observed extension directions.",
            ["reproduction_notes", "possible_extensions"],
            rows,
        ),
    ]
    paper_titles = list(dict.fromkeys(title for matrix in matrices for title in matrix.paper_titles))
    return LiteratureReviewOutline(
        title=title,
        paper_titles=paper_titles,
        sections=sections,
        clusters=_build_clusters(rows),
        limitations=_outline_limitations(sections),
    )


def build_literature_review_markdown(outline: LiteratureReviewOutline) -> str:
    lines = [
        f"# {outline.title}",
        "",
        "## Papers",
        "",
    ]
    lines.extend(f"- {paper}" for paper in outline.paper_titles)
    lines.extend(["", "## Topic Clusters", ""])
    if outline.clusters:
        for cluster in outline.clusters:
            lines.append(
                f"- {cluster.dimension}: {cluster.value} "
                f"({', '.join(cluster.papers)})"
            )
    else:
        lines.append(f"- {NOT_SPECIFIED}")
    lines.append("")
    for section in outline.sections:
        lines.extend(_section_lines(section))
    lines.extend(["## Limitations of This Outline", ""])
    lines.extend(f"- {item}" for item in outline.limitations)
    return "\n".join(lines).rstrip() + "\n"


def export_literature_review_json(
    outline: LiteratureReviewOutline,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(outline.model_dump_json(indent=2), encoding="utf-8")
    return path


def export_literature_review_markdown(
    outline: LiteratureReviewOutline,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_literature_review_markdown(outline), encoding="utf-8")
    return path


def load_comparison_matrix_json(path: str | Path) -> ComparisonMatrix:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ComparisonMatrix.model_validate(payload)


def _rows_by_dimension(matrices: Sequence[ComparisonMatrix]) -> dict[str, list[ComparisonRow]]:
    rows: dict[str, list[ComparisonRow]] = defaultdict(list)
    for matrix in matrices:
        for row in matrix.rows:
            rows[row.dimension].append(row)
    return dict(rows)


def _build_section(
    title: str,
    purpose: str,
    dimensions: list[str],
    rows: dict[str, list[ComparisonRow]],
) -> ReviewSection:
    points: list[ReviewPoint] = []
    missing_or_not_comparable: list[str] = []
    for dimension in dimensions:
        for row in rows.get(dimension, []):
            specified = [
                cell
                for cell in row.cells
                if cell.value != NOT_SPECIFIED
            ]
            if len(specified) < 2 or row.comparability == NOT_COMPARABLE:
                missing_or_not_comparable.append(
                    f"{row.label}: {NOT_COMPARABLE}; "
                    f"{len(specified)} paper(s) provide comparable information."
                )
            if specified:
                points.append(
                    ReviewPoint(
                        dimension=row.label,
                        text=_row_summary(row, specified),
                        related_papers=[cell.paper_title for cell in specified],
                    )
                )
            else:
                points.append(
                    ReviewPoint(
                        dimension=row.label,
                        text=f"{row.label}: {NOT_SPECIFIED}",
                        related_papers=[],
                    )
                )
    return ReviewSection(
        title=title,
        purpose=purpose,
        points=points,
        missing_or_not_comparable=missing_or_not_comparable,
    )


def _row_summary(row: ComparisonRow, cells) -> str:
    claims = "; ".join(f"{cell.paper_title}: {cell.value}" for cell in cells)
    return f"{row.label}: {claims}. Comparability: {row.comparability}."


def _build_clusters(rows: dict[str, list[ComparisonRow]]) -> list[ReviewCluster]:
    clusters: list[ReviewCluster] = []
    for row_list in rows.values():
        for row in row_list:
            grouped: dict[str, list[str]] = defaultdict(list)
            value_by_key: dict[str, str] = {}
            for cell in row.cells:
                if cell.value == NOT_SPECIFIED:
                    continue
                key = cell.value.casefold()
                grouped[key].append(cell.paper_title)
                value_by_key[key] = cell.value
            for key, papers in grouped.items():
                if len(papers) >= 2:
                    clusters.append(
                        ReviewCluster(
                            dimension=row.label,
                            value=value_by_key[key],
                            papers=papers,
                        )
                    )
    return clusters


def _outline_limitations(sections: list[ReviewSection]) -> list[str]:
    limitations = [
        "This outline only uses comparison-matrix content.",
        "It does not generate final research ideas or claim novelty.",
    ]
    if any(section.missing_or_not_comparable for section in sections):
        limitations.append(
            "Some dimensions are missing or not comparable and must be checked manually."
        )
    return limitations


def _section_lines(section: ReviewSection) -> list[str]:
    lines = [
        f"## {section.title}",
        "",
        f"Purpose: {section.purpose}",
        "",
    ]
    if section.points:
        lines.extend(f"- {point.text}" for point in section.points)
    else:
        lines.append(f"- {NOT_SPECIFIED}")
    if section.missing_or_not_comparable:
        lines.extend(["", "Missing or not comparable:"])
        lines.extend(f"- {item}" for item in section.missing_or_not_comparable)
    lines.append("")
    return lines
