import json
from pathlib import Path

from autoresearcher.cli import main
from autoresearcher.comparison.matrix import (
    ComparisonCell,
    ComparisonMatrix,
    ComparisonRow,
    export_comparison_json,
)
from autoresearcher.review.outline import (
    build_literature_review_markdown,
    build_literature_review_outline,
    export_literature_review_json,
    export_literature_review_markdown,
    load_comparison_matrix_json,
)


def test_build_literature_review_outline_uses_matrix_content_only():
    matrix = _matrix()

    outline = build_literature_review_outline([matrix], title="RAG Review")

    assert outline.title == "RAG Review"
    assert outline.paper_titles == ["Paper A", "Paper B"]
    assert outline.sections[0].title == "Problem Framing"
    problem_points = outline.sections[0].points
    assert "Paper A: Evaluate RAG retrieval failures." in problem_points[0].text
    assert "Paper B: Evaluate RAG retrieval failures." in problem_points[0].text
    assert all("research idea" not in point.text.casefold() for section in outline.sections for point in section.points)


def test_outline_preserves_not_comparable_fields():
    outline = build_literature_review_outline([_matrix()])

    evaluation = next(section for section in outline.sections if section.title == "Evaluation Setup")

    assert any("Baselines: not comparable" in item for item in evaluation.missing_or_not_comparable)
    assert any("Some dimensions are missing or not comparable" in item for item in outline.limitations)


def test_outline_builds_grounded_topic_clusters():
    outline = build_literature_review_outline([_matrix()])

    clusters = {(cluster.dimension, cluster.value) for cluster in outline.clusters}

    assert ("Research Problem", "Evaluate RAG retrieval failures.") in clusters
    assert ("Method", "Retry retrieval when evidence is weak.") in clusters


def test_build_literature_review_markdown_is_review_oriented():
    markdown = build_literature_review_markdown(build_literature_review_outline([_matrix()]))

    assert markdown.startswith("# Literature Review Outline")
    assert "## Topic Clusters" in markdown
    assert "## Problem Framing" in markdown
    assert "## Evaluation Setup" in markdown
    assert "not comparable" in markdown
    assert "Research Idea Card" not in markdown


def test_review_outline_json_and_markdown_exports(tmp_path: Path):
    outline = build_literature_review_outline([_matrix()])

    json_path = export_literature_review_json(outline, tmp_path / "outline.json")
    markdown_path = export_literature_review_markdown(outline, tmp_path / "outline.md")

    assert json.loads(json_path.read_text(encoding="utf-8"))["title"] == "Literature Review Outline"
    assert markdown_path.read_text(encoding="utf-8").startswith("# Literature Review Outline")


def test_load_comparison_matrix_json(tmp_path: Path):
    matrix_path = export_comparison_json(_matrix(), tmp_path / "matrix.json")

    loaded = load_comparison_matrix_json(matrix_path)

    assert loaded.paper_titles == ["Paper A", "Paper B"]


def test_cli_review_outline_command(tmp_path: Path):
    matrix_path = export_comparison_json(_matrix(), tmp_path / "matrix.json")
    markdown_path = tmp_path / "outline.md"
    json_path = tmp_path / "outline.json"

    rc = main(
        [
            "review-outline",
            "--matrix",
            str(matrix_path),
            "--title",
            "RAG Review",
            "--output",
            str(markdown_path),
            "--json-output",
            str(json_path),
        ]
    )

    assert rc == 0
    assert markdown_path.read_text(encoding="utf-8").startswith("# RAG Review")
    assert json.loads(json_path.read_text(encoding="utf-8"))["title"] == "RAG Review"


def _matrix() -> ComparisonMatrix:
    return ComparisonMatrix(
        paper_titles=["Paper A", "Paper B"],
        rows=[
            ComparisonRow(
                dimension="problem",
                label="Research Problem",
                comparability="comparable: same reported value",
                cells=[
                    _cell("Paper A", "Evaluate RAG retrieval failures."),
                    _cell("Paper B", "Evaluate RAG retrieval failures."),
                ],
            ),
            ComparisonRow(
                dimension="motivation",
                label="Motivation",
                comparability="comparable: different reported values",
                cells=[
                    _cell("Paper A", "Retrieval failures cause unsupported answers."),
                    _cell("Paper B", "Grounded QA needs corrective retrieval."),
                ],
            ),
            ComparisonRow(
                dimension="method",
                label="Method",
                comparability="comparable: same reported value",
                cells=[
                    _cell("Paper A", "Retry retrieval when evidence is weak."),
                    _cell("Paper B", "Retry retrieval when evidence is weak."),
                ],
            ),
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
                comparability="not comparable",
                cells=[
                    _cell("Paper A", "BM25."),
                    _cell("Paper B", "not specified", evidence_count=0),
                ],
            ),
            ComparisonRow(
                dimension="main_results",
                label="Main Results",
                comparability="not comparable",
                cells=[
                    _cell("Paper A", "not specified", evidence_count=0),
                    _cell("Paper B", "not specified", evidence_count=0),
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
                dimension="reproduction_notes",
                label="Reproduction Notes",
                comparability="comparable: different reported values",
                cells=[
                    _cell("Paper A", "Requires retriever logs."),
                    _cell("Paper B", "Requires QA labels."),
                ],
            ),
            ComparisonRow(
                dimension="possible_extensions",
                label="Possible Extensions",
                comparability="not comparable",
                cells=[
                    _cell("Paper A", "not specified", evidence_count=0),
                    _cell("Paper B", "not specified", evidence_count=0),
                ],
            ),
        ],
    )


def _cell(title: str, value: str, evidence_count: int = 1) -> ComparisonCell:
    evidence = [] if evidence_count == 0 else [f"[abstract] {value} Reason: fixture"]
    return ComparisonCell(
        paper_title=title,
        value=value,
        evidence_count=evidence_count,
        evidence=evidence,
    )
