from __future__ import annotations

import argparse
from pathlib import Path

from autoresearcher.pipeline import run_research_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoresearcher",
        description="Search papers and export a compact research report.",
    )
    parser.add_argument("topic", help="Research topic or query.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum ranked papers to keep.")
    parser.add_argument(
        "--db",
        default="data/autoresearcher.sqlite",
        help="SQLite database path.",
    )
    parser.add_argument(
        "--report",
        default="reports/research_report.md",
        help="Markdown report output path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_research_pipeline(
        topic=args.topic,
        limit=args.limit,
        db_path=Path(args.db),
        report_path=Path(args.report),
    )
    print(f"Topic: {result.topic}")
    print(f"Papers: {len(result.papers)}")
    print(f"Database: {result.db_path}")
    print(f"Report: {result.report_path}")
    if result.errors:
        print("Source warnings:")
        for error in result.errors:
            print(f"- {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
