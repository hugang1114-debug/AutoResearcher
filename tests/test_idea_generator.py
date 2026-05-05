from pathlib import Path

import pytest

from autoresearcher.idea_generator import (
    IdeaGenerationError,
    build_comparison_table,
    build_idea_markdown_report,
    export_idea_markdown_report,
    generate_research_idea_cards,
    parse_paper_card,
)
from autoresearcher.paper_analyzer import PaperAnalysis, build_paper_card


def test_parse_paper_card_reads_required_comparison_fields():
    card = build_paper_card(
        "RAG | Evaluation",
        PaperAnalysis(
            research_problem="Evaluate RAG systems.",
            method="Benchmark pipeline.",
            datasets="Natural Questions",
            metrics="exact match",
            limitations="single-domain questions",
        ),
    )

    parsed = parse_paper_card(card)

    assert parsed.title == "RAG | Evaluation"
    assert parsed.problem == "Evaluate RAG systems."
    assert parsed.method == "Benchmark pipeline."
    assert parsed.datasets == "Natural Questions"
    assert parsed.metrics == "exact match"
    assert parsed.limitations == "single-domain questions"


def test_generate_research_idea_cards_from_multiple_paper_cards():
    cards = _sample_paper_cards()

    ideas = generate_research_idea_cards(cards)

    assert 3 <= len(ideas) <= 5
    titles = {"RAG Evaluation", "Agentic RAG", "RAG Robustness"}
    for idea in ideas:
        assert set(idea.related_papers).issubset(titles)
        assert idea.research_gap
        assert idea.proposed_method
        assert idea.experiment_plan
        assert idea.risk
        assert idea.difficulty in {"low", "medium", "high"}
    assert any("datasets" in idea.research_gap for idea in ideas)
    assert any("metrics" in idea.research_gap for idea in ideas)
    assert any("limitations" in idea.research_gap for idea in ideas)


def test_generate_research_idea_cards_refuses_insufficient_evidence():
    cards = [
        build_paper_card("Sparse One", PaperAnalysis()),
        build_paper_card("Sparse Two", PaperAnalysis()),
    ]

    with pytest.raises(IdeaGenerationError):
        generate_research_idea_cards(cards)


def test_build_idea_markdown_report_contains_comparison_and_required_fields():
    report = build_idea_markdown_report(_sample_paper_cards())

    assert "# Research Idea Report" in report
    assert "## Paper Comparison" in report
    assert "| Paper | Problem | Method | Datasets | Metrics | Limitations |" in report
    assert "- related_papers:" in report
    assert "- research_gap:" in report
    assert "- proposed_method:" in report
    assert "- experiment_plan:" in report
    assert "- risk:" in report
    assert "- difficulty:" in report


def test_export_idea_markdown_report_writes_file(tmp_path: Path):
    output_path = tmp_path / "ideas.md"

    exported = export_idea_markdown_report(_sample_paper_cards(), output_path)

    assert exported == output_path
    assert output_path.read_text(encoding="utf-8").startswith("# Research Idea Report")


def test_build_comparison_table_escapes_markdown_pipes():
    card = build_paper_card(
        "RAG Evaluation",
        PaperAnalysis(
            research_problem="Compare retrieval | generation.",
            method="Benchmark pipeline.",
        ),
    )

    table = build_comparison_table([card])

    assert "Compare retrieval \\| generation." in table


def _sample_paper_cards() -> list[str]:
    return [
        build_paper_card(
            "RAG Evaluation",
            PaperAnalysis(
                research_problem="Evaluate RAG answer quality.",
                method="Retriever-generator benchmark.",
                datasets="Natural Questions",
                metrics="exact match; retrieval recall",
                limitations="single-domain questions",
            ),
        ),
        build_paper_card(
            "Agentic RAG",
            PaperAnalysis(
                research_problem="Plan multi-step retrieval for complex QA.",
                method="Planner-based retrieval agent.",
                datasets="HotpotQA",
                metrics="F1; success rate",
                limitations="high inference cost",
            ),
        ),
        build_paper_card(
            "RAG Robustness",
            PaperAnalysis(
                research_problem="Measure RAG robustness under noisy passages.",
                method="Noise injection evaluation.",
                datasets="Natural Questions; TriviaQA",
                metrics="robust accuracy; exact match",
                limitations="limited multilingual coverage",
            ),
        ),
    ]
