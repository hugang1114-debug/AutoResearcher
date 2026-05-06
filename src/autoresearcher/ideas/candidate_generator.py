from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from autoresearcher.analyzers.llm_client import NOT_SPECIFIED
from autoresearcher.gaps.extractor import GapExtractionResult, ResearchGapCard

Difficulty = Literal["low", "medium", "high"]


class IdeaGenerationError(RuntimeError):
    """Raised when gap cards cannot support grounded candidate ideas."""


class CandidateIdeaEvidence(BaseModel):
    """Trace from a candidate idea back to a source gap card."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_gap_id: str
    gap_category: str
    source_dimensions: list[str] = Field(default_factory=list)
    related_papers: list[str] = Field(default_factory=list)
    text: str
    reason: str


class CandidateIdeaCard(BaseModel):
    """A candidate idea grounded in at least two related papers."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idea_id: str
    title: str
    related_papers: list[str] = Field(min_length=2)
    source_gap_ids: list[str] = Field(min_length=1)
    research_gap: str
    proposed_method: str
    experiment_plan: str
    risk: str
    difficulty: Difficulty
    evidence: list[CandidateIdeaEvidence] = Field(min_length=1)
    status: str = "candidate"

    @field_validator(
        "title",
        "research_gap",
        "proposed_method",
        "experiment_plan",
        "risk",
        mode="before",
    )
    @classmethod
    def require_specified_text(cls, value: object) -> str:
        text = str(value or "").strip()
        if not text or text.casefold() == NOT_SPECIFIED:
            raise ValueError("candidate idea fields must be grounded in gap evidence")
        return text


