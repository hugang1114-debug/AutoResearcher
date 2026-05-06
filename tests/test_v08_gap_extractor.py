import json
from pathlib import Path

import pytest

from autoresearcher.analyzers.llm_client import NOT_SPECIFIED
from autoresearcher.cli import main
from autoresearcher.comparison.matrix import (
    NOT_COMPARABLE,
    ComparisonCell,
    ComparisonMatrix,
    ComparisonRow,
    export_comparison_json,
)
from autoresearcher.gaps.extractor import (
    GapEvidence,
    ResearchGapCard,
    build_research_gap_markdown,
    export_research_gap_json,
    export_research_gap_markdown,
    extract_research_gaps,
)
from autoresearcher.review.outline import (
    build_literature_review_outline,
    export_literature_review_json,
)
from autoresearcher.workspace.core import create_workspace, workspace_status


def test_gap_card_schema_requires_grounding_fields():
    card = ResearchGapCard.model_validate(
        {
            "gap_id": "GAP-001",
            "category": "evaluation_mismatch",
            "title": "Different datasets across papers",
            "description": "The matrix reports different datasets.",
            "related_papers": ["Paper A", "Paper B"],
            "source_dimensions": ["Datasets"],
            "evidence": [
                {
                    "source": "comparison_matrix",
                    "dimension": "Datasets",
                    "paper_title": "Paper A",
                    "text": "[experiment] Natural Questions. Reason: fixture",
                    "reason": "The comparison matrix cites this evidence.",
                }
            ],
            "confidence": "medium",
        }
    )

    assert card.gap_id == "GAP-001"
    assert card.evidence[0].dimension == "Datasets"


def test_invalid_gap_category_is_rejected():
    with pytest.raises(ValueError):
        ResearchGapCard(
            gap_id="GAP-001",
            category="unsupported",
            title="Bad gap",
            description="Bad gap",
            evidence=[
                GapEvidence(
                    source="comparison_matrix",
                    dimension="Datasets",
                    text="fixture",
                    reason="fixture",
                )
            ],
        )


def test_extract_research_gaps_is_evidence_backed_and_uses_outline_context():
    matrix = _matrix()
    outline = build_literature_review_outline([matrix])

    result = extract_research_gaps([matrix], [outline])

    categories = {gap.category for gap in result.gaps}
    assert "evaluation_mismatch" in categories
    assert "baseline_gap" in categories
    assert "stated_limitation" in categories
    assert "extension_direction" in categories
    assert all(gap.evidence for gap in result.gaps)
    assert all(gap.source_dimensions for gap in result.gaps)
    assert any(
        evidence.source == "review_outline"
        for gap in result.gaps
        for evidence in gap.evidence
    )


def test_not_specified_rows_become_reporting_gaps_not_fake_claims():
    result = extract_research_gaps([_missing_matrix()])

    gap = result.gaps[0]

    assert gap.category == "not_comparable"
    assert "reporting or extraction gap" in gap.description
    assert all(evidence.text == NOT_SPECIFIED for evidence in gap.evidence)
    assert "proposed_method" not in result.model_dump_json()


def test_research_gap_markdown_and_exports(tmp_path: Path):
    result = extract_research_gaps([_matrix()])

    markdown = build_research_gap_markdown(result)
    json_path = export_research_gap_json(result, tmp_path / "gaps.json")
    markdown_path = export_research_gap_markdown(result, tmp_path / "gaps.md")

    assert markdown.startswith("# Research Gap Candidates")
    assert "| Source | Dimension | Paper | Evidence | Reason |" in markdown
    assert "Research Idea Card" not in markdown
    assert json.loads(json_path.read_text(encoding="utf-8"))["gaps"][0]["gap_id"] == "GAP-001"
    assert markdown_path.read_text(encoding="utf-8").startswith("# Research Gap Candidates")


def test_cli_extract_gaps_command(tmp_path: Path):
    matrix_path = export_comparison_json(_matrix(), tmp_path / "matrix.json")
    outline_path = export_literature_review_json(
        build_literature_review_outline([_matrix()]),
        tmp_path / "outline.json",
    )
    markdown_path = tmp_path / "gaps.md"
    json_path = tmp_path / "gaps.json"

    rc = main(
        [
            "extract-gaps",
            "--matrix",
            str(matrix_path),
            "--review-outline",
            str(outline_path),
            "--output",
            str(markdown_path),
            "--json-output",
            str(json_path),
        ]
    )

    assert rc == 0
    assert markdown_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["gaps"]


def test_cli_workspace_extract_gaps_command(tmp_path: Path):
    workspace = create_workspace("rag-review", root=tmp_path)
    matrix_path = export_comparison_json(_matrix(), Path(workspace.comparisons_dir) / "matrix.json")
    export_literature_review_json(
        build_literature_review_outline([_matrix()]),
        Path(workspace.reviews_dir) / "outline.json",
    )

    rc = main(
        [
            "workspace-extract-gaps",
            "--name",
            workspace.name,
            "--root",
            str(tmp_path),
            "--matrix",
            str(matrix_path),
            "--name-output",
            "rag-gaps",
        ]
    )

    assert rc == 0
    assert (workspace.gaps_path / "rag-gaps.md").exists()
    assert (workspace.gaps_path / "rag-gaps.json").exists()
    assert workspace_status(workspace)["gaps"] == 1


def _matrix() -> ComparisonMatrix:
    return ComparisonMatrix(
        paper_titles=["Paper A", "Paper B"],
        rows=[
            ComparisonRow(
                dimension="datasets",
                label="Datasets",
                comparability="comparable: different reported values",
                cells=[
                    _cell("Paper A", "Natural Questions."),
                    _cell("Paper B", "HotpotQA."),
                ],
            ),
            ComparisonRow(
                dimension="metrics",
                label="Metrics",
                comparability="comparable: same reported value",
                cells=[
                    _cell("Paper A", "Exact match."),
                    _cell("Paper B", "Exact match."),
                ],
            ),
            ComparisonRow(
                dimension="baselines",
                label="Baselines",
                comparability=NOT_COMPARABLE,
                cells=[
                    _cell("Paper A", "BM25."),
                    _cell("Paper B", NOT_SPECIFIED, evidence_count=0),
                ],
            ),
            ComparisonRow(
                dimension="limitations",
                label="Limitations",
                comparability="comparable: different reported values",
                cells=[
                    _cell("Paper A", "Only English QA."),
                    _cell("Paper B", "Small benchmark scale."),
                ],
            ),
            ComparisonRow(
                dimension="possible_extensions",
                label="Possible Extensions",
                comparability=NOT_COMPARABLE,
                cells=[
                    _cell("Paper A", "Evaluate multilingual QA."),
                    _cell("Paper B", NOT_SPECIFIED, evidence_count=0),
                ],
            ),
        ],
    )


def _missing_matrix() -> ComparisonMatrix:
    return ComparisonMatrix(
        paper_titles=["Paper A", "Paper B"],
        rows=[
            ComparisonRow(
                dimension="main_results",
                label="Main Results",
                comparability=NOT_COMPARABLE,
                cells=[
                    _cell("Paper A", NOT_SPECIFIED, evidence_count=0),
                    _cell("Paper B", NOT_SPECIFIED, evidence_count=0),
                ],
            )
        ],
    )


def _cell(title: str, value: str, evidence_count: int = 1) -> ComparisonCell:
    evidence = [] if evidence_count == 0 else [f"[experiment] {value} Reason: fixture"]
    return ComparisonCell(
        paper_title=title,
        value=value,
        evidence_count=evidence_count,
        evidence=evidence,
    )
