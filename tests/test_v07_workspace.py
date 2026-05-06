import json
from pathlib import Path

from autoresearcher.analyzers.llm_client import MockLLMClient
from autoresearcher.batch.paper_card_batch import input_from_paper_metadata, run_paper_card_batch
from autoresearcher.cli import main
from autoresearcher.comparison.matrix import export_comparison_json, build_comparison_matrix
from autoresearcher.models import PaperMetadata
from autoresearcher.storage import PaperStore
from autoresearcher.workspace.core import create_workspace, load_workspace, workspace_status


def test_create_and_load_workspace(tmp_path: Path):
    workspace = create_workspace("rag-review", root=tmp_path)

    loaded = load_workspace("rag-review", root=tmp_path)

    assert loaded == workspace
    assert Path(workspace.db_path).parent.exists()
    assert workspace.card_json_dir.exists()
    assert (Path(workspace.root) / "workspace.json").exists()


def test_workspace_status_counts_outputs(tmp_path: Path):
    workspace = create_workspace("rag-review", root=tmp_path)
    workspace.card_json_dir.joinpath("a.json").write_text("{}", encoding="utf-8")
    Path(workspace.reviews_dir).joinpath("outline.md").write_text("# Outline", encoding="utf-8")

    status = workspace_status(workspace)

    assert status["card_json"] == 1
    assert status["reviews"] == 1


def test_cli_workspace_init_and_status(tmp_path: Path, capsys):
    rc = main(["workspace-init", "--name", "rag-review", "--root", str(tmp_path)])

    assert rc == 0
    assert (tmp_path / "rag-review" / "workspace.json").exists()

    rc = main(["workspace-status", "--name", "rag-review", "--root", str(tmp_path)])
    output = capsys.readouterr().out

    assert rc == 0
    assert "name: rag-review" in output
    assert "card_json: 0" in output


def test_cli_workspace_search_uses_workspace_paths(monkeypatch, tmp_path: Path):
    workspace = create_workspace("rag-review", root=tmp_path)
    captured = {}

    class Result:
        topic = "rag"
        papers = [PaperMetadata(title="Paper")]
        errors = []

        def __init__(self, db_path, report_path):
            self.db_path = Path(db_path)
            self.report_path = Path(report_path)

    def fake_pipeline(topic, limit, db_path, report_path):
        captured.update(
            {
                "topic": topic,
                "limit": limit,
                "db_path": Path(db_path),
                "report_path": Path(report_path),
            }
        )
        return Result(db_path, report_path)

    monkeypatch.setattr("autoresearcher.cli.run_research_pipeline", fake_pipeline)

    rc = main(
        [
            "workspace-search",
            "--name",
            workspace.name,
            "--root",
            str(tmp_path),
            "Adaptive RAG",
            "--limit",
            "3",
        ]
    )

    assert rc == 0
    assert captured["db_path"] == Path(workspace.db_path)
    assert captured["report_path"].parent == Path(workspace.reports_dir)
    assert captured["limit"] == 3


def test_cli_workspace_batch_compare_and_review(tmp_path: Path):
    workspace = create_workspace("rag-review", root=tmp_path)
    with PaperStore(workspace.db_path) as store:
        store.upsert_papers(
            [
                PaperMetadata(
                    title="Paper A",
                    abstract="This paper evaluates retrieval failures.",
                    source="test",
                    paper_id="a",
                    relevance_score=2.0,
                ),
                PaperMetadata(
                    title="Paper B",
                    abstract="This paper studies corrective retrieval.",
                    source="test",
                    paper_id="b",
                    relevance_score=1.5,
                ),
            ]
        )

    rc = main(
        [
            "workspace-batch-analyze",
            "--name",
            workspace.name,
            "--root",
            str(tmp_path),
            "--top",
            "2",
            "--mock",
        ]
    )
    assert rc == 0
    assert len(list(workspace.card_json_dir.glob("*.json"))) == 2

    rc = main(
        [
            "workspace-compare",
            "--name",
            workspace.name,
            "--root",
            str(tmp_path),
            "--name-output",
            "rag-comparison",
        ]
    )
    assert rc == 0
    matrix_path = Path(workspace.comparisons_dir) / "rag-comparison.json"
    assert matrix_path.exists()

    rc = main(
        [
            "workspace-review-outline",
            "--name",
            workspace.name,
            "--root",
            str(tmp_path),
            "--matrix",
            str(matrix_path),
            "--title",
            "RAG Review",
            "--name-output",
            "rag-review",
        ]
    )
    assert rc == 0
    assert (Path(workspace.reviews_dir) / "rag-review.md").exists()
    assert json.loads((Path(workspace.reviews_dir) / "rag-review.json").read_text(encoding="utf-8"))["title"] == "RAG Review"


def test_workspace_compare_requires_two_cards(tmp_path: Path):
    workspace = create_workspace("rag-review", root=tmp_path)
    run_paper_card_batch(
        [input_from_paper_metadata(PaperMetadata(title="Paper A", abstract="Abstract.", paper_id="a"))],
        output_dir=workspace.cards_dir,
        llm_client=MockLLMClient(),
    )

    rc = None
    try:
        rc = main(["workspace-compare", "--name", workspace.name, "--root", str(tmp_path)])
    except SystemExit as exc:
        assert "at least two card JSON files" in str(exc)
    assert rc is None
