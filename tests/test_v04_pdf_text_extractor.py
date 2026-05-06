import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, TextStringObject

from autoresearcher.cli import main
from autoresearcher.pdf.text_extractor import (
    extract_pdf_text,
    export_extracted_pdf_json,
    export_extracted_pdf_text,
    split_into_sections,
)


def test_split_into_sections_detects_common_paper_headings():
    text = """Title line
Abstract
This paper evaluates retrieval failures.
Introduction
RAG systems can fail during retrieval.
Method
We retry retrieval when evidence is weak.
Experiments
We evaluate on a QA benchmark.
Limitations
Only English data is considered.
References
[1] Example
"""

    sections = split_into_sections(text)

    assert [section.name for section in sections] == [
        "unknown",
        "abstract",
        "introduction",
        "method",
        "experiment",
        "limitation",
        "references",
    ]
    assert sections[1].text == "This paper evaluates retrieval failures."


def test_extract_pdf_text_reads_local_pdf_and_sections(tmp_path: Path):
    pdf_path = tmp_path / "paper.pdf"
    _write_text_pdf(
        pdf_path,
        [
            "Abstract\nThis paper evaluates retrieval failures.\nIntroduction\nRAG systems can fail.",
            "Method\nWe retry retrieval.\nExperiments\nWe report exact match.",
        ],
    )

    extracted = extract_pdf_text(pdf_path)

    assert extracted.source_path == str(pdf_path)
    assert extracted.page_count == 2
    assert "This paper evaluates retrieval failures." in extracted.text
    assert {section.name for section in extracted.sections} >= {"abstract", "method", "experiment"}
    assert extracted.warnings == []


def test_extract_pdf_text_page_range(tmp_path: Path):
    pdf_path = tmp_path / "paper.pdf"
    _write_text_pdf(pdf_path, ["Abstract\nPage one.", "Method\nPage two."])

    extracted = extract_pdf_text(pdf_path, page_range="2")

    assert "Page two." in extracted.text
    assert "Page one." not in extracted.text


def test_extract_pdf_text_rejects_invalid_page_range(tmp_path: Path):
    pdf_path = tmp_path / "paper.pdf"
    _write_text_pdf(pdf_path, ["Abstract\nPage one."])

    with pytest.raises(ValueError):
        extract_pdf_text(pdf_path, page_range="2")


def test_export_extracted_pdf_json_and_text(tmp_path: Path):
    pdf_path = tmp_path / "paper.pdf"
    json_path = tmp_path / "paper.json"
    text_path = tmp_path / "paper.txt"
    _write_text_pdf(pdf_path, ["Abstract\nExport this text."])

    extracted = extract_pdf_text(pdf_path)
    export_extracted_pdf_json(extracted, json_path)
    export_extracted_pdf_text(extracted, text_path)

    assert json.loads(json_path.read_text(encoding="utf-8"))["page_count"] == 1
    assert "Export this text." in text_path.read_text(encoding="utf-8")


def test_cli_extract_pdf_text_command(tmp_path: Path):
    pdf_path = tmp_path / "paper.pdf"
    json_path = tmp_path / "out.json"
    text_path = tmp_path / "out.txt"
    _write_text_pdf(pdf_path, ["Abstract\nCLI extraction works."])

    rc = main(
        [
            "extract-pdf-text",
            "--pdf",
            str(pdf_path),
            "--output",
            str(json_path),
            "--text-output",
            str(text_path),
        ]
    )

    assert rc == 0
    assert "CLI extraction works." in text_path.read_text(encoding="utf-8")
    assert json.loads(json_path.read_text(encoding="utf-8"))["sections"][0]["name"] == "abstract"


def _write_text_pdf(path: Path, pages: list[str]) -> None:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        font_ref = writer._add_object(font)
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {
                        NameObject("/F1"): font_ref,
                    }
                )
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(_pdf_text_stream(text).encode("utf-8"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as file:
        writer.write(file)


def _pdf_text_stream(text: str) -> str:
    escaped_lines = [_escape_pdf_text(line) for line in text.splitlines()]
    commands = ["BT", "/F1 12 Tf", "72 720 Td"]
    for index, line in enumerate(escaped_lines):
        if index:
            commands.append("0 -16 Td")
        commands.append(f"({line}) Tj")
    commands.append("ET")
    return "\n".join(commands)


def _escape_pdf_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )
