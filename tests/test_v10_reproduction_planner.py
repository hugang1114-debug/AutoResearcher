import json
from pathlib import Path

from autoresearcher.analyzers.llm_client import NOT_SPECIFIED
from autoresearcher.analyzers.paper_analyzer import PaperAnalysisResult, PaperCard
from autoresearcher.cli import main
from autoresearcher.comparison.matrix import export_comparison_json
from autoresearcher.ideas.candidate_generator import (
    CandidateIdeaCard,
    IdeaGenerationResult,
    export_candidate_idea_json,
)
from autoresearcher.reproduction.planner import (
    ReproductionPlan,
    build_reproduction_plan_markdown,
    export_reproduction_plan_json,
    export_reproduction_plan_markdown,
    plan_reproduction,
    plan_reproduction_from_ideas,
    plan_reproduction_from_paper_cards,
)
from autoresearcher.workspace.core import create_workspace, workspace_status


def test_reproduction_plan_schema_contains_required_operational_fields():
    plan = ReproductionPlan.model_validate(
        {
            "plan_id": "PLAN-001",
            "target_type": "candidate_idea",
            "target_id": "IDEA-001",
            "title": "Controlled evaluation",
            "objective": "Validate a controlled evaluation idea.",
            "hardware_assumptions": {"compute": "single GPU", "gpu": "single GPU"},
            "dataset_requirements": [{"name": "Natural Questions", "source": "idea evidence"}],
            "commands": [
                {
                    "step": 1,
                    "name": "Create environment",
                    "command": "python -m venv .venv",
                }
            ],
            "risks": ["Implementation details are missing."],
            "success_checks": ["Metrics are produced."],
            "missing_information": ["repository URL"],
            "evidence": [
                {
                    "source_type": "candidate_idea",
                    "source_id": "IDEA-001",
                    "text": "GAP-001: dataset mismatch",
                    "reason": "Grounded in gap evidence.",
                }
            ],
        }
    )

    assert plan.hardware_assumptions.compute == "single GPU"
    assert plan.dataset_requirements[0].required is True
    assert plan.commands[0].command == "python -m venv .venv"


def test_plan_reproduction_from_candidate_idea_includes_commands_risks_and_evidence():
    result = plan_reproduction_from_ideas([_idea_result()], hardware="single GPU")

    plan = result.plans[0]

    assert plan.plan_id == "PLAN-001"
    assert plan.target_type == "candidate_idea"
    assert plan.hardware_assumptions.gpu == "single GPU"
    assert plan.dataset_requirements[0].name != NOT_SPECIFIED
    assert len(plan.commands) >= 5
    assert plan.risks
    assert plan.success_checks
    assert plan.evidence[0].source_type == "candidate_idea"


def test_plan_reproduction_from_paper_card_marks_missing_information():
    result = plan_reproduction_from_paper_cards([_paper_card()], hardware=NOT_SPECIFIED)

    plan = result.plans[0]

    assert plan.target_type == "paper"
    assert plan.target_id == "paper-a"
    assert plan.dataset_requirements[0].name == "Natural Questions."
    assert "hardware" in plan.missing_information
    assert any("Reported metrics are computed" in item for item in plan.success_checks)


def test_combined_reproduction_planning_assigns_stable_ids():
    result = plan_reproduction(
        idea_results=[_idea_result()],
        paper_cards=[_paper_card()],
        hardware="single GPU",
    )

    assert [plan.plan_id for plan in result.plans] == ["PLAN-001", "PLAN-002"]


def test_reproduction_markdown_and_exports(tmp_path: Path):
    result = plan_reproduction_from_ideas([_idea_result()], hardware="single GPU")

    markdown = build_reproduction_plan_markdown(result)
    json_path = export_reproduction_plan_json(result, tmp_path / "plan.json")
    markdown_path = export_reproduction_plan_markdown(result, tmp_path / "plan.md")

    assert markdown.startswith("# Reproduction Plans")
    assert "### Hardware Assumptions" in markdown
    assert "### Dataset Requirements" in markdown
    assert "### Commands" in markdown
    assert "python scripts/run_experiment.py" in markdown
    assert json.loads(json_path.read_text(encoding="utf-8"))["plans"][0]["plan_id"] == "PLAN-001"
    assert markdown_path.read_text(encoding="utf-8").startswith("# Reproduction Plans")


