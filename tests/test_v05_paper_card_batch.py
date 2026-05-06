import json
from pathlib import Path

from autoresearcher.analyzers.llm_client import MockLLMClient
from autoresearcher.batch.paper_card_batch import (
    BatchPaperInput,
    input_from_paper_metadata,
    load_batch_manifest,
    run_paper_card_batch,
)
from autoresearcher.cli import main
from autoresearcher.models import PaperMetadata
from autoresearcher.storage import PaperStore


def test_load_batch_manifest_accepts_papers_object(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "id": "paper-a",
                        "title": "Paper A",
                        "abstract": "This paper evaluates RAG failures.",
                        "metadata": {"source": "manual"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    inputs = load_batch_manifest(manifest)

    assert inputs[0].id == "paper-a"
    assert inputs[0].title == "Paper A"
    assert inputs[0].metadata == {"source": "manual"}


def test_load_batch_manifest_accepts_utf8_bom(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        "\ufeff" + json.dumps([{"id": "paper-a", "title": "Paper A"}]),
        encoding="utf-8",
    )

    inputs = load_batch_manifest(manifest)

    assert inputs[0].id == "paper-a"


def test_run_paper_card_batch_writes_outputs_and_continues_after_failure(tmp_path: Path):
    text_file = tmp_path / "paper_a.txt"
    text_file.write_text("Method\nWe retry retrieval.", encoding="utf-8")
    summary_path = tmp_path / "summary.json"

    summary = run_paper_card_batch(
        [
            BatchPaperInput(
                id="paper-a",
                title="Paper A",
                abstract="This paper evaluates RAG failures.",
                pdf_text_file=str(text_file),
            ),
            BatchPaperInput(id="broken-paper"),
        ],
        output_dir=tmp_path / "cards",
        llm_client=MockLLMClient(),
        summary_output=summary_path,
    )

    assert summary.total == 2
    assert summary.succeeded == 1
    assert summary.failed == 1
    assert summary.outputs[0].json_path is not None
    assert Path(summary.outputs[0].json_path).exists()
    assert Path(summary.outputs[0].markdown_path).exists()
    assert summary.outputs[1].error == "title is required"
    assert json.loads(summary_path.read_text(encoding="utf-8"))["failed"] == 1


def test_input_from_paper_metadata_preserves_core_fields():
    paper = PaperMetadata(
        title="Stored Paper",
        abstract="Stored abstract.",
        source="test",
        paper_id="stored-1",
        year=2026,
    )

    batch_input = input_from_paper_metadata(paper)

    assert batch_input.id == "stored-1"
    assert batch_input.title == "Stored Paper"
    assert batch_input.abstract == "Stored abstract."
    assert batch_input.metadata["year"] == 2026


def test_cli_batch_analyze_manifest(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    output_dir = tmp_path / "batch"
    manifest.write_text(
        json.dumps(
            [
                {
                    "id": "paper-a",
                    "title": "Paper A",
                    "abstract": "This paper evaluates retrieval failures.",
                }
            ]
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "batch-analyze",
            "--manifest",
            str(manifest),
            "--mock",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert rc == 0
    assert (output_dir / "json" / "paper-a.json").exists()
    assert (output_dir / "markdown" / "paper-a.md").exists()
    assert json.loads((output_dir / "batch_summary.json").read_text(encoding="utf-8"))["succeeded"] == 1


def test_cli_batch_analyze_sqlite_paper_ids(tmp_path: Path):
    db_path = tmp_path / "papers.sqlite"
    output_dir = tmp_path / "batch"
    with PaperStore(db_path) as store:
        store.upsert_papers(
            [
                PaperMetadata(
                    title="Stored Paper",
                    abstract="This paper studies corrective retrieval.",
                    source="test",
                    paper_id="stored-1",
                )
            ]
        )

    rc = main(
        [
            "batch-analyze",
            "--paper-id",
            "stored-1",
            "--paper-id",
            "missing-1",
            "--db",
            str(db_path),
            "--mock",
            "--output-dir",
            str(output_dir),
        ]
    )

    summary = json.loads((output_dir / "batch_summary.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert summary["succeeded"] == 1
    assert summary["failed"] == 1
    assert (output_dir / "json" / "stored-1.json").exists()
