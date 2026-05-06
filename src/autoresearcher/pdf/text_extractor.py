from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

SectionName = Literal[
    "abstract",
    "introduction",
    "method",
    "experiment",
    "limitation",
    "references",
    "unknown",
]


class PDFSection(BaseModel):
    """A coarse section extracted from PDF text."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: SectionName
    text: str


class ExtractedPDF(BaseModel):
    """Text extraction result for one local PDF."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_path: str
    page_count: int
    text: str
    sections: list[PDFSection] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def extract_pdf_text(pdf_path: str | Path, page_range: str | None = None) -> ExtractedPDF:
    """Extract plain text and coarse sections from a local PDF.

    This intentionally does not perform OCR or layout understanding. It is a
    light ingestion step for feeding v0.2 paper analysis.
    """
    path = Path(pdf_path)
    reader = PdfReader(str(path))
    selected_pages = _parse_page_range(page_range, len(reader.pages))
    warnings: list[str] = []
    page_texts: list[str] = []
    for index in selected_pages:
        text = reader.pages[index].extract_text() or ""
        if not text.strip():
            warnings.append(f"page {index + 1} has no extractable text")
        page_texts.append(text)
    combined_text = _normalize_text("\n\n".join(page_texts))
    if not combined_text:
        warnings.append("no extractable text found; OCR is not supported in v0.4")
    sections = split_into_sections(combined_text)
    return ExtractedPDF(
        source_path=str(path),
        page_count=len(reader.pages),
        text=combined_text,
        sections=sections,
        warnings=warnings,
    )


def split_into_sections(text: str) -> list[PDFSection]:
    normalized = _normalize_text(text)
    if not normalized:
        return [PDFSection(name="unknown", text="")]
    matches = list(SECTION_PATTERN.finditer(normalized))
    if not matches:
        return [PDFSection(name="unknown", text=normalized)]
    sections: list[PDFSection] = []
    if matches[0].start() > 0:
        preface = normalized[: matches[0].start()].strip()
        if preface:
            sections.append(PDFSection(name="unknown", text=preface))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        section_text = normalized[start:end].strip()
        if section_text:
            sections.append(
                PDFSection(
                    name=_section_name(match.group(1)),
                    text=section_text,
                )
            )
    return sections or [PDFSection(name="unknown", text=normalized)]


def export_extracted_pdf_json(extracted: ExtractedPDF, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(extracted.model_dump_json(indent=2), encoding="utf-8")
    return path


def export_extracted_pdf_text(extracted: ExtractedPDF, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(extracted.text, encoding="utf-8")
    return path


def _parse_page_range(page_range: str | None, page_count: int) -> list[int]:
    if not page_range:
        return list(range(page_count))
    pages: set[int] = set()
    for chunk in page_range.split(","):
        part = chunk.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start > end:
                raise ValueError(f"invalid page range: {part}")
            pages.update(range(start - 1, end))
        else:
            pages.add(int(part) - 1)
    invalid = [page + 1 for page in pages if page < 0 or page >= page_count]
    if invalid:
        raise ValueError(f"page out of range: {invalid}")
    return sorted(pages)


def _normalize_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    compact_lines = [line for line in lines if line]
    return "\n".join(compact_lines).strip()


def _section_name(raw_heading: str) -> SectionName:
    heading = raw_heading.casefold()
    if "abstract" in heading:
        return "abstract"
    if "intro" in heading:
        return "introduction"
    if any(term in heading for term in ("method", "approach", "model")):
        return "method"
    if any(term in heading for term in ("experiment", "evaluation", "result")):
        return "experiment"
    if any(term in heading for term in ("limitation", "discussion")):
        return "limitation"
    if "reference" in heading:
        return "references"
    return "unknown"


SECTION_PATTERN = re.compile(
    r"(?im)^(?:\d+(?:\.\d+)*\s+)?"
    r"(abstract|introduction|related work|method(?:ology)?|approach|model|"
    r"experiments?|evaluation|results?|limitations?|discussion|references)\b"
    r"[^\n]*\n"
)
