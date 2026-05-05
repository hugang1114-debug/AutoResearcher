import json

import pytest

from autoresearcher.paper_analyzer import (
    NOT_SPECIFIED,
    PaperAnalysisError,
    PaperAnalyzer,
    build_paper_card,
    parse_analysis_response,
)


class MockLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompt = ""

    def generate(self, prompt: str) -> str:
        self.prompt = prompt
        return self.response


def test_paper_analyzer_calls_llm_and_validates_json():
    response = json.dumps(
        {
            "research_problem": "How to evaluate RAG systems.",
            "motivation": "Existing evaluations miss retrieval quality.",
            "method": "A benchmark with retrieval and generation metrics.",
            "datasets": "Natural Questions",
            "metrics": "Recall, exact match",
            "key_findings": "Retrieval quality affects answer quality.",
            "limitations": "Small domain coverage.",
            "future_work": "Broader multilingual evaluation.",
            "reproduction_notes": "Dataset and metrics are described.",
        }
    )
    llm = MockLLM(response)

    analysis = PaperAnalyzer(llm, max_pdf_chars=25).analyze(
        title="RAG Evaluation",
        abstract="We evaluate retrieval augmented generation.",
        pdf_text="This PDF text is intentionally long enough to truncate.",
    )

    assert analysis.research_problem == "How to evaluate RAG systems."
    assert "RAG Evaluation" in llm.prompt
    assert "[truncated]" in llm.prompt


def test_parse_analysis_response_normalizes_missing_values():
    response = """```json
{
  "research_problem": "",
  "motivation": null,
  "method": "not mentioned",
  "datasets": [],
  "metrics": ["accuracy", "F1"],
  "key_findings": "not specified",
  "limitations": "Unknown",
  "reproduction_notes": {"code": "not provided"}
}
```"""

    analysis = parse_analysis_response(response)

    assert analysis.research_problem == NOT_SPECIFIED
    assert analysis.motivation == NOT_SPECIFIED
    assert analysis.method == NOT_SPECIFIED
    assert analysis.datasets == NOT_SPECIFIED
    assert analysis.metrics == "accuracy; F1"
    assert analysis.key_findings == NOT_SPECIFIED
    assert analysis.limitations == NOT_SPECIFIED
    assert analysis.future_work == NOT_SPECIFIED
    assert analysis.reproduction_notes == '{"code": "not provided"}'


def test_parse_analysis_response_rejects_invalid_json():
    with pytest.raises(PaperAnalysisError):
        parse_analysis_response("this is not json")


def test_build_paper_card_returns_markdown_table():
    analysis = parse_analysis_response(
        json.dumps(
            {
                "research_problem": "Compare RAG | agent evaluation.",
                "motivation": "not specified",
                "method": "Manual benchmark.",
                "datasets": "not specified",
                "metrics": "not specified",
                "key_findings": "not specified",
                "limitations": "not specified",
                "future_work": "not specified",
                "reproduction_notes": "not specified",
            }
        )
    )

    card = build_paper_card("RAG Agents", analysis)

    assert card.startswith("## Paper Card: RAG Agents")
    assert "| Research problem | Compare RAG \\| agent evaluation. |" in card
    assert "| Reproduction notes | not specified |" in card
