from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from autoresearcher.analyzers.llm_client import NOT_SPECIFIED
from autoresearcher.analyzers.paper_analyzer import ANALYSIS_CLAIM_FIELDS, PaperCard
from autoresearcher.ideas.candidate_generator import CandidateIdeaCard, IdeaGenerationResult

TargetType = Literal["paper", "candidate_idea"]
EvidenceSourceType = Literal["paper_card", "candidate_idea"]


class HardwareAssumptions(BaseModel):
    """Hardware assumptions for a reproduction or validation plan."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    compute: str = NOT_SPECIFIED
    gpu: str = NOT_SPECIFIED
    memory: str = NOT_SPECIFIED
    storage: str = NOT_SPECIFIED
    time_budget: str = NOT_SPECIFIED
    notes: str = NOT_SPECIFIED


class DatasetRequirement(BaseModel):
    """Dataset or artifact requirement extracted from the source card."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = NOT_SPECIFIED
    source: str = NOT_SPECIFIED
    preprocessing: str = NOT_SPECIFIED
    required: bool = True
    notes: str = NOT_SPECIFIED


class ReproductionCommand(BaseModel):
    """One command template in the plan."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    step: int
    name: str
    command: str
    expected_output: str = NOT_SPECIFIED
    risk: str = NOT_SPECIFIED


class PlanEvidence(BaseModel):
    """Evidence linking the plan back to a paper card or candidate idea."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_type: EvidenceSourceType
    source_id: str
    text: str
    reason: str


class ReproductionPlan(BaseModel):
    """Practical plan for reproducing a paper or validating a candidate idea."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    plan_id: str
    target_type: TargetType
    target_id: str
    title: str
    objective: str
    hardware_assumptions: HardwareAssumptions
    dataset_requirements: list[DatasetRequirement] = Field(default_factory=list)
    commands: list[ReproductionCommand] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    success_checks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    evidence: list[PlanEvidence] = Field(default_factory=list)


class ReproductionPlanningResult(BaseModel):
    """Structured v0.10 reproduction planning output."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    plans: list[ReproductionPlan] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def plan_reproduction_from_ideas(
    idea_results: Sequence[IdeaGenerationResult],
    *,
    hardware: str = NOT_SPECIFIED,
    max_plans: int | None = None,
) -> ReproductionPlanningResult:
    return plan_reproduction(
        idea_results=idea_results,
        paper_cards=[],
        hardware=hardware,
        max_plans=max_plans,
    )


def plan_reproduction_from_paper_cards(
    paper_cards: Sequence[PaperCard],
    *,
    hardware: str = NOT_SPECIFIED,
    max_plans: int | None = None,
) -> ReproductionPlanningResult:
    return plan_reproduction(
        idea_results=[],
        paper_cards=paper_cards,
        hardware=hardware,
        max_plans=max_plans,
    )


def plan_reproduction(
    *,
    idea_results: Sequence[IdeaGenerationResult],
    paper_cards: Sequence[PaperCard],
    hardware: str = NOT_SPECIFIED,
    max_plans: int | None = None,
) -> ReproductionPlanningResult:
    ideas = [idea for result in idea_results for idea in result.idea_cards]
    plans = [
        *[_plan_from_idea(idea, hardware) for idea in ideas],
        *[_plan_from_paper_card(card, hardware) for card in paper_cards],
    ]
    if max_plans is not None:
        plans = plans[:max_plans]
    return ReproductionPlanningResult(
        plans=_assign_plan_ids(plans),
        limitations=_result_limitations(),
    )


def build_reproduction_plan_markdown(result: ReproductionPlanningResult) -> str:
    lines = [
        "# Reproduction Plans",
        "",
        "These plans are operational checklists. They do not execute experiments.",
        "",
    ]
    if not result.plans:
        lines.append(f"- {NOT_SPECIFIED}")
    for plan in result.plans:
        lines.extend(_plan_markdown_lines(plan))
    lines.extend(["## Planning Limitations", ""])
    lines.extend(f"- {item}" for item in result.limitations)
    return "\n".join(lines).rstrip() + "\n"


