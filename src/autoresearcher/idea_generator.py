from __future__ import annotations

from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from autoresearcher.paper_analyzer import NOT_SPECIFIED


class IdeaGenerationError(RuntimeError):
    """Raised when there is not enough evidence to generate grounded ideas."""


class PaperCard(BaseModel):
    """Minimal structured representation parsed from a markdown paper card."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str
    problem: str = Field(default=NOT_SPECIFIED)
    method: str = Field(default=NOT_SPECIFIED)
    datasets: str = Field(default=NOT_SPECIFIED)
    metrics: str = Field(default=NOT_SPECIFIED)
    limitations: str = Field(default=NOT_SPECIFIED)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_missing_values(cls, value: object) -> str:
        text = str(value or "").strip()
        if not text or text.casefold() in MISSING_VALUES:
            return NOT_SPECIFIED
        return text


class ResearchIdeaCard(BaseModel):
    """Evidence-backed research idea card."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    related_papers: list[str] = Field(min_length=1)
    research_gap: str
    proposed_method: str
    experiment_plan: str
    risk: str
    difficulty: Literal["low", "medium", "high"]

    @field_validator("research_gap", "proposed_method", "experiment_plan", "risk", mode="before")
    @classmethod
    def require_text(cls, value: object) -> str:
        text = str(value or "").strip()
        if not text or text.casefold() in MISSING_VALUES:
            raise ValueError("idea fields must be grounded in paper-card evidence")
        return text


def parse_paper_card(markdown: str) -> PaperCard:
    """Parse one markdown paper card produced by paper_analyzer.build_paper_card."""
    title = _parse_title(markdown)
    fields: dict[str, str] = {}
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        cells = _split_markdown_table_row(stripped)
        if len(cells) < 2 or cells[0].casefold() == "field":
            continue
        key = _normalize_label(cells[0])
        fields[key] = cells[1]
    return PaperCard(
        title=title,
        problem=fields.get("research problem", NOT_SPECIFIED),
        method=fields.get("method", NOT_SPECIFIED),
        datasets=fields.get("datasets", NOT_SPECIFIED),
        metrics=fields.get("metrics", NOT_SPECIFIED),
        limitations=fields.get("limitations", NOT_SPECIFIED),
    )


def parse_paper_cards(markdown: str) -> list[PaperCard]:
    """Parse multiple paper cards from a single markdown document."""
    chunks: list[str] = []
    current: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## Paper Card:") and current:
            chunks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current))
    return [parse_paper_card(chunk) for chunk in chunks if "Paper Card:" in chunk]


def generate_research_idea_cards(
    paper_cards: Sequence[str | PaperCard],
    min_ideas: int = 3,
    max_ideas: int = 5,
) -> list[ResearchIdeaCard]:
    """Generate 3-5 grounded ideas from multiple paper cards.

    The generator is deterministic and evidence constrained. It uses only
    problem, method, datasets, metrics, and limitations explicitly present in
    the input cards. If there is not enough evidence for at least min_ideas,
    it raises IdeaGenerationError instead of inventing ideas.
    """
    cards = _normalize_paper_cards(paper_cards)
    if len(cards) < 2:
        raise IdeaGenerationError("At least two paper cards are required.")
    candidates = [
        _dataset_generalization_idea(cards),
        _metric_alignment_idea(cards),
        _method_comparison_idea(cards),
        _limitation_driven_idea(cards),
        _problem_slice_idea(cards),
    ]
    ideas = _dedupe_ideas([idea for idea in candidates if idea is not None])
    if len(ideas) < min_ideas:
        raise IdeaGenerationError(
            f"Only {len(ideas)} evidence-backed ideas could be generated; "
            f"{min_ideas} are required."
        )
    return ideas[:max_ideas]


def build_idea_markdown_report(
    paper_cards: Sequence[str | PaperCard],
    min_ideas: int = 3,
    max_ideas: int = 5,
) -> str:
    cards = _normalize_paper_cards(paper_cards)
    ideas = generate_research_idea_cards(cards, min_ideas=min_ideas, max_ideas=max_ideas)
    lines = [
        "# Research Idea Report",
        "",
        "## Paper Comparison",
        "",
        build_comparison_table(cards),
        "",
        "## Research Idea Cards",
        "",
    ]
    for index, idea in enumerate(ideas, start=1):
        lines.extend(_idea_card_lines(index, idea))
    return "\n".join(lines).rstrip() + "\n"


