from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from autoresearcher.analyzers.llm_client import LLMClient, NOT_SPECIFIED
from autoresearcher.analyzers.prompts import DEFAULT_MAX_TEXT_CHARS, build_paper_analysis_prompt

SourceSection = Literal[
    "abstract",
    "introduction",
    "method",
    "experiment",
    "limitation",
    "unknown",
]
ConfidenceLevel = Literal["low", "medium", "high"]


class PaperAnalysisError(RuntimeError):
    """Raised when evidence-based paper analysis fails."""


class EvidenceSpan(BaseModel):
    """Evidence supporting one analysis claim."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_section: SourceSection = "unknown"
    text: str = NOT_SPECIFIED
    reason: str = NOT_SPECIFIED

    @field_validator("text", "reason", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        return _normalize_missing_value(value)


class EvidenceBackedClaim(BaseModel):
    """A claim that must be grounded in explicit evidence."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    claim: str = NOT_SPECIFIED
    evidence: list[EvidenceSpan] = Field(default_factory=list)

    @field_validator("claim", mode="before")
    @classmethod
    def normalize_claim(cls, value: object) -> str:
        return _normalize_missing_value(value)

    @model_validator(mode="after")
    def require_evidence_for_claim(self) -> "EvidenceBackedClaim":
        self.evidence = [
            item
            for item in self.evidence
            if item.text != NOT_SPECIFIED and item.reason != NOT_SPECIFIED
        ]
        if self.claim != NOT_SPECIFIED and not self.evidence:
            self.claim = NOT_SPECIFIED
        if self.claim == NOT_SPECIFIED:
            self.evidence = []
        return self


class AnalysisConfidence(BaseModel):
    """Confidence summary for the structured analysis."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    level: ConfidenceLevel = "low"
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_information: list[str] = Field(default_factory=list)
    rationale: str = NOT_SPECIFIED

    @field_validator("rationale", mode="before")
    @classmethod
    def normalize_rationale(cls, value: object) -> str:
        return _normalize_missing_value(value)

    @field_validator("missing_information", mode="before")
    @classmethod
    def normalize_missing_information(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [
            _normalize_missing_value(item)
            for item in value
            if _normalize_missing_value(item) != NOT_SPECIFIED
        ]


class PaperAnalysisResult(BaseModel):
    """Validated evidence-based paper analysis."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = NOT_SPECIFIED
    problem: EvidenceBackedClaim = Field(default_factory=EvidenceBackedClaim)
    motivation: EvidenceBackedClaim = Field(default_factory=EvidenceBackedClaim)
    method: EvidenceBackedClaim = Field(default_factory=EvidenceBackedClaim)
    datasets: EvidenceBackedClaim = Field(default_factory=EvidenceBackedClaim)
    metrics: EvidenceBackedClaim = Field(default_factory=EvidenceBackedClaim)
    baselines: EvidenceBackedClaim = Field(default_factory=EvidenceBackedClaim)
    main_results: EvidenceBackedClaim = Field(default_factory=EvidenceBackedClaim)
    limitations: EvidenceBackedClaim = Field(default_factory=EvidenceBackedClaim)
    reproduction_notes: EvidenceBackedClaim = Field(default_factory=EvidenceBackedClaim)
    possible_extensions: EvidenceBackedClaim = Field(default_factory=EvidenceBackedClaim)
    confidence: AnalysisConfidence = Field(default_factory=AnalysisConfidence)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> str:
        return _normalize_missing_value(value)

    @model_validator(mode="after")
    def adjust_confidence_for_missing_evidence(self) -> "PaperAnalysisResult":
        missing = [
            field
            for field in ANALYSIS_CLAIM_FIELDS
            if getattr(self, field).claim == NOT_SPECIFIED
        ]
        merged_missing = list(dict.fromkeys([*self.confidence.missing_information, *missing]))
        self.confidence.missing_information = merged_missing
        missing_count = len(missing)
        evidence_count = sum(len(getattr(self, field).evidence) for field in ANALYSIS_CLAIM_FIELDS)
        if missing_count >= 6 or evidence_count <= 2:
            self.confidence.level = "low"
            self.confidence.score = min(self.confidence.score, 0.35)
        elif missing_count >= 3:
            if self.confidence.level == "high":
                self.confidence.level = "medium"
            self.confidence.score = min(self.confidence.score, 0.65)
        return self


class PaperCard(BaseModel):
    """A paper card ready for markdown export and downstream review."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    analysis: PaperAnalysisResult
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaperAnalyzer:
    """Convert metadata, abstract, and PDF text into an evidence-based paper card."""

    def __init__(
        self,
        llm_client: LLMClient,
        max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
    ) -> None:
        self.llm_client = llm_client
        self.max_text_chars = max_text_chars

    def analyze(
        self,
        *,
        title: str,
        abstract: str = "",
        pdf_text: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PaperCard:
        prompt = build_paper_analysis_prompt(
            title=title,
            abstract=abstract,
            pdf_text=pdf_text,
            metadata=metadata or {},
            max_text_chars=self.max_text_chars,
        )
        response = self.llm_client.generate(prompt)
        result = parse_analysis_response(response)
        if result.title == NOT_SPECIFIED and title:
            result.title = title
        return PaperCard(analysis=result, metadata=metadata or {})


def parse_analysis_response(response: str) -> PaperAnalysisResult:
    try:
        payload = json.loads(_extract_json_text(response))
    except json.JSONDecodeError as exc:
        raise PaperAnalysisError(f"LLM did not return valid JSON: {exc}") from exc
    try:
        return PaperAnalysisResult.model_validate(payload)
    except ValidationError as exc:
        raise PaperAnalysisError(f"LLM JSON failed validation: {exc}") from exc


def _extract_json_text(response: str) -> str:
    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and start < end:
        return text[start : end + 1]
    return text


def _normalize_missing_value(value: object) -> str:
    if value is None:
        return NOT_SPECIFIED
    if isinstance(value, list):
        value = "; ".join(str(item).strip() for item in value if str(item).strip())
    elif isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        value = str(value).strip()
    if not value or value.casefold() in MISSING_VALUES:
        return NOT_SPECIFIED
    return value


ANALYSIS_CLAIM_FIELDS = [
    "problem",
    "motivation",
    "method",
    "datasets",
    "metrics",
    "baselines",
    "main_results",
    "limitations",
    "reproduction_notes",
    "possible_extensions",
]

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
