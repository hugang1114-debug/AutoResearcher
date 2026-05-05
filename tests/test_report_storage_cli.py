from pathlib import Path

from autoresearcher.cli import main
from autoresearcher.models import PaperMetadata
from autoresearcher.report import build_markdown_report
from autoresearcher.storage import PaperStore


def test_storage_roundtrip(tmp_path: Path):
    db_path = tmp_path / "papers.sqlite"
    paper = PaperMetadata(
        title="A Test Paper",
        authors=["Ada", "Grace"],
        abstract="Test abstract",
        source="test",
        paper_id="p1",
        year=2025,
        relevance_score=1.2,
    )

    with PaperStore(db_path) as store:
        assert store.upsert_papers([paper]) == 1
        loaded = store.list_papers()

    assert loaded[0].title == "A Test Paper"
    assert loaded[0].authors == ["Ada", "Grace"]
    assert loaded[0].relevance_score == 1.2


def test_build_markdown_report_contains_sections():
    report = build_markdown_report(
        "rag evaluation",
        [PaperMetadata(title="RAG Metrics", source="test", relevance_score=0.9)],
    )

    assert "# AutoResearcher Report: rag evaluation" in report
    assert "## Top Papers" in report
    assert "## Research Idea Cards" in report
    assert "RAG Metrics" in report


def test_cli_runs_with_mocked_pipeline(monkeypatch, tmp_path: Path, capsys):
    def fake_pipeline(topic, limit, db_path, report_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(db_path).write_text("db", encoding="utf-8")
        Path(report_path).write_text("report", encoding="utf-8")

        class Result:
            papers = [PaperMetadata(title="Paper")]
            errors = []

            def __init__(self):
                self.topic = topic
                self.db_path = Path(db_path)
                self.report_path = Path(report_path)

        return Result()

    monkeypatch.setattr("autoresearcher.cli.run_research_pipeline", fake_pipeline)
    rc = main(
        [
            "test topic",
            "--limit",
            "1",
            "--db",
            str(tmp_path / "db.sqlite"),
            "--report",
            str(tmp_path / "report.md"),
        ]
    )

    output = capsys.readouterr().out
    assert rc == 0
    assert "Topic: test topic" in output
    assert "Papers: 1" in output