class IdeaGenerationResult(BaseModel):
    """Structured v0.9 output for candidate idea cards."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idea_cards: list[CandidateIdeaCard] = Field(default_factory=list)
    source_gap_ids: list[str] = Field(default_factory=list)
    skipped_gap_ids: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def generate_candidate_ideas(
    gap_results: Sequence[GapExtractionResult],
    *,
    min_ideas: int = 1,
    max_ideas: int = 5,
    constraints: Sequence[str] | None = None,
) -> IdeaGenerationResult:
    """Generate candidate idea cards from evidence-backed gap cards."""
    if not gap_results:
        raise ValueError("At least one gap extraction result is required.")
    if min_ideas < 1:
        raise ValueError("min_ideas must be at least 1.")
    if max_ideas < min_ideas:
        raise ValueError("max_ideas must be greater than or equal to min_ideas.")

    gaps = _dedupe_gaps([gap for result in gap_results for gap in result.gaps])
    direct = [_idea_from_gap(gap, constraints or []) for gap in gaps]
    clustered = _clustered_ideas(gaps, constraints or [])
    ideas = _dedupe_ideas([idea for idea in [*direct, *clustered] if idea is not None])
    ideas = _assign_idea_ids(ideas)[:max_ideas]
    if len(ideas) < min_ideas:
        raise IdeaGenerationError(
            f"Only {len(ideas)} grounded candidate idea(s) could be generated; "
            f"{min_ideas} required."
        )
    used_gap_ids = _dedupe([gap_id for idea in ideas for gap_id in idea.source_gap_ids])
    return IdeaGenerationResult(
        idea_cards=ideas,
        source_gap_ids=used_gap_ids,
        skipped_gap_ids=[gap.gap_id for gap in gaps if gap.gap_id not in used_gap_ids],
        constraints=list(constraints or []),
        limitations=_limitations(ideas),
    )


def build_candidate_idea_markdown(result: IdeaGenerationResult) -> str:
    lines = [
        "# Candidate Research Idea Cards",
        "",
        "These are candidate ideas for human screening. They are not novelty claims.",
        "",
        "## Constraints",
        "",
    ]
    if result.constraints:
        lines.extend(f"- {item}" for item in result.constraints)
    else:
        lines.append(f"- {NOT_SPECIFIED}")

    lines.extend(["", "## Idea Cards", ""])
    if not result.idea_cards:
        lines.append(f"- {NOT_SPECIFIED}")
    for idea in result.idea_cards:
        lines.extend(_idea_markdown_lines(idea))

    lines.extend(["## Skipped Gaps", ""])
    if result.skipped_gap_ids:
        lines.extend(f"- {gap_id}" for gap_id in result.skipped_gap_ids)
    else:
        lines.append(f"- {NOT_SPECIFIED}")

    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in result.limitations)
    return "\n".join(lines).rstrip() + "\n"


def export_candidate_idea_json(result: IdeaGenerationResult, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path


def export_candidate_idea_markdown(result: IdeaGenerationResult, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_candidate_idea_markdown(result), encoding="utf-8")
    return path


def load_gap_extraction_json(path: str | Path) -> GapExtractionResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return GapExtractionResult.model_validate(payload)


def _idea_from_gap(
    gap: ResearchGapCard,
    constraints: Sequence[str],
) -> CandidateIdeaCard | None:
    if gap.category in {"missing_information", "not_comparable"}:
        return None
    related_papers = _specified_related_papers(gap)
    if len(related_papers) < 2 or not gap.evidence:
        return None
    return _build_idea_from_gaps([gap], constraints)


def _clustered_ideas(
    gaps: Sequence[ResearchGapCard],
    constraints: Sequence[str],
) -> list[CandidateIdeaCard]:
    grouped: dict[tuple[str, tuple[str, ...]], list[ResearchGapCard]] = defaultdict(list)
    for gap in gaps:
        if gap.category in {"missing_information", "not_comparable"}:
            continue
        key = (gap.category, tuple(gap.source_dimensions))
        grouped[key].append(gap)
    ideas: list[CandidateIdeaCard] = []
    for gap_group in grouped.values():
        related = _dedupe([paper for gap in gap_group for paper in _specified_related_papers(gap)])
        if len(gap_group) >= 2 and len(related) >= 2:
            ideas.append(_build_idea_from_gaps(gap_group, constraints))
    return ideas


def _build_idea_from_gaps(
    gaps: Sequence[ResearchGapCard],
    constraints: Sequence[str],
) -> CandidateIdeaCard:
    category = gaps[0].category
    related_papers = _dedupe([paper for gap in gaps for paper in _specified_related_papers(gap)])
    source_gap_ids = [gap.gap_id for gap in gaps]
    dimensions = _dedupe([dimension for gap in gaps for dimension in gap.source_dimensions])
    evidence = [_idea_evidence(gap) for gap in gaps]
    title, proposed_method, experiment_plan, risk, difficulty = _idea_fields(
        category,
        dimensions,
        constraints,
    )
    return CandidateIdeaCard(
        idea_id="pending",
        title=title,
        related_papers=related_papers,
        source_gap_ids=source_gap_ids,
        research_gap=_research_gap_text(gaps),
        proposed_method=proposed_method,
        experiment_plan=experiment_plan,
        risk=risk,
        difficulty=difficulty,
        evidence=evidence,
    )


def _idea_fields(
    category: str,
    dimensions: Sequence[str],
    constraints: Sequence[str],
) -> tuple[str, str, str, str, Difficulty]:
    dimension_text = _join_or_not_specified(dimensions)
    constraint_text = f" Constraints to respect: {'; '.join(constraints)}." if constraints else ""
    if category == "evaluation_mismatch":
        return (
            f"Controlled evaluation alignment for {dimension_text}",
            (
                "Build a small controlled evaluation matrix that reuses only the "
                f"datasets or metrics named in the source gaps.{constraint_text}"
            ),
            (
                "Select the related papers, normalize the reported evaluation setup, "
                "run or rescore comparable outputs, and record where rankings change."
            ),
            (
                "The source cards may not include implementation details, splits, or "
                "prediction files needed for a faithful rerun."
            ),
            "high",
        )
    if category == "baseline_gap":
        return (
            "Baseline audit for comparable evaluation",
            (
                "Create a baseline-audit table from the reported baseline evidence and "
                f"rerun only baselines that are explicitly named.{constraint_text}"
            ),
            (
                "For each related paper, list reported baselines, mark missing baselines, "
                "then test whether adding the shared baseline changes the comparison."
            ),
            (
                "A missing baseline may reflect extraction failure rather than a true "
                "paper limitation."
            ),
            "medium",
        )
    if category == "stated_limitation":
        return (
            f"Stress test around stated limitations in {dimension_text}",
            (
                "Turn the stated limitations into targeted evaluation cases and compare "
                f"the related papers under those cases.{constraint_text}"
            ),
            (
                "For each limitation, define one observable failure condition, build a "
                "small test slice, and check whether the related methods fail similarly."
            ),
            (
                "Some limitations are qualitative and may require manual annotation or "
                "additional data not present in the gap cards."
            ),
            "medium",
        )
    if category == "extension_direction":
        return (
            f"Validate reported extension directions for {dimension_text}",
            (
                "Compare the extension directions already reported in the gap cards and "
                f"turn the overlapping direction into a small validation study.{constraint_text}"
            ),
            (
                "Choose one shared extension direction, define a minimal benchmark slice, "
                "and evaluate whether it improves the source papers' stated limitations."
            ),
            (
                "Possible-extension notes may be broad and may not include enough detail "
                "to become an executable experiment without reading the full papers."
            ),
            "high",
        )
    return (
        f"Candidate follow-up for {dimension_text}",
        (
            "Use the source gap evidence to define a small comparison-first follow-up "
            f"study without adding unsupported claims.{constraint_text}"
        ),
        (
            "Validate the source gaps against the papers, define a measurable target, "
            "and run a small comparison using only explicitly available artifacts."
        ),
        "The source gap may be too broad to support a clean experiment.",
        "high",
    )


def _research_gap_text(gaps: Sequence[ResearchGapCard]) -> str:
    return " ".join(
        f"{gap.gap_id}: {gap.description}"
        for gap in gaps
    )


def _idea_evidence(gap: ResearchGapCard) -> CandidateIdeaEvidence:
    evidence_text = "; ".join(item.text for item in gap.evidence[:3])
    return CandidateIdeaEvidence(
        source_gap_id=gap.gap_id,
        gap_category=gap.category,
        source_dimensions=gap.source_dimensions,
        related_papers=gap.related_papers,
        text=evidence_text or gap.description,
        reason=(
            "This candidate idea is grounded in the gap card description and its "
            "evidence spans."
        ),
    )


def _specified_related_papers(gap: ResearchGapCard) -> list[str]:
    return [
        paper
        for paper in gap.related_papers
        if paper and paper.casefold() != NOT_SPECIFIED
    ]


def _dedupe_gaps(gaps: Sequence[ResearchGapCard]) -> list[ResearchGapCard]:
    deduped: list[ResearchGapCard] = []
    seen: set[str] = set()
    for gap in gaps:
        if gap.gap_id in seen:
            continue
        seen.add(gap.gap_id)
        deduped.append(gap)
    return deduped


def _dedupe_ideas(ideas: Sequence[CandidateIdeaCard]) -> list[CandidateIdeaCard]:
    deduped: list[CandidateIdeaCard] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for idea in ideas:
        key = (idea.research_gap.casefold(), tuple(sorted(idea.related_papers)))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(idea)
    return deduped


def _assign_idea_ids(ideas: Sequence[CandidateIdeaCard]) -> list[CandidateIdeaCard]:
    return [
        idea.model_copy(update={"idea_id": f"IDEA-{index:03d}"})
        for index, idea in enumerate(ideas, start=1)
    ]


def _limitations(ideas: Sequence[CandidateIdeaCard]) -> list[str]:
    limitations = [
        "Candidate ideas are generated only from evidence-backed gap cards.",
        "They must be checked manually against the original papers before any experiment.",
        "This output does not claim novelty, feasibility, or expected performance.",
    ]
    if any(idea.difficulty == "high" for idea in ideas):
        limitations.append("High-difficulty ideas likely require additional paper reading or artifacts.")
    return limitations


def _idea_markdown_lines(idea: CandidateIdeaCard) -> list[str]:
    lines = [
        f"### {idea.idea_id}: {idea.title}",
        "",
        f"- status: {idea.status}",
        f"- related_papers: {', '.join(idea.related_papers)}",
        f"- source_gap_ids: {', '.join(idea.source_gap_ids)}",
        f"- research_gap: {idea.research_gap}",
        f"- proposed_method: {idea.proposed_method}",
        f"- experiment_plan: {idea.experiment_plan}",
        f"- risk: {idea.risk}",
        f"- difficulty: {idea.difficulty}",
        "",
        "| Source Gap | Category | Dimensions | Related Papers | Evidence | Reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for evidence in idea.evidence:
        lines.append(
            "| "
            + " | ".join(
                _escape_table(value)
                for value in [
                    evidence.source_gap_id,
                    evidence.gap_category,
                    ", ".join(evidence.source_dimensions),
                    ", ".join(evidence.related_papers),
                    evidence.text,
                    evidence.reason,
                ]
            )
            + " |"
        )
    lines.append("")
    return lines


def _join_or_not_specified(values: Sequence[str]) -> str:
    return ", ".join(values) if values else NOT_SPECIFIED


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))