def export_reproduction_plan_json(
    result: ReproductionPlanningResult,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path


def export_reproduction_plan_markdown(
    result: ReproductionPlanningResult,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_reproduction_plan_markdown(result), encoding="utf-8")
    return path


def load_idea_generation_json(path: str | Path) -> IdeaGenerationResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return IdeaGenerationResult.model_validate(payload)


def _plan_from_idea(idea: CandidateIdeaCard, hardware: str) -> ReproductionPlan:
    missing = [
        "Exact repository URL is not specified.",
        "Exact dataset download commands are not specified unless listed in evidence.",
        "Exact model checkpoints and hyperparameters are not specified.",
    ]
    if hardware == NOT_SPECIFIED:
        missing.append("Hardware is not specified by the user.")
    return ReproductionPlan(
        plan_id="pending",
        target_type="candidate_idea",
        target_id=idea.idea_id,
        title=idea.title,
        objective=idea.experiment_plan,
        hardware_assumptions=_hardware_from_idea(idea, hardware),
        dataset_requirements=_datasets_from_idea(idea),
        commands=_commands_for_idea(idea),
        risks=_dedupe([idea.risk, *missing[:2]]),
        success_checks=[
            "The related papers and source gap ids are checked against original PDFs.",
            "The evaluation script produces comparable metrics for every related paper.",
            "The result table records whether the candidate idea remains plausible.",
        ],
        missing_information=missing,
        evidence=[
            PlanEvidence(
                source_type="candidate_idea",
                source_id=idea.idea_id,
                text=f"{item.source_gap_id}: {item.text}",
                reason=item.reason,
            )
            for item in idea.evidence
        ],
    )


def _plan_from_paper_card(card: PaperCard, hardware: str) -> ReproductionPlan:
    analysis = card.analysis
    target_id = str(card.metadata.get("paper_id") or card.metadata.get("arxiv_id") or _slugify(analysis.title))
    missing = [
        field
        for field in ANALYSIS_CLAIM_FIELDS
        if getattr(analysis, field).claim == NOT_SPECIFIED
    ]
    if hardware == NOT_SPECIFIED:
        missing.append("hardware")
    evidence = []
    for field in ["method", "datasets", "metrics", "baselines", "main_results", "reproduction_notes"]:
        claim = getattr(analysis, field)
        if claim.claim == NOT_SPECIFIED:
            continue
        evidence.append(
            PlanEvidence(
                source_type="paper_card",
                source_id=target_id,
                text=f"{field}: {claim.claim}",
                reason=f"The paper card provides this {field} claim with evidence.",
            )
        )
    return ReproductionPlan(
        plan_id="pending",
        target_type="paper",
        target_id=target_id,
        title=analysis.title,
        objective=_paper_objective(card),
        hardware_assumptions=_hardware_from_paper(card, hardware),
        dataset_requirements=_datasets_from_paper(card),
        commands=_commands_for_paper(card),
        risks=_paper_risks(card, missing),
        success_checks=_paper_success_checks(card),
        missing_information=missing,
        evidence=evidence,
    )


def _hardware_from_idea(idea: CandidateIdeaCard, hardware: str) -> HardwareAssumptions:
    notes = f"Candidate idea difficulty: {idea.difficulty}."
    if hardware != NOT_SPECIFIED:
        notes = f"{notes} User hardware constraint: {hardware}."
    gpu = hardware if hardware != NOT_SPECIFIED else NOT_SPECIFIED
    return HardwareAssumptions(
        compute=hardware,
        gpu=gpu,
        memory=NOT_SPECIFIED,
        storage=NOT_SPECIFIED,
        time_budget=NOT_SPECIFIED,
        notes=notes,
    )


def _hardware_from_paper(card: PaperCard, hardware: str) -> HardwareAssumptions:
    reproduction_notes = card.analysis.reproduction_notes.claim
    notes = reproduction_notes if reproduction_notes != NOT_SPECIFIED else "Paper card does not specify hardware."
    if hardware != NOT_SPECIFIED:
        notes = f"{notes} User hardware constraint: {hardware}."
    return HardwareAssumptions(
        compute=hardware,
        gpu=hardware if hardware != NOT_SPECIFIED else NOT_SPECIFIED,
        memory=NOT_SPECIFIED,
        storage=NOT_SPECIFIED,
        time_budget=NOT_SPECIFIED,
        notes=notes,
    )


def _datasets_from_idea(idea: CandidateIdeaCard) -> list[DatasetRequirement]:
    dataset_text = _dataset_evidence_text(idea)
    if dataset_text == NOT_SPECIFIED:
        dataset_text = _first_matching_text([idea.research_gap, idea.experiment_plan], ["dataset", "datasets"])
    return [
        DatasetRequirement(
            name=dataset_text,
            source="candidate idea evidence" if dataset_text != NOT_SPECIFIED else NOT_SPECIFIED,
            preprocessing=NOT_SPECIFIED,
            notes="Verify dataset names and splits against the original papers.",
        )
    ]


def _dataset_evidence_text(idea: CandidateIdeaCard) -> str:
    for item in idea.evidence:
        if any("dataset" in dimension.casefold() for dimension in item.source_dimensions):
            return item.text
    return _first_matching_text([item.text for item in idea.evidence], ["dataset", "datasets"])


def _datasets_from_paper(card: PaperCard) -> list[DatasetRequirement]:
    value = card.analysis.datasets.claim
    return [
        DatasetRequirement(
            name=value,
            source="paper card datasets field" if value != NOT_SPECIFIED else NOT_SPECIFIED,
            preprocessing=NOT_SPECIFIED,
            notes="Dataset splits, licenses, and download URLs must be checked manually.",
        )
    ]


def _commands_for_idea(idea: CandidateIdeaCard) -> list[ReproductionCommand]:
    slug = _slugify(idea.idea_id)
    return [
        ReproductionCommand(
            step=1,
            name="Create environment",
            command="python -m venv .venv",
            expected_output="A clean Python environment for the validation project.",
            risk="Exact Python and dependency versions are not specified in the idea card.",
        ),
        ReproductionCommand(
            step=2,
            name="Install dependencies",
            command="python -m pip install -r requirements.txt",
            expected_output="Dependencies for the selected papers or baselines are installed.",
            risk="requirements.txt must be created after inspecting the related papers or repositories.",
        ),
        ReproductionCommand(
            step=3,
            name="Prepare datasets",
            command=f"python scripts/prepare_data.py --target {slug}",
            expected_output="Dataset artifacts are available in a local data directory.",
            risk="Dataset URLs, splits, and preprocessing are not fully specified.",
        ),
        ReproductionCommand(
            step=4,
            name="Run validation experiment",
            command=f"python scripts/run_experiment.py --config configs/{slug}.yaml",
            expected_output="Predictions, logs, and metrics are written to outputs.",
            risk=idea.risk,
        ),
        ReproductionCommand(
            step=5,
            name="Evaluate and compare",
            command=f"python scripts/evaluate.py --run outputs/{slug}",
            expected_output="A result table that can be compared against the source papers.",
            risk="Evaluation metrics may not be directly reproducible from the available artifacts.",
        ),
    ]


def _commands_for_paper(card: PaperCard) -> list[ReproductionCommand]:
    slug = _slugify(card.analysis.title)
    return [
        ReproductionCommand(
            step=1,
            name="Create environment",
            command="python -m venv .venv",
            expected_output="A clean Python environment for the reproduction attempt.",
            risk="The paper card may not specify the original environment.",
        ),
        ReproductionCommand(
            step=2,
            name="Install paper dependencies",
            command="python -m pip install -r requirements.txt",
            expected_output="Dependencies are installed.",
            risk="The original repository or dependency list is not specified unless present in reproduction notes.",
        ),
        ReproductionCommand(
            step=3,
            name="Prepare paper datasets",
            command=f"python scripts/prepare_data.py --paper {slug}",
            expected_output="Datasets are downloaded or linked locally.",
            risk="Dataset download URLs and preprocessing are not specified in the paper card.",
        ),
        ReproductionCommand(
            step=4,
            name="Run paper method",
            command=f"python scripts/run_experiment.py --config configs/{slug}.yaml",
            expected_output="Model outputs and logs are produced.",
            risk="Method implementation details may be incomplete.",
        ),
        ReproductionCommand(
            step=5,
            name="Evaluate reported metrics",
            command=f"python scripts/evaluate.py --run outputs/{slug}",
            expected_output="Metrics comparable to the paper card are produced.",
            risk="Metric definitions may require details not present in the paper card.",
        ),
    ]


def _paper_objective(card: PaperCard) -> str:
    method = card.analysis.method.claim
    results = card.analysis.main_results.claim
    if method != NOT_SPECIFIED and results != NOT_SPECIFIED:
        return f"Reproduce the stated method and check the reported result: {results}"
    if method != NOT_SPECIFIED:
        return f"Reproduce the stated method: {method}"
    return "Reproduce the paper as far as the available paper card allows."


def _paper_risks(card: PaperCard, missing: Sequence[str]) -> list[str]:
    risks = [
        "Original repository, exact dependencies, or random seeds may be missing.",
        "Paper-card evidence may be incomplete and must be checked against the PDF.",
    ]
    limitation = card.analysis.limitations.claim
    if limitation != NOT_SPECIFIED:
        risks.append(f"Reported limitation: {limitation}")
    if missing:
        risks.append(f"Missing fields: {', '.join(missing)}")
    return _dedupe(risks)


def _paper_success_checks(card: PaperCard) -> list[str]:
    metrics = card.analysis.metrics.claim
    baselines = card.analysis.baselines.claim
    checks = ["The implementation runs end to end without manual notebook edits."]
    if metrics != NOT_SPECIFIED:
        checks.append(f"Reported metrics are computed: {metrics}")
    else:
        checks.append("Evaluation metrics are identified from the original paper.")
    if baselines != NOT_SPECIFIED:
        checks.append(f"At least one reported baseline is compared: {baselines}")
    checks.append("Differences from the paper card are documented with likely causes.")
    return checks


def _first_matching_text(values: Sequence[str], keywords: Sequence[str]) -> str:
    for value in values:
        lowered = value.casefold()
        if any(keyword in lowered for keyword in keywords):
            return value
    return NOT_SPECIFIED


def _assign_plan_ids(plans: Sequence[ReproductionPlan]) -> list[ReproductionPlan]:
    return [
        plan.model_copy(update={"plan_id": f"PLAN-{index:03d}"})
        for index, plan in enumerate(plans, start=1)
    ]


def _result_limitations() -> list[str]:
    return [
        "Plans are generated from structured cards, not from full repository inspection.",
        "Commands are templates and may require manual editing before execution.",
        "No experiment is executed by AutoResearcher in v0.10.",
        "Hardware, dataset URLs, licenses, seeds, and exact hyperparameters must be verified manually.",
    ]


def _plan_markdown_lines(plan: ReproductionPlan) -> list[str]:
    lines = [
        f"## {plan.plan_id}: {plan.title}",
        "",
        f"- target_type: {plan.target_type}",
        f"- target_id: {plan.target_id}",
        f"- objective: {plan.objective}",
        "",
        "### Hardware Assumptions",
        "",
        f"- compute: {plan.hardware_assumptions.compute}",
        f"- gpu: {plan.hardware_assumptions.gpu}",
        f"- memory: {plan.hardware_assumptions.memory}",
        f"- storage: {plan.hardware_assumptions.storage}",
        f"- time_budget: {plan.hardware_assumptions.time_budget}",
        f"- notes: {plan.hardware_assumptions.notes}",
        "",
        "### Dataset Requirements",
        "",
        "| Name | Source | Preprocessing | Required | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in plan.dataset_requirements:
        lines.append(
            "| "
            + " | ".join(
                _escape_table(str(value))
                for value in [item.name, item.source, item.preprocessing, item.required, item.notes]
            )
            + " |"
        )
    lines.extend(["", "### Commands", ""])
    for command in plan.commands:
        lines.extend(
            [
                f"{command.step}. {command.name}",
                "",
                f"```powershell\n{command.command}\n```",
                "",
                f"- expected_output: {command.expected_output}",
                f"- risk: {command.risk}",
                "",
            ]
        )
    lines.extend(["### Success Checks", ""])
    lines.extend(f"- {item}" for item in plan.success_checks)
    lines.extend(["", "### Risks", ""])
    lines.extend(f"- {item}" for item in plan.risks)
    lines.extend(["", "### Missing Information", ""])
    if plan.missing_information:
        lines.extend(f"- {item}" for item in plan.missing_information)
    else:
        lines.append(f"- {NOT_SPECIFIED}")
    lines.extend(
        [
            "",
            "### Evidence",
            "",
            "| Source | Source ID | Evidence | Reason |",
            "| --- | --- | --- | --- |",
        ]
    )
    if plan.evidence:
        for evidence in plan.evidence:
            lines.append(
                "| "
                + " | ".join(
                    _escape_table(value)
                    for value in [
                        evidence.source_type,
                        evidence.source_id,
                        evidence.text,
                        evidence.reason,
                    ]
                )
                + " |"
            )
    else:
        lines.append(f"| {NOT_SPECIFIED} | {NOT_SPECIFIED} | {NOT_SPECIFIED} | {NOT_SPECIFIED} |")
    lines.append("")
    return lines


def _slugify(value: str) -> str:
    slug = "".join(char if char.isalnum() else "-" for char in value.lower()).strip("-")
    return slug or "target"


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))