def export_idea_markdown_report(
    paper_cards: Sequence[str | PaperCard],
    output_path: str | Path,
    min_ideas: int = 3,
    max_ideas: int = 5,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        build_idea_markdown_report(
            paper_cards,
            min_ideas=min_ideas,
            max_ideas=max_ideas,
        ),
        encoding="utf-8",
    )
    return path


def build_comparison_table(paper_cards: Sequence[str | PaperCard]) -> str:
    cards = _normalize_paper_cards(paper_cards)
    lines = [
        "| Paper | Problem | Method | Datasets | Metrics | Limitations |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for card in cards:
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_table(card.title),
                    _escape_table(card.problem),
                    _escape_table(card.method),
                    _escape_table(card.datasets),
                    _escape_table(card.metrics),
                    _escape_table(card.limitations),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _dataset_generalization_idea(cards: list[PaperCard]) -> ResearchIdeaCard | None:
    evidence_cards = _cards_with(cards, "datasets")
    if len(evidence_cards) < 2 or _unique_values(evidence_cards, "datasets") < 2:
        return None
    method_cards = _cards_with(evidence_cards, "method") or _cards_with(cards, "method")
    metric_cards = _cards_with(cards, "metrics")
    return ResearchIdeaCard(
        related_papers=_titles(evidence_cards),
        research_gap=(
            "The cards use different stated datasets without a shared cross-dataset "
            f"evaluation: {_evidence(evidence_cards, 'datasets')}."
        ),
        proposed_method=(
            "Run the stated methods on the stated datasets: "
            f"{_evidence(method_cards, 'method')}."
        ),
        experiment_plan=(
            "Build a paper-by-dataset evaluation matrix using "
            f"{_evidence(evidence_cards, 'datasets')} and score it with "
            f"{_evidence(metric_cards, 'metrics') if metric_cards else NOT_SPECIFIED}."
        ),
        risk=(
            "Dataset and task definitions may not be directly compatible because the "
            "cards specify dataset names but not splits or preprocessing."
        ),
        difficulty="high" if len(evidence_cards) >= 3 else "medium",
    )


def _metric_alignment_idea(cards: list[PaperCard]) -> ResearchIdeaCard | None:
    evidence_cards = _cards_with(cards, "metrics")
    if len(evidence_cards) < 2 or _unique_values(evidence_cards, "metrics") < 2:
        return None
    return ResearchIdeaCard(
        related_papers=_titles(evidence_cards),
        research_gap=(
            "The cards report different metrics for related evaluations: "
            f"{_evidence(evidence_cards, 'metrics')}."
        ),
        proposed_method=(
            "Create a common evaluation protocol that reports every metric explicitly "
            f"named in the cards: {_join_unique_values(evidence_cards, 'metrics')}."
        ),
        experiment_plan=(
            "For each related paper, rerun or re-score the stated method with the "
            "shared metric set and compare rankings before and after metric alignment."
        ),
        risk=(
            "Some metrics may require predictions, labels, or intermediate outputs "
            "that the cards do not specify."
        ),
        difficulty="medium",
    )


def _method_comparison_idea(cards: list[PaperCard]) -> ResearchIdeaCard | None:
    evidence_cards = _cards_with(cards, "method")
    if len(evidence_cards) < 2 or _unique_values(evidence_cards, "method") < 2:
        return None
    dataset_cards = _cards_with(cards, "datasets")
    metric_cards = _cards_with(cards, "metrics")
    return ResearchIdeaCard(
        related_papers=_titles(evidence_cards),
        research_gap=(
            "The cards describe different methods but do not show a controlled "
            f"comparison across them: {_evidence(evidence_cards, 'method')}."
        ),
        proposed_method=(
            "Treat each stated method as an experimental arm and compare them under "
            "the same datasets and metrics already listed in the paper cards."
        ),
        experiment_plan=(
            "Implement the stated methods, evaluate on "
            f"{_evidence(dataset_cards, 'datasets') if dataset_cards else NOT_SPECIFIED}, "
            "and report "
            f"{_evidence(metric_cards, 'metrics') if metric_cards else NOT_SPECIFIED}."
        ),
        risk=(
            "The cards do not specify enough implementation detail to guarantee a "
            "faithful method reproduction."
        ),
        difficulty="high",
    )


def _limitation_driven_idea(cards: list[PaperCard]) -> ResearchIdeaCard | None:
    evidence_cards = _cards_with(cards, "limitations")
    if not evidence_cards:
        return None
    method_cards = _cards_with(evidence_cards, "method") or _cards_with(cards, "method")
    return ResearchIdeaCard(
        related_papers=_titles(evidence_cards),
        research_gap=(
            "The cards explicitly list limitations that can be turned into targeted "
            f"experiments: {_evidence(evidence_cards, 'limitations')}."
        ),
        proposed_method=(
            "Use the related papers' stated methods as baselines and design stress "
            "tests focused only on the stated limitations."
        ),
        experiment_plan=(
            "For each limitation, run the corresponding stated method "
            f"({_evidence(method_cards, 'method') if method_cards else NOT_SPECIFIED}) "
            "on the paper's stated dataset or metric setup and measure the failure mode."
        ),
        risk=(
            "A limitation may be qualitative, so the cards may not contain enough "
            "detail to convert every limitation into a numeric test."
        ),
        difficulty="medium" if len(evidence_cards) <= 2 else "high",
    )


def _problem_slice_idea(cards: list[PaperCard]) -> ResearchIdeaCard | None:
    evidence_cards = _cards_with(cards, "problem")
    if len(evidence_cards) < 2 or _unique_values(evidence_cards, "problem") < 2:
        return None
    method_cards = _cards_with(cards, "method")
    metric_cards = _cards_with(cards, "metrics")
    return ResearchIdeaCard(
        related_papers=_titles(evidence_cards),
        research_gap=(
            "The cards frame nearby but different research problems: "
            f"{_evidence(evidence_cards, 'problem')}."
        ),
        proposed_method=(
            "Build a problem-slice benchmark from the stated problem descriptions "
            "and evaluate the stated methods inside each slice."
        ),
        experiment_plan=(
            "Map each paper to its stated problem slice, evaluate "
            f"{_evidence(method_cards, 'method') if method_cards else NOT_SPECIFIED}, "
            "and compare outcomes using "
            f"{_evidence(metric_cards, 'metrics') if metric_cards else NOT_SPECIFIED}."
        ),
        risk=(
            "Problem descriptions in the cards may be too broad to define clean, "
            "non-overlapping slices without reading the full papers."
        ),
        difficulty="medium",
    )


def _normalize_paper_cards(paper_cards: Sequence[str | PaperCard]) -> list[PaperCard]:
    cards: list[PaperCard] = []
    for item in paper_cards:
        cards.append(item if isinstance(item, PaperCard) else parse_paper_card(item))
    return cards


def _cards_with(cards: list[PaperCard], field: str) -> list[PaperCard]:
    return [card for card in cards if _is_specified(getattr(card, field))]


def _is_specified(value: str) -> bool:
    return bool(value) and value.casefold() not in MISSING_VALUES


def _unique_values(cards: list[PaperCard], field: str) -> int:
    return len({getattr(card, field).casefold() for card in cards if _is_specified(getattr(card, field))})


def _titles(cards: list[PaperCard]) -> list[str]:
    return [card.title for card in cards]


def _evidence(cards: list[PaperCard], field: str) -> str:
    return "; ".join(f"{card.title}: {getattr(card, field)}" for card in cards)


def _join_unique_values(cards: list[PaperCard], field: str) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for card in cards:
        value = getattr(card, field)
        key = value.casefold()
        if _is_specified(value) and key not in seen:
            seen.add(key)
            values.append(value)
    return "; ".join(values)


def _dedupe_ideas(ideas: list[ResearchIdeaCard]) -> list[ResearchIdeaCard]:
    unique: list[ResearchIdeaCard] = []
    seen: set[str] = set()
    for idea in ideas:
        key = idea.research_gap.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(idea)
    return unique


def _idea_card_lines(index: int, idea: ResearchIdeaCard) -> list[str]:
    return [
        f"### Idea {index}",
        "",
        f"- related_papers: {', '.join(idea.related_papers)}",
        f"- research_gap: {idea.research_gap}",
        f"- proposed_method: {idea.proposed_method}",
        f"- experiment_plan: {idea.experiment_plan}",
        f"- risk: {idea.risk}",
        f"- difficulty: {idea.difficulty}",
        "",
    ]


def _parse_title(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("## Paper Card:"):
            title = line.split(":", 1)[1].strip()
            return title or NOT_SPECIFIED
    return NOT_SPECIFIED


def _normalize_label(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _split_markdown_table_row(row: str) -> list[str]:
    text = row.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "|":
            cells.append(_clean_cell("".join(current)))
            current = []
            continue
        current.append(char)
    if escaped:
        current.append("\\")
    cells.append(_clean_cell("".join(current)))
    return cells


def _clean_cell(value: str) -> str:
    return value.strip().replace("<br>", "\n")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


MISSING_VALUES = {
    "",
    "n/a",
    "na",
    "none",
    "not available",
    "not mentioned",
    "not provided",
    "not specified",
    "not stated",
    "null",
    "unknown",
    "unspecified",
}
