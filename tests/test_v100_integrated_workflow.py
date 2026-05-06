import json
from pathlib import Path

from autoresearcher.analyzers.llm_client import NOT_SPECIFIED
from autoresearcher.analyzers.paper_analyzer import PaperAnalysisResult, PaperCard
from autoresearcher.cli import main
from autoresearcher.workspace.core import create_workspace, workspace_status


def test_v100_workspace_workflow_from_cards_to_reproduction_plan(tmp_path: Path):
    workspace = create_workspace("rag-review", root=tmp_path)
    _write_card(workspace.card_json_dir / "paper-a.json", _paper_card("Paper A", "Natural Questions.", "Exact match.", "BM25.", "Only English QA."))
    _write_card(workspace.card_json_dir / "paper-b.json", _paper_card("Paper B", "HotpotQA.", "F1.", NOT_SPECIFIED, "High inference cost."))

    rc = main(
        [
            "workspace-compare",
            "--name",
            workspace.name,
            "--root",
            str(tmp_path),
            "--name-output",
            "matrix",
        ]
    )
    assert rc == 0
    assert (Path(workspace.comparisons_dir) / "matrix.json").exists()

    rc = main(
        [
            "workspace-review-outline",
            "--name",
            workspace.name,
            "--root",
            str(tmp_path),
            "--title",
            "RAG Review",
            "--name-output",
            "review",
        ]
    )
    assert rc == 0
    assert (Path(workspace.reviews_dir) / "review.json").exists()

    rc = main(
        [
            "workspace-extract-gaps",
            "--name",
            workspace.name,
            "--root",
            str(tmp_path),
            "--name-output",
            "gaps",
        ]
    )
    assert rc == 0
    gaps_path = workspace.gaps_path / "gaps.json"
    gap_payload = json.loads(gaps_path.read_text(encoding="utf-8"))
    assert any(gap["category"] == "evaluation_mismatch" for gap in gap_payload["gaps"])

    rc = main(
        [
            "workspace-generate-ideas",
            "--name",
            workspace.name,
            "--root",
            str(tmp_path),
            "--name-output",
            "ideas",
            "--constraint",
            "single GPU",
        ]
    )
    assert rc == 0
    ideas_path = workspace.ideas_path / "ideas.json"
    idea_payload = json.loads(ideas_path.read_text(encoding="utf-8"))
    assert idea_payload["idea_cards"]

    rc = main(
        [
            "workspace-plan-reproduction",
            "--name",
            workspace.name,
            "--root",
            str(tmp_path),
            "--name-output",
            "reproduction",
            "--hardware",
            "single GPU",
        ]
    )
    assert rc == 0
    plan_path = workspace.reproduction_path / "reproduction.json"
    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan_payload["plans"]
    assert plan_payload["plans"][0]["commands"]

    status = workspace_status(workspace)
    assert status["card_json"] == 2
    assert status["comparisons"] == 1
    assert status["reviews"] == 1
    assert status["gaps"] == 1
    assert status["ideas"] == 1
    assert status["reproduction"] == 1


def _write_card(path: Path, card: PaperCard) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(card.model_dump_json(indent=2), encoding="utf-8")


def _paper_card(
    title: str,
    datasets: str,
    metrics: str,
    baselines: str,
    limitations: str,
) -> PaperCard:
    return PaperCard(
        analysis=PaperAnalysisResult.model_validate(
            {
                "title": title,
                "problem": _claim("Evaluate RAG retrieval failures."),
                "motivation": _claim("Retrieval failures reduce answer grounding."),
                "method": _claim(f"{title} uses a retrieval correction pipeline."),
                "datasets": _claim(datasets),
                "metrics": _claim(metrics),
                "baselines": _claim(baselines),
                "main_results": _claim("Improves answer grounding."),
                "limitations": _claim(limitations),
                "reproduction_notes": _claim("Requires retriever logs and QA labels."),
                "possible_extensions": _claim("Evaluate multilingual QA."),
                "confidence": {
                    "level": "medium",
                    "score": 0.7,
                    "missing_information": [],
                    "rationale": "Integrated workflow fixture.",
                },
            }
        ),
        metadata={"source": "fixture", "paper_id": title.lower().replace(" ", "-")},
    )


def _claim(value: str):
    if value == NOT_SPECIFIED:
        return {"claim": NOT_SPECIFIED, "evidence": []}
    return {
        "claim": value,
        "evidence": [
            {
                "source_section": "abstract",
                "text": value,
                "reason": "Integrated workflow fixture evidence.",
            }
        ],
    }
