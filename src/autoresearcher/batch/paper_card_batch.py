from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from autoresearcher.analyzers.llm_client import LLMClient
from autoresearcher.analyzers.markdown_exporter import export_paper_card_markdown
from autoresearcher.analyzers.paper_analyzer import PaperAnalyzer
from autoresearcher.models import PaperMetadata


class BatchPaperInput(BaseModel):
    """One paper to analyze in a batch run."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str | None = None
    title: str | None = None
    abstract: str = ""
    pdf_text: str = ""
    pdf_text_file: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata", mode="before")
    @classmethod
    def normalize_metadata(cls, value: object) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}


class BatchPaperOutput(BaseModel):
    """Per-paper batch result."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    input_id: str
    title: str
    status: Literal["succeeded", "failed"]
    json_path: str | None = None
    markdown_path: str | None = None
    error: str | None = None


class BatchAnalysisSummary(BaseModel):
    """Summary for a batch paper-card run."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    total: int
    succeeded: int
    failed: int
    outputs: list[BatchPaperOutput]


def load_batch_manifest(path: str | Path) -> list[BatchPaperInput]:
    """Load batch inputs from JSON.

    Supported shapes:
    - `[{"title": "...", ...}]`
    - `{"papers": [{"title": "...", ...}]}`
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    items = payload.get("papers", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("Batch manifest must be a list or an object with a 'papers' list.")
    return [BatchPaperInput.model_validate(item) for item in items]


def input_from_paper_metadata(paper: PaperMetadata) -> BatchPaperInput:
    return BatchPaperInput(
        id=paper.paper_id or paper.arxiv_id or paper.doi or paper.source_key(),
        title=paper.title,
        abstract=paper.abstract,
        metadata={
            "title": paper.title,
            "authors": paper.authors,
            "source": paper.source,
            "paper_id": paper.paper_id,
            "doi": paper.doi,
            "arxiv_id": paper.arxiv_id,
            "url": paper.url,
            "published_at": paper.published_at,
            "year": paper.year,
            "venue": paper.venue,
            "citation_count": paper.citation_count,
            "pdf_url": paper.pdf_url,
        },
    )


def run_paper_card_batch(
    inputs: Sequence[BatchPaperInput],
    output_dir: str | Path,
    llm_client: LLMClient,
    summary_output: str | Path | None = None,
) -> BatchAnalysisSummary:
    """Analyze multiple papers and continue after per-paper failures."""
    output = Path(output_dir)
    json_dir = output / "json"
    markdown_dir = output / "markdown"
    json_dir.mkdir(parents=True, exist_ok=True)
    markdown_dir.mkdir(parents=True, exist_ok=True)

    analyzer = PaperAnalyzer(llm_client)
    results: list[BatchPaperOutput] = []
    used_slugs: set[str] = set()
    for index, item in enumerate(inputs, start=1):
        input_id = item.id or f"paper-{index}"
        title = item.title or ""
        try:
            if not title:
                raise ValueError("title is required")
            pdf_text = _resolve_pdf_text(item)
            metadata = {"id": input_id, **item.metadata}
            card = analyzer.analyze(
                title=title,
                abstract=item.abstract,
                pdf_text=pdf_text,
                metadata=metadata,
            )
            slug = _unique_slug(_slugify(input_id or title), used_slugs)
            json_path = json_dir / f"{slug}.json"
            markdown_path = markdown_dir / f"{slug}.md"
            json_path.write_text(card.model_dump_json(indent=2), encoding="utf-8")
            export_paper_card_markdown(card, markdown_path)
            results.append(
                BatchPaperOutput(
                    input_id=input_id,
                    title=title,
                    status="succeeded",
                    json_path=str(json_path),
                    markdown_path=str(markdown_path),
                )
            )
        except Exception as exc:
            results.append(
                BatchPaperOutput(
                    input_id=input_id,
                    title=title or "not specified",
                    status="failed",
                    error=str(exc),
                )
            )

    summary = BatchAnalysisSummary(
        total=len(results),
        succeeded=sum(1 for result in results if result.status == "succeeded"),
        failed=sum(1 for result in results if result.status == "failed"),
        outputs=results,
    )
    if summary_output is not None:
        path = Path(summary_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    return summary


def _resolve_pdf_text(item: BatchPaperInput) -> str:
    if item.pdf_text_file:
        return Path(item.pdf_text_file).read_text(encoding="utf-8")
    return item.pdf_text


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    return slug[:80] or "paper"


def _unique_slug(slug: str, used_slugs: set[str]) -> str:
    candidate = slug
    counter = 2
    while candidate in used_slugs:
        candidate = f"{slug}-{counter}"
        counter += 1
    used_slugs.add(candidate)
    return candidate