def test_cli_plan_reproduction_command_with_idea_json(tmp_path: Path):
    idea_path = export_candidate_idea_json(_idea_result(), tmp_path / "ideas.json")
    markdown_path = tmp_path / "plan.md"
    json_path = tmp_path / "plan.json"

    rc = main(
        [
            "plan-reproduction",
            "--idea",
            str(idea_path),
            "--hardware",
            "single GPU",
            "--output",
            str(markdown_path),
            "--json-output",
            str(json_path),
        ]
    )

    assert rc == 0
    assert markdown_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["plans"][0]["target_type"] == "candidate_idea"


def test_cli_plan_reproduction_command_with_paper_card_json(tmp_path: Path):
    card_path = tmp_path / "paper.json"
    card_path.write_text(_paper_card().model_dump_json(indent=2), encoding="utf-8")
    markdown_path = tmp_path / "paper_plan.md"

    rc = main(
        [
            "plan-reproduction",
            "--paper-card",
            str(card_path),
            "--output",
            str(markdown_path),
        ]
    )

    assert rc == 0
    assert "PLAN-001" in markdown_path.read_text(encoding="utf-8")


def test_cli_workspace_plan_reproduction_command(tmp_path: Path):
    workspace = create_workspace("rag-review", root=tmp_path)
    idea_path = export_candidate_idea_json(_idea_result(), workspace.ideas_path / "ideas.json")

    rc = main(
        [
            "workspace-plan-reproduction",
            "--name",
            workspace.name,
            "--root",
            str(tmp_path),
            "--idea",
            str(idea_path),
            "--name-output",
            "idea-plan",
            "--hardware",
            "single GPU",
        ]
    )

    assert rc == 0
    assert (workspace.reproduction_path / "idea-plan.md").exists()
    assert (workspace.reproduction_path / "idea-plan.json").exists()
    assert workspace_status(workspace)["reproduction"] == 1


def _idea_result() -> IdeaGenerationResult:
    idea = CandidateIdeaCard(
        idea_id="IDEA-001",
        title="Controlled evaluation alignment for Datasets",
        related_papers=["Paper A", "Paper B"],
        source_gap_ids=["GAP-001"],
        research_gap="GAP-001: Paper cards report different datasets.",
        proposed_method="Build a controlled evaluation matrix over named datasets.",
        experiment_plan="Normalize the evaluation setup over Natural Questions and HotpotQA.",
        risk="Implementation details and dataset splits may be missing.",
        difficulty="high",
        evidence=[
            {
                "source_gap_id": "GAP-001",
                "gap_category": "evaluation_mismatch",
                "source_dimensions": ["Datasets"],
                "related_papers": ["Paper A", "Paper B"],
                "text": "Paper A: Natural Questions; Paper B: HotpotQA",
                "reason": "Gap evidence reports different datasets.",
            }
        ],
    )
    return IdeaGenerationResult(idea_cards=[idea], source_gap_ids=["GAP-001"])


def _paper_card() -> PaperCard:
    return PaperCard(
        analysis=PaperAnalysisResult.model_validate(_paper_payload()),
        metadata={"paper_id": "paper-a"},
    )


def _paper_payload():
    def claim(value: str):
        if value == NOT_SPECIFIED:
            return {"claim": NOT_SPECIFIED, "evidence": []}
        return {
            "claim": value,
            "evidence": [
                {
                    "source_section": "abstract",
                    "text": value,
                    "reason": "fixture evidence",
                }
            ],
        }

    return {
        "title": "Paper A",
        "problem": claim("Evaluate RAG retrieval failures."),
        "motivation": claim(NOT_SPECIFIED),
        "method": claim("Retry retrieval when evidence is weak."),
        "datasets": claim("Natural Questions."),
        "metrics": claim("Exact match."),
        "baselines": claim("BM25."),
        "main_results": claim("Improves answer grounding."),
        "limitations": claim("Only English QA."),
        "reproduction_notes": claim(NOT_SPECIFIED),
        "possible_extensions": claim(NOT_SPECIFIED),
        "confidence": {
            "level": "medium",
            "score": 0.6,
            "missing_information": [],
            "rationale": "fixture",
        },
    }
