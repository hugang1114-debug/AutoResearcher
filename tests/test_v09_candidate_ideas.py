import json
from pathlib import Path

import pytest

from autoresearcher.cli import main
from autoresearcher.gaps.extractor import (
    GapEvidence,
    GapExtractionResult,
    ResearchGapCard,
    export_research_gap_json,
)
from autoresearcher.ideas.candidate_generator import (
    CandidateIdeaCard,
    IdeaGenerationError,
    build_candidate_idea_markdown,
    export_candidate_idea_json,
    export_candidate_idea_markdown,
    generate_candidate_ideas,
)
from autoresearcher.workspace.core import create_workspace, workspace_status


def test_candidate_idea_schema_requires_two_related_papers_and_evidence():
    idea = CandidateIdeaCard.model_validate(
        {
            "idea_id": "IDEA-001",
            "title": "Controlled evaluation alignment",
            "related_papers": ["Paper A", "Paper B"],
            "source_gap_ids": ["GAP-001"],
            "research_gap": "GAP-001 reports different datasets.",
            "proposed_method": "Build a controlled evaluation matrix.",
            "experiment_plan": "Normalize datasets and compare reported methods.",
            "risk": "Implementation details may be missing.",
            "difficulty": "high",
            "evidence": [
                {
                    "source_gap_id": "GAP-001",
                    "gap_category": "evaluation_mismatch",
                    "source_dimensions": ["Datasets"],
                    "related_papers": ["Paper A", "Paper B"],
                    "text": "Paper A: NQ; Paper B: HotpotQA",
                    "reason": "Gap evidence reports different datasets.",
                }
            ],
        }
    )

    assert idea.status == "candidate"
    assert idea.related_papers == ["Paper A", "Paper B"]


def test_candidate_idea_schema_rejects_single_paper_ideas():
    with pytest.raises(ValueError):
        CandidateIdeaCard(
            idea_id="IDEA-001",
            title="Unsupported idea",
            related_papers=["Paper A"],
            source_gap_ids=["GAP-001"],
            research_gap="Only one paper supports this.",
            proposed_method="Try something.",
            experiment_plan="Run a test.",
            risk="Unsupported.",
            difficulty="medium",
            evidence=[
                {
                    "source_gap_id": "GAP-001",
                    "gap_category": "stated_limitation",
                    "text": "Only Paper A.",
                    "reason": "fixture",
                }
            ],
        )


def test_generate_candidate_ideas_traces_back_to_gap_evidence():
    result = generate_candidate_ideas([_gap_result()], constraints=["single GPU"])

    assert 3 <= len(result.idea_cards) <= 5
    assert "GAP-005" in result.skipped_gap_ids
    assert result.constraints == ["single GPU"]
    for idea in result.idea_cards:
        assert len(idea.related_papers) >= 2
        assert idea.source_gap_ids
        assert idea.evidence
        assert idea.risk
        assert idea.difficulty in {"low", "medium", "high"}
        assert "novel" not in idea.research_gap.casefold()
        assert "single GPU" in idea.proposed_method or idea.evidence


def test_generate_candidate_ideas_refuses_unsupported_gaps():
    with pytest.raises(IdeaGenerationError):
        generate_candidate_ideas([_unsupported_gap_result()])


def test_candidate_idea_markdown_and_exports(tmp_path: Path):
    result = generate_candidate_ideas([_gap_result()])

    markdown = build_candidate_idea_markdown(result)
    json_path = export_candidate_idea_json(result, tmp_path / "ideas.json")
    markdown_path = export_candidate_idea_markdown(result, tmp_path / "ideas.md")

    assert markdown.startswith("# Candidate Research Idea Cards")
    assert "not novelty claims" in markdown
    assert "| Source Gap | Category | Dimensions | Related Papers | Evidence | Reason |" in markdown
    assert json.loads(json_path.read_text(encoding="utf-8"))["idea_cards"][0]["idea_id"] == "IDEA-001"
    assert markdown_path.read_text(encoding="utf-8").startswith("# Candidate Research Idea Cards")


