from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Workspace(BaseModel):
    """A local-first workspace with stable output paths."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str
    root: str
    db_path: str
    reports_dir: str
    papers_dir: str
    text_dir: str
    cards_dir: str
    comparisons_dir: str
    reviews_dir: str
    gaps_dir: str | None = None
    ideas_dir: str | None = None
    reproduction_dir: str | None = None

    @property
    def root_path(self) -> Path:
        return Path(self.root)

    @property
    def card_json_dir(self) -> Path:
        return Path(self.cards_dir) / "json"

    @property
    def card_markdown_dir(self) -> Path:
        return Path(self.cards_dir) / "markdown"

    @property
    def gaps_path(self) -> Path:
        return Path(self.gaps_dir) if self.gaps_dir else self.root_path / "gaps"

    @property
    def ideas_path(self) -> Path:
        return Path(self.ideas_dir) if self.ideas_dir else self.root_path / "ideas"

    @property
    def reproduction_path(self) -> Path:
        return (
            Path(self.reproduction_dir)
            if self.reproduction_dir
            else self.root_path / "reproduction"
        )


def create_workspace(name: str, root: str | Path = "workspaces") -> Workspace:
    workspace_root = Path(root) / name
    workspace = Workspace(
        name=name,
        root=str(workspace_root),
        db_path=str(workspace_root / "data" / "autoresearcher.sqlite"),
        reports_dir=str(workspace_root / "reports"),
        papers_dir=str(workspace_root / "papers"),
        text_dir=str(workspace_root / "text"),
        cards_dir=str(workspace_root / "cards"),
        comparisons_dir=str(workspace_root / "comparisons"),
        reviews_dir=str(workspace_root / "reviews"),
        gaps_dir=str(workspace_root / "gaps"),
        ideas_dir=str(workspace_root / "ideas"),
        reproduction_dir=str(workspace_root / "reproduction"),
    )
    _ensure_workspace_dirs(workspace)
    _metadata_path(workspace).write_text(workspace.model_dump_json(indent=2), encoding="utf-8")
    return workspace


def load_workspace(name: str, root: str | Path = "workspaces") -> Workspace:
    workspace_root = Path(root) / name
    metadata_path = workspace_root / "workspace.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Workspace not found: {metadata_path}")
    return Workspace.model_validate_json(metadata_path.read_text(encoding="utf-8"))


def workspace_status(workspace: Workspace) -> dict[str, int | str]:
    return {
        "name": workspace.name,
        "root": workspace.root,
        "papers": _count_files(workspace.papers_dir, "*"),
        "text_files": _count_files(workspace.text_dir, "*"),
        "card_json": _count_files(workspace.card_json_dir, "*.json"),
        "card_markdown": _count_files(workspace.card_markdown_dir, "*.md"),
        "comparisons": _count_files(workspace.comparisons_dir, "*.json"),
        "reviews": _count_files(workspace.reviews_dir, "*.md"),
        "gaps": _count_files(workspace.gaps_path, "*.md"),
        "ideas": _count_files(workspace.ideas_path, "*.md"),
        "reproduction": _count_files(workspace.reproduction_path, "*.md"),
        "reports": _count_files(workspace.reports_dir, "*.md"),
    }


def _ensure_workspace_dirs(workspace: Workspace) -> None:
    for path in [
        Path(workspace.db_path).parent,
        Path(workspace.reports_dir),
        Path(workspace.papers_dir),
        Path(workspace.text_dir),
        workspace.card_json_dir,
        workspace.card_markdown_dir,
        Path(workspace.comparisons_dir),
        Path(workspace.reviews_dir),
        workspace.gaps_path,
        workspace.ideas_path,
        workspace.reproduction_path,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def _metadata_path(workspace: Workspace) -> Path:
    return workspace.root_path / "workspace.json"


def _count_files(path: str | Path, pattern: str) -> int:
    target = Path(path)
    if not target.exists():
        return 0
    return sum(1 for item in target.glob(pattern) if item.is_file())
