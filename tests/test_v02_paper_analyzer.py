from pathlib import Path

from autoresearcher.analyzers.llm_client import MockLLMClient, NOT_SPECIFIED
from autoresearcher.analyzers.markdown_exporter import (
    build_paper_card_markdown,
    export_paper_card_markdown,
)
from autoresearcher.analyzers.paper_analyzer import (
    AnalysisConfidence,
    EvidenceBackedClaim,
    EvidenceSpan,
    PaperAnalysisResult,
    PaperAnalyzer,
    PaperCard,
)
from autoresearcher.cli import main
from autoresearcher.models import PaperMetadata
from autoresearcher.storage import PaperStore


def test_paper_analysis_result_schema_accepts_evidence_backed_claims():
    result = PaperAnalysisResult.model_validate(_analysis_payload())

    assert result.title == "Evidence RAG"
    assert result.problem.claim == "Evaluate retrieval failures in RAG."
    assert result.problem.evidence[0].source_section == "abstract"
    assert result.confidence.level == "medium"


def test_claim_without_evidence_is_forced_to_not_specified_and_confidence_drops():
    payload = _analysis_payload()
    payload["datasets"] = {"claim": "Natural Questions", "evidence": []}
    payload["confidence"] = {
        "level": "high",
        "score": 0.95,
        "missing_information": [],
        "rationale": "The model claimed high confidence.",
    }

    result = PaperAnalysisResult.model_validate(payload)

    assert result.datasets.claim == NOT_SPECIFIED
    assert "datasets" in result.confidence.missing_information
    assert result.confidence.level in {"low", "medium"}
    assert result.confidence.score <= 0.65


def test_mock_llm_client_returns_valid_json_without_external_api():
    client = MockLLMClient()

    response = client.generate(
        "Title:\nMock Paper\n\nAbstract:\nThis paper evaluates RAG failures.\n\nPDF text:\nnot specified"
    )
    result = PaperAnalysisResult.model_validate_json(response)

    assert client.prompts
    assert result.title == "Mock Paper"
    assert result.problem.claim == "This paper evaluates RAG failures."
    assert result.method.claim == NOT_SPECIFIED


def test_paper_analyzer_normalizes_missing_information_to_not_specified():
    payload = _analysis_payload()
    payload["metrics"] = {"claim": "", "evidence": []}
    payload["baselines"] = {"claim": None, "evidence": []}
    analyzer = PaperAnalyzer(MockLLMClient(payload))

    card = analyzer.analyze(
        title="Evidence RAG",
        abstract="This paper evaluates retrieval failures in RAG.",
    )

    assert card.analysis.metrics.claim == NOT_SPECIFIED
    assert card.analysis.baselines.claim == NOT_SPECIFIED
    assert "metrics" in card.analysis.confidence.missing_information
    assert "baselines" in card.analysis.confidence.missing_information


def test_markdown_exporter_outputs_required_sections_and_evidence_table(tmp_path: Path):
    card = PaperCard(
        analysis=PaperAnalysisResult.model_validate(_analysis_payload()),
        metadata={"source": "test", "year": 2026},
    )

    markdown = build_paper_card_markdown(card)
    output = export_paper_card_markdown(card, tmp_path / "card.md")

    assert output.read_text(encoding="utf-8") == markdown
    for heading in [
        "# Paper Card: Evidence RAG",
        "## Basic Information",
        "## Research Problem",
        "## Motivation",
        "## Method",
        "## Datasets",
        "## Metrics",
        "## Baselines",
        "## Main Results",
        "## Limitations",
        "## Reproduction Notes",
        "## Possible Extensions",
        "## Evidence Table",
        "## Confidence and Missing Information",
    ]:
        assert heading in markdown
    assert "| Research Problem | abstract | This paper evaluates retrieval failures in RAG." in markdown


def test_cli_analyze_command_with_mock_writes_markdown_card(tmp_path: Path):
    output = tmp_path / "paper_card.md"

    rc = main(
        [
            "analyze",
            "--title",
            "Mock Paper",
            "--abstract",
            "This paper evaluates RAG failures.",
            "--mock",
            "--output",
            str(output),
        ]
    )

    assert rc == 0
    text = output.read_text(encoding="utf-8")
    assert "# Paper Card: Mock Paper" in text
    assert "This paper evaluates RAG failures." in text


def test_cli_export_card_loads_paper_from_sqlite(tmp_path: Path):
    db_path = tmp_path / "papers.sqlite"
    output = tmp_path / "exported.md"
    with PaperStore(db_path) as store:
        store.upsert_papers(
            [
                PaperMetadata(
                    title="Stored RAG Paper",
                    abstract="This paper studies corrective RAG evaluation.",
                    source="test",
                    paper_id="stored-1",
                )
            ]
        )

    rc = main(
        [
            "export-card",
            "--paper-id",
            "stored-1",
            "--db",
            str(db_path),
            "--mock",
            "--output",
            str(output),
        ]
    )

    assert rc == 0
    assert "# Paper Card: Stored RAG Paper" in output.read_text(encoding="utf-8")


def _analysis_payload():
    evidence = {
        "source_section": "abstract",
        "text": "This paper evaluates retrieval failures in RAG.",
        "reason": "The sentence states the evaluation target.",
    }
    method_evidence = {
        "source_section": "method",
        "text": "The method detects retrieval failure and retries retrieval.",
        "reason": "The text describes the core method.",
    }
    limitation_evidence = {
        "source_section": "limitation",
        "text": "The evaluation is limited to English QA datasets.",
        "reason": "The text states an explicit limitation.",
    }
    return {
        "title": "Evidence RAG",
        "problem": {
            "claim": "Evaluate retrieval failures in RAG.",
            "evidence": [evidence],
        },
        "motivation": {
            "claim": "Retrieval failures can cause unsupported answers.",
            "evidence": [evidence],
        },
        "method": {
            "claim": "Detect retrieval failure and retry retrieval.",
            "evidence": [method_evidence],
        },
        "datasets": {
            "claim": "English QA datasets.",
            "evidence": [limitation_evidence],
        },
        "metrics": {
            "claim": "not specified",
            "evidence": [],
        },
        "baselines": {
            "claim": "not specified",
            "evidence": [],
        },
        "main_results": {
            "claim": "not specified",
            "evidence": [],
        },
        "limitations": {
            "claim": "Limited to English QA datasets.",
            "evidence": [limitation_evidence],
        },
        "reproduction_notes": {
            "claim": "Requires retrieval failure detector and QA evaluation data.",
            "evidence": [method_evidence, limitation_evidence],
        },
        "possible_extensions": {
            "claim": "Extend the evaluation beyond English QA datasets.",
            "evidence": [limitation_evidence],
        },
        "confidence": {
            "level": "medium",
            "score": 0.62,
            "missing_information": ["metrics", "baselines", "main_results"],
            "rationale": "Several fields are supported, but experiment details are missing.",
        },
    }
