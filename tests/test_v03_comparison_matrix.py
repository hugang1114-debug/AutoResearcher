import json
from pathlib import Path

import pytest

from autoresearcher.analyzers.llm_client import NOT_SPECIFIED
from autoresearcher.analyzers.paper_analyzer import PaperAnalysisResult, PaperCard
from autoresearcher.cli import main
from autoresearcher.comparison.matrix import (
    NOT_COMPARABLE,
    build_comparison_markdown,
    build_comparison_matrix,
    export_comparison_json,
    export_comparison_markdown,
    load_paper_card_json,
)


def test_build_comparison_matrix_from_paper_cards():
    cards = [
        PaperCard(analysis=PaperAnalysisResult.model_validate(_payload("Paper A", method="Retry retrieval."))),
        PaperCard(analysis=PaperAnalysisResult.model_validate(_payload("Paper B", method="Rerank retrieved passages."))),
    ]

    matrix = build_comparison_matrix(cards)

    assert matrix.paper_titles == ["Paper A", "Paper B"]
    method = _row(matrix, "method")
    assert method.comparability == "comparable: different reported values"
    assert method.cells[0].value == "Retry retrieval."
    assert method.cells[0].evidence_count == 1


def test_comparison_matrix_marks_not_comparable_when_evidence_is_missing():
    first = PaperAnalysisResult.model_validate(_payload("Paper A", metrics="Exact match."))
    second_payload = _payload("Paper B")
    second_payload["metrics"] = {"claim": NOT_SPECIFIED, "evidence": []}
    second = PaperAnalysisResult.model_validate(second_payload)

    matrix = build_comparison_matrix([first, second])

    metrics = _row(matrix, "metrics")
    assert metrics.comparability == NOT_COMPARABLE
    assert metrics.cells[1].value == NOT_SPECIFIED


def test_comparison_matrix_requires_multiple_cards():
    with pytest.raises(ValueError):
        build_comparison_matrix([PaperAnalysisResult.model_validate(_payload("Only Paper"))])


def test_comparison_markdown_is_review_friendly_and_not_idea_output():
    matrix = build_comparison_matrix(
        [
            PaperAnalysisResult.model_validate(_payload("Paper A")),
            PaperAnalysisResult.model_validate(_payload("Paper B", datasets="HotpotQA.")),
        ]
    )

    markdown = build_comparison_markdown(matrix)

    assert "# Multi-paper Comparison Matrix" in markdown
    assert "## Matrix" in markdown
    assert "## Evidence Notes" in markdown
    assert "Research Problem" in markdown
    assert NOT_COMPARABLE in markdown
    assert "Research Idea" not in markdown


def test_comparison_json_and_markdown_exports(tmp_path: Path):
    matrix = build_comparison_matrix(
        [
            PaperAnalysisResult.model_validate(_payload("Paper A")),
            PaperAnalysisResult.model_validate(_payload("Paper B", baselines="BM25.")),
        ]
    )

    json_path = export_comparison_json(matrix, tmp_path / "matrix.json")
    markdown_path = export_comparison_markdown(matrix, tmp_path / "matrix.md")

    assert json.loads(json_path.read_text(encoding="utf-8"))["paper_titles"] == ["Paper A", "Paper B"]
    assert markdown_path.read_text(encoding="utf-8").startswith("# Multi-paper Comparison Matrix")


def test_load_paper_card_json_accepts_card_or_analysis_payload(tmp_path: Path):
    analysis_path = tmp_path / "analysis.json"
    card_path = tmp_path / "card.json"
    payload = _payload("Paper A")
    analysis_path.write_text(json.dumps(payload), encoding="utf-8")
    card_path.write_text(json.dumps({"analysis": payload, "metadata": {"source": "test"}}), encoding="utf-8")

    analysis_card = load_paper_card_json(analysis_path)
    full_card = load_paper_card_json(card_path)

    assert analysis_card.analysis.title == "Paper A"
    assert full_card.metadata == {"source": "test"}


def test_cli_compare_command_writes_json_and_markdown(tmp_path: Path):
    first = tmp_path / "paper_a.json"
    second = tmp_path / "paper_b.json"
    json_output = tmp_path / "comparison.json"
    markdown_output = tmp_path / "comparison.md"
    first.write_text(json.dumps(_payload("Paper A")), encoding="utf-8")
    second.write_text(json.dumps(_payload("Paper B", limitations="Only English QA.")), encoding="utf-8")

    rc = main(
        [
            "compare",
            "--input",
            str(first),
            "--input",
            str(second),
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
        ]
    )

    assert rc == 0
    assert json_output.exists()
    assert markdown_output.exists()
    assert "# Multi-paper Comparison Matrix" in markdown_output.read_text(encoding="utf-8")


def _row(matrix, dimension):
    return next(row for row in matrix.rows if row.dimension == dimension)


def _payload(title: str, **overrides):
    def claim(value: str, section: str = "abstract"):
        if value == NOT_SPECIFIED:
            return {"claim": NOT_SPECIFIED, "evidence": []}
        return {
            "claim": value,
            "evidence": [
                {
                    "source_section": section,
                    "text": value,
                    "reason": f"The paper card states: {value}",
                }
            ],
        }

    values = {
        "problem": "Evaluate retrieval failures in RAG.",
        "motivation": "Retrieval failures cause unsupported answers.",
        "method": "Retry retrieval.",
        "datasets": "Natural Questions.",
        "metrics": "Exact match.",
        "baselines": NOT_SPECIFIED,
        "main_results": "Improves answer grounding.",
        "limitations": NOT_SPECIFIED,
        "reproduction_notes": "Requires retriever logs.",
        "possible_extensions": NOT_SPECIFIED,
    }
    values.update(overrides)
    return {
        "title": title,
        **{
            field: claim(value, "limitation" if field == "limitations" else "abstract")
            for field, value in values.items()
        },
        "confidence": {
            "level": "medium",
            "score": 0.6,
            "missing_information": [
                field for field, value in values.items() if value == NOT_SPECIFIED
            ],
            "rationale": "Test fixture.",
        },
    }