def test_cli_generate_ideas_command(tmp_path: Path):
    gaps_path = export_research_gap_json(_gap_result(), tmp_path / "gaps.json")
    markdown_path = tmp_path / "ideas.md"
    json_path = tmp_path / "ideas.json"

    rc = main(
        [
            "generate-ideas",
            "--gaps",
            str(gaps_path),
            "--output",
            str(markdown_path),
            "--json-output",
            str(json_path),
            "--constraint",
            "single GPU",
        ]
    )

    assert rc == 0
    assert markdown_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["idea_cards"]


def test_cli_workspace_generate_ideas_command(tmp_path: Path):
    workspace = create_workspace("rag-review", root=tmp_path)
    gaps_path = export_research_gap_json(_gap_result(), workspace.gaps_path / "gaps.json")

    rc = main(
        [
            "workspace-generate-ideas",
            "--name",
            workspace.name,
            "--root",
            str(tmp_path),
            "--gaps",
            str(gaps_path),
            "--name-output",
            "candidate-ideas",
        ]
    )

    assert rc == 0
    assert (workspace.ideas_path / "candidate-ideas.md").exists()
    assert (workspace.ideas_path / "candidate-ideas.json").exists()
    assert workspace_status(workspace)["ideas"] == 1


def _gap_result() -> GapExtractionResult:
    return GapExtractionResult(
        paper_titles=["Paper A", "Paper B"],
        gaps=[
            _gap(
                "GAP-001",
                "evaluation_mismatch",
                "Different datasets across papers",
                "Paper cards report different datasets for related evaluations.",
                ["Paper A", "Paper B"],
                ["Datasets"],
                ["Paper A: Natural Questions", "Paper B: HotpotQA"],
            ),
            _gap(
                "GAP-002",
                "baseline_gap",
                "Baseline reporting gap",
                "Baseline information is incomplete across related papers.",
                ["Paper A", "Paper B"],
                ["Baselines"],
                ["Paper A: BM25", "Paper B: not specified"],
            ),
            _gap(
                "GAP-003",
                "stated_limitation",
                "Limitation in Paper A",
                "Paper A states limited multilingual coverage.",
                ["Paper A"],
                ["Limitations"],
                ["limited multilingual coverage"],
            ),
            _gap(
                "GAP-004",
                "stated_limitation",
                "Limitation in Paper B",
                "Paper B states high inference cost.",
                ["Paper B"],
                ["Limitations"],
                ["high inference cost"],
            ),
            _gap(
                "GAP-005",
                "not_comparable",
                "Missing method evidence",
                "Method information is not comparable.",
                ["Paper A", "Paper B"],
                ["Method"],
                ["not specified"],
            ),
        ],
        limitations=["fixture"],
    )


def _unsupported_gap_result() -> GapExtractionResult:
    return GapExtractionResult(
        paper_titles=["Paper A", "Paper B"],
        gaps=[
            _gap(
                "GAP-001",
                "not_comparable",
                "Missing method evidence",
                "Method information is not comparable.",
                ["Paper A", "Paper B"],
                ["Method"],
                ["not specified"],
            )
        ],
        limitations=["fixture"],
    )


def _gap(
    gap_id: str,
    category: str,
    title: str,
    description: str,
    related_papers: list[str],
    source_dimensions: list[str],
    evidence_texts: list[str],
) -> ResearchGapCard:
    return ResearchGapCard(
        gap_id=gap_id,
        category=category,
        title=title,
        description=description,
        related_papers=related_papers,
        source_dimensions=source_dimensions,
        evidence=[
            GapEvidence(
                source="comparison_matrix",
                dimension=source_dimensions[0],
                paper_title=related_papers[index % len(related_papers)],
                text=text,
                reason="fixture evidence",
            )
            for index, text in enumerate(evidence_texts)
        ],
        confidence="medium",
    )
