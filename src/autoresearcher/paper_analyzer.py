from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

NOT_SPECIFIED = "not specified"
DEFAULT_MAX_PDF_CHARS = 12000


class PaperAnalysisError(RuntimeError):
    """Raised when a paper analysis cannot be produced or validated."""


class LLMConfigurationError(PaperAnalysisError):
    """Raised when a real LLM client is missing required configuration."""


class LLMClient(Protocol):
    """Minimal interface required by the paper analyzer."""

    def generate(self, prompt: str) -> str:
        """Return an LLM response as a string."""


class PaperAnalysis(BaseModel):
    """Structured paper analysis returned by an LLM and validated by Pydantic."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    research_problem: str = Field(default=NOT_SPECIFIED)
    motivation: str = Field(default=NOT_SPECIFIED)
    method: str = Field(default=NOT_SPECIFIED)
    datasets: str = Field(default=NOT_SPECIFIED)
    metrics: str = Field(default=NOT_SPECIFIED)
    key_findings: str = Field(default=NOT_SPECIFIED)
    limitations: str = Field(default=NOT_SPECIFIED)
    future_work: str = Field(default=NOT_SPECIFIED)
    reproduction_notes: str = Field(default=NOT_SPECIFIED)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_missing_values(cls, value: object) -> str:
        if value is None:
            return NOT_SPECIFIED
        if isinstance(value, list):
            value = "; ".join(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            value = str(value).strip()
        if value.casefold() in MISSING_VALUES:
            return NOT_SPECIFIED
        return value or NOT_SPECIFIED


class OpenAICompatibleLLMClient:
    """Small stdlib client for OpenAI-compatible chat-completions endpoints."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError("api_key is required.")
        if not model:
            raise LLMConfigurationError("model is required.")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "OpenAICompatibleLLMClient":
        api_key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("AUTORESEARCHER_LLM_MODEL", "")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if not api_key:
            raise LLMConfigurationError("Set OPENAI_API_KEY before using the LLM client.")
        if not model:
            raise LLMConfigurationError("Set AUTORESEARCHER_LLM_MODEL before using the LLM client.")
        return cls(api_key=api_key, model=model, base_url=base_url)

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You analyze research papers. Return valid JSON only. "
                        f"When evidence is missing, write exactly {NOT_SPECIFIED!r}."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "AutoResearcher/0.1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise PaperAnalysisError(f"LLM request failed: {exc.code} {details}") from exc
        except urllib.error.URLError as exc:
            raise PaperAnalysisError(f"LLM request failed: {exc.reason}") from exc
        return body["choices"][0]["message"]["content"]


class PaperAnalyzer:
    """Analyze one paper using an injected LLM client."""

    def __init__(
        self,
        llm_client: LLMClient,
        max_pdf_chars: int = DEFAULT_MAX_PDF_CHARS,
    ) -> None:
        self.llm_client = llm_client
        self.max_pdf_chars = max_pdf_chars

    def analyze(self, title: str, abstract: str, pdf_text: str) -> PaperAnalysis:
        prompt = build_analysis_prompt(
            title=title,
            abstract=abstract,
            pdf_text=pdf_text,
            max_pdf_chars=self.max_pdf_chars,
        )
        response = self.llm_client.generate(prompt)
        return parse_analysis_response(response)


def build_analysis_prompt(
    title: str,
    abstract: str,
    pdf_text: str,
    max_pdf_chars: int = DEFAULT_MAX_PDF_CHARS,
) -> str:
    fields = "\n".join(f"- {field}" for field in PaperAnalysis.model_fields)
    truncated_pdf_text = truncate_text(pdf_text, max_pdf_chars)
    return f"""Analyze the research paper using only the supplied title, abstract, and PDF text.

Rules:
- Return one valid JSON object and no extra text.
- The JSON object must contain exactly these string fields:
{fields}
- If the provided material does not contain enough evidence for a field, use exactly "{NOT_SPECIFIED}".
- Do not infer details from outside knowledge.
- Do not invent datasets, metrics, results, limitations, or future work.

Title:
{title or NOT_SPECIFIED}

Abstract:
{abstract or NOT_SPECIFIED}

PDF text:
{truncated_pdf_text or NOT_SPECIFIED}
"""


def parse_analysis_response(response: str) -> PaperAnalysis:
    try:
        payload = json.loads(_extract_json_text(response))
    except json.JSONDecodeError as exc:
        raise PaperAnalysisError(f"LLM did not return valid JSON: {exc}") from exc
    try:
        return PaperAnalysis.model_validate(payload)
    except ValidationError as exc:
        raise PaperAnalysisError(f"LLM JSON failed validation: {exc}") from exc


def build_paper_card(title: str, analysis: PaperAnalysis) -> str:
    rows = [
        ("Research problem", analysis.research_problem),
        ("Motivation", analysis.motivation),
        ("Method", analysis.method),
        ("Datasets", analysis.datasets),
        ("Metrics", analysis.metrics),
        ("Key findings", analysis.key_findings),
        ("Limitations", analysis.limitations),
        ("Future work", analysis.future_work),
        ("Reproduction notes", analysis.reproduction_notes),
    ]
    lines = [
        f"## Paper Card: {title or NOT_SPECIFIED}",
        "",
        "| Field | Analysis |",
        "| --- | --- |",
    ]
    for field, value in rows:
        lines.append(f"| {field} | {_escape_markdown_table(value)} |")
    return "\n".join(lines) + "\n"


def truncate_text(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "\n[truncated]"


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


def _escape_markdown_table(value: str) -> str:
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
