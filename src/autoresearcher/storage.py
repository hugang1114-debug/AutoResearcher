from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from autoresearcher.models import PaperMetadata


SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    source_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT,
    abstract TEXT,
    url TEXT,
    source TEXT,
    paper_id TEXT,
    doi TEXT,
    arxiv_id TEXT,
    published_at TEXT,
    year INTEGER,
    citation_count INTEGER,
    venue TEXT,
    pdf_url TEXT,
    relevance_score REAL DEFAULT 0
);
"""


class PaperStore:
    """Small SQLite repository for normalized papers."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.connection.execute(SCHEMA)
        self.connection.commit()

    def upsert_papers(self, papers: Iterable[PaperMetadata]) -> int:
        rows = [paper.to_record() for paper in papers]
        if not rows:
            return 0
        self.connection.executemany(
            """
            INSERT INTO papers (
                source_key, title, authors, abstract, url, source, paper_id,
                doi, arxiv_id, published_at, year, citation_count, venue,
                pdf_url, relevance_score
            )
            VALUES (
                :source_key, :title, :authors, :abstract, :url, :source,
                :paper_id, :doi, :arxiv_id, :published_at, :year,
                :citation_count, :venue, :pdf_url, :relevance_score
            )
            ON CONFLICT(source_key) DO UPDATE SET
                title = excluded.title,
                authors = excluded.authors,
                abstract = excluded.abstract,
                url = excluded.url,
                source = excluded.source,
                paper_id = excluded.paper_id,
                doi = excluded.doi,
                arxiv_id = excluded.arxiv_id,
                published_at = excluded.published_at,
                year = excluded.year,
                citation_count = excluded.citation_count,
                venue = excluded.venue,
                pdf_url = excluded.pdf_url,
                relevance_score = excluded.relevance_score
            """,
            rows,
        )
        self.connection.commit()
        return len(rows)

    def list_papers(self, limit: int | None = None) -> list[PaperMetadata]:
        sql = "SELECT * FROM papers ORDER BY relevance_score DESC, year DESC"
        params: tuple[int, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        rows = self.connection.execute(sql, params).fetchall()
        return [PaperMetadata.from_record(dict(row)) for row in rows]

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "PaperStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
