from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from autoresearcher.analyzers.llm_client import build_default_llm_client
from autoresearcher.analyzers.markdown_exporter import (
    build_paper_card_markdown,
    export_paper_card_markdown,
)
from autoresearcher.analyzers.paper_analyzer import PaperAnalyzer
from autoresearcher.batch.paper_card_batch import (
    BatchPaperInput,
    input_from_paper_metadata,
    load_batch_manifest,
    run_paper_card_batch,
)
from autoresearcher.comparison.matrix import (
    build_comparison_matrix,
    export_comparison_json,
    export_comparison_markdown,
    load_paper_card_json,
)
from autoresearcher.gaps.extractor import (
    export_research_gap_json,
    export_research_gap_markdown,
    extract_research_gaps,
    load_literature_review_outline_json,
)
from autoresearcher.ideas.candidate_generator import (
    IdeaGenerationError,
    export_candidate_idea_json,
    export_candidate_idea_markdown,
    generate_candidate_ideas,
    load_gap_extraction_json,
)
from autoresearcher.models import PaperMetadata
from autoresearcher.pdf.text_extractor import (
    export_extracted_pdf_json,
    export_extracted_pdf_text,
    extract_pdf_text,
)
from autoresearcher.pipeline import run_research_pipeline
from autoresearcher.review.outline import (
    build_literature_review_outline,
    export_literature_review_json,
    export_literature_review_markdown,
    load_comparison_matrix_json,
)
from autoresearcher.reproduction.planner import (
    export_reproduction_plan_json,
    export_reproduction_plan_markdown,
    load_idea_generation_json,
    plan_reproduction,
)
from autoresearcher.storage import PaperStore
from autoresearcher.workspace.core import create_workspace, load_workspace, workspace_status


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


def build_command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoresearcher",
        description="AutoResearcher command line tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser(
        "analyze",
        help="Analyze one paper into an evidence-based paper card.",
    )
    _add_analysis_arguments(analyze)
    analyze.add_argument(
        "--output",
        help="Optional Markdown output path. If omitted, prints the card to stdout.",
    )

    export_card = subparsers.add_parser(
        "export-card",
        help="Analyze one paper and export a Markdown paper card.",
    )
    _add_analysis_arguments(export_card)
    export_card.add_argument("--output", required=True, help="Markdown output path.")

    compare = subparsers.add_parser(
        "compare",
        help="Build a multi-paper comparison matrix from v0.2 card JSON files.",
    )
    compare.add_argument(
        "--input",
        action="append",
        required=True,
        help="Path to a PaperCard or PaperAnalysisResult JSON file. Repeat for multiple papers.",
    )
    compare.add_argument("--json-output", required=True, help="JSON matrix output path.")
    compare.add_argument("--markdown-output", required=True, help="Markdown matrix output path.")

    extract = subparsers.add_parser(
        "extract-pdf-text",
        help="Extract plain text and coarse sections from a local PDF.",
    )
    extract.add_argument("--pdf", required=True, help="Local PDF path.")
    extract.add_argument("--output", required=True, help="Extracted JSON output path.")
    extract.add_argument("--text-output", help="Optional plain text output path.")
    extract.add_argument(
        "--pages",
        help="Optional 1-based page range, e.g. '1-3' or '1,3,5'.",
    )

    batch = subparsers.add_parser(
        "batch-analyze",
        help="Build multiple evidence-based paper cards in one batch run.",
    )
    batch.add_argument("--manifest", help="JSON manifest with papers to analyze.")
    batch.add_argument(
        "--paper-id",
        action="append",
        help="Paper id, arXiv id, DOI, or source key from SQLite. Repeat for multiple papers.",
    )
    batch.add_argument(
        "--db",
        default="data/autoresearcher.sqlite",
        help="SQLite database path used with --paper-id.",
    )
    batch.add_argument("--output-dir", required=True, help="Directory for JSON and Markdown cards.")
    batch.add_argument(
        "--summary-output",
        help="Optional summary JSON path. Defaults to <output-dir>/batch_summary.json.",
    )
    batch.add_argument(
        "--mock",
        action="store_true",
        help="Force deterministic mock LLM mode.",
    )

    review = subparsers.add_parser(
        "review-outline",
        help="Build a literature review outline from comparison matrix JSON files.",
    )
    review.add_argument(
        "--matrix",
        action="append",
        required=True,
        help="Path to a comparison matrix JSON file. Repeat for multiple matrices.",
    )
    review.add_argument(
        "--title",
        default="Literature Review Outline",
        help="Outline title.",
    )
    review.add_argument("--output", required=True, help="Markdown outline output path.")
    review.add_argument("--json-output", help="Optional structured JSON outline output path.")

    gaps = subparsers.add_parser(
        "extract-gaps",
        help="Extract evidence-backed research gap candidates from comparison artifacts.",
    )
    gaps.add_argument(
        "--matrix",
        action="append",
        required=True,
        help="Path to a comparison matrix JSON file. Repeat for multiple matrices.",
    )
    gaps.add_argument(
        "--review-outline",
        action="append",
        help="Optional literature review outline JSON file. Repeat for multiple outlines.",
    )
    gaps.add_argument("--output", required=True, help="Markdown gap report output path.")
    gaps.add_argument("--json-output", help="Optional structured JSON gap output path.")

    ideas = subparsers.add_parser(
        "generate-ideas",
        help="Generate candidate research idea cards from v0.8 gap JSON files.",
    )
    ideas.add_argument(
        "--gaps",
        action="append",
        required=True,
        help="Path to a gap extraction JSON file. Repeat for multiple gap files.",
    )
    ideas.add_argument("--output", required=True, help="Markdown candidate idea output path.")
    ideas.add_argument("--json-output", help="Optional structured JSON idea output path.")
    ideas.add_argument("--min-ideas", type=int, default=1, help="Minimum grounded ideas required.")
    ideas.add_argument("--max-ideas", type=int, default=5, help="Maximum idea cards to emit.")
    ideas.add_argument(
        "--constraint",
        action="append",
        help="Optional user constraint such as compute budget or dataset availability.",
    )

    reproduction = subparsers.add_parser(
        "plan-reproduction",
        help="Create reproduction plans from paper cards or candidate ideas.",
    )
    reproduction.add_argument(
        "--idea",
        action="append",
        help="Path to a candidate idea JSON file. Repeat for multiple files.",
    )
    reproduction.add_argument(
        "--paper-card",
        action="append",
        help="Path to a PaperCard or PaperAnalysisResult JSON file. Repeat for multiple papers.",
    )
    reproduction.add_argument("--output", required=True, help="Markdown reproduction plan output path.")
    reproduction.add_argument("--json-output", help="Optional structured JSON plan output path.")
    reproduction.add_argument("--hardware", default="not specified", help="User hardware assumption or constraint.")
    reproduction.add_argument("--max-plans", type=int, help="Maximum plans to emit.")

    workspace_init = subparsers.add_parser(
        "workspace-init",
        help="Create a local AutoResearcher workspace.",
    )
    workspace_init.add_argument("--name", required=True, help="Workspace name.")
    workspace_init.add_argument("--root", default="workspaces", help="Workspace root directory.")

    workspace_status_cmd = subparsers.add_parser(
        "workspace-status",
        help="Show workspace file counts and paths.",
    )
    _add_workspace_reference_arguments(workspace_status_cmd)

    workspace_search = subparsers.add_parser(
        "workspace-search",
        help="Run paper search into a workspace database and report folder.",
    )
    _add_workspace_reference_arguments(workspace_search)
    workspace_search.add_argument("topic", help="Research topic or query.")
    workspace_search.add_argument("--limit", type=int, default=10, help="Maximum ranked papers to keep.")

    workspace_batch = subparsers.add_parser(
        "workspace-batch-analyze",
        help="Analyze the top papers stored in a workspace.",
    )
    _add_workspace_reference_arguments(workspace_batch)
    workspace_batch.add_argument("--top", type=int, default=5, help="Number of top stored papers to analyze.")
    workspace_batch.add_argument("--mock", action="store_true", help="Force deterministic mock LLM mode.")

    workspace_compare = subparsers.add_parser(
        "workspace-compare",
        help="Build a workspace comparison matrix from generated card JSON files.",
    )
    _add_workspace_reference_arguments(workspace_compare)
    workspace_compare.add_argument("--name-output", default="comparison", help="Output filename stem.")

    workspace_review = subparsers.add_parser(
        "workspace-review-outline",
        help="Build a workspace review outline from a comparison matrix.",
    )
    _add_workspace_reference_arguments(workspace_review)
    workspace_review.add_argument("--matrix", help="Comparison matrix JSON path.")
    workspace_review.add_argument("--title", default="Literature Review Outline", help="Outline title.")
    workspace_review.add_argument("--name-output", default="review_outline", help="Output filename stem.")

    workspace_gaps = subparsers.add_parser(
        "workspace-extract-gaps",
        help="Extract workspace gap candidates from the latest or specified matrix.",
    )
    _add_workspace_reference_arguments(workspace_gaps)
    workspace_gaps.add_argument("--matrix", help="Comparison matrix JSON path.")
    workspace_gaps.add_argument("--review-outline", help="Literature review outline JSON path.")
    workspace_gaps.add_argument("--name-output", default="research_gaps", help="Output filename stem.")

    workspace_ideas = subparsers.add_parser(
        "workspace-generate-ideas",
        help="Generate workspace candidate ideas from the latest or specified gap JSON.",
    )
    _add_workspace_reference_arguments(workspace_ideas)
    workspace_ideas.add_argument("--gaps", help="Gap extraction JSON path.")
    workspace_ideas.add_argument("--name-output", default="candidate_ideas", help="Output filename stem.")
    workspace_ideas.add_argument("--min-ideas", type=int, default=1, help="Minimum grounded ideas required.")
    workspace_ideas.add_argument("--max-ideas", type=int, default=5, help="Maximum idea cards to emit.")
    workspace_ideas.add_argument(
        "--constraint",
        action="append",
        help="Optional user constraint such as compute budget or dataset availability.",
    )

    workspace_reproduction = subparsers.add_parser(
        "workspace-plan-reproduction",
        help="Create workspace reproduction plans from idea JSON or paper-card JSON.",
    )
    _add_workspace_reference_arguments(workspace_reproduction)
    workspace_reproduction.add_argument("--idea", help="Candidate idea JSON path.")
    workspace_reproduction.add_argument("--paper-card", action="append", help="Paper card JSON path.")
    workspace_reproduction.add_argument("--name-output", default="reproduction_plan", help="Output filename stem.")
    workspace_reproduction.add_argument("--hardware", default="not specified", help="User hardware assumption or constraint.")
    workspace_reproduction.add_argument("--max-plans", type=int, help="Maximum plans to emit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in {
        "analyze",
        "export-card",
        "compare",
        "extract-pdf-text",
        "batch-analyze",
        "review-outline",
        "extract-gaps",
        "generate-ideas",
        "plan-reproduction",
        "workspace-init",
        "workspace-status",
        "workspace-search",
        "workspace-batch-analyze",
        "workspace-compare",
        "workspace-review-outline",
        "workspace-extract-gaps",
        "workspace-generate-ideas",
        "workspace-plan-reproduction",
    }:
        return _run_command(argv)
    return _run_search(argv)


def _run_search(argv: list[str]) -> int:
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


def _run_command(argv: list[str]) -> int:
    args = build_command_parser().parse_args(argv)
    if args.command == "compare":
        return _run_compare(args)
    if args.command == "extract-pdf-text":
        return _run_extract_pdf_text(args)
    if args.command == "batch-analyze":
        return _run_batch_analyze(args)
    if args.command == "review-outline":
        return _run_review_outline(args)
    if args.command == "extract-gaps":
        return _run_extract_gaps(args)
    if args.command == "generate-ideas":
        return _run_generate_ideas(args)
    if args.command == "plan-reproduction":
        return _run_plan_reproduction(args)
    if args.command == "workspace-init":
        return _run_workspace_init(args)
    if args.command == "workspace-status":
        return _run_workspace_status(args)
    if args.command == "workspace-search":
        return _run_workspace_search(args)
    if args.command == "workspace-batch-analyze":
        return _run_workspace_batch_analyze(args)
    if args.command == "workspace-compare":
        return _run_workspace_compare(args)
    if args.command == "workspace-review-outline":
        return _run_workspace_review_outline(args)
    if args.command == "workspace-extract-gaps":
        return _run_workspace_extract_gaps(args)
    if args.command == "workspace-generate-ideas":
        return _run_workspace_generate_ideas(args)
    if args.command == "workspace-plan-reproduction":
        return _run_workspace_plan_reproduction(args)
    card = _build_analysis_card(args)
    markdown = build_paper_card_markdown(card)
    if args.json_output:
        path = Path(args.json_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(card.model_dump_json(indent=2), encoding="utf-8")
        print(f"Paper card JSON: {path}")
    if args.output:
        path = export_paper_card_markdown(card, args.output)
        print(f"Paper card: {path}")
    else:
        print(markdown, end="")
    return 0


def _add_analysis_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--paper-id", help="Paper id, arXiv id, DOI, or source key from SQLite.")
    parser.add_argument("--title", help="Paper title.")
    parser.add_argument("--abstract", default="", help="Paper abstract.")
    parser.add_argument("--pdf-text", default="", help="Extracted PDF text.")
    parser.add_argument("--pdf-text-file", help="Path to a text file containing extracted PDF text.")
    parser.add_argument(
        "--db",
        default="data/autoresearcher.sqlite",
        help="SQLite database path used with --paper-id.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force deterministic mock LLM mode.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also print validated JSON analysis before Markdown output.",
    )
    parser.add_argument("--json-output", help="Optional PaperCard JSON output path.")


def _add_workspace_reference_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", required=True, help="Workspace name.")
    parser.add_argument("--root", default="workspaces", help="Workspace root directory.")


def _build_analysis_card(args: argparse.Namespace):
    paper = _load_paper_from_args(args)
    title = args.title or (paper.title if paper else "")
    if not title:
        raise SystemExit("analyze requires --title or --paper-id.")
    abstract = args.abstract or (paper.abstract if paper else "")
    pdf_text = _read_pdf_text(args)
    metadata = _metadata_from_paper(paper) if paper else {"title": title}
    analyzer = PaperAnalyzer(build_default_llm_client(mock=args.mock))
    card = analyzer.analyze(
        title=title,
        abstract=abstract,
        pdf_text=pdf_text,
        metadata=metadata,
    )
    if args.json:
        print(json.dumps(card.analysis.model_dump(), ensure_ascii=False, indent=2))
    return card


def _load_paper_from_args(args: argparse.Namespace) -> PaperMetadata | None:
    if not args.paper_id:
        return None
    with PaperStore(args.db) as store:
        paper = store.get_paper(args.paper_id)
    if paper is None:
        raise SystemExit(f"Paper not found in {args.db}: {args.paper_id}")
    return paper


def _read_pdf_text(args: argparse.Namespace) -> str:
    if args.pdf_text_file:
        return Path(args.pdf_text_file).read_text(encoding="utf-8")
    return args.pdf_text or ""


def _metadata_from_paper(paper: PaperMetadata) -> dict[str, object]:
    return {
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
    }


def _run_compare(args: argparse.Namespace) -> int:
    cards = [load_paper_card_json(path) for path in args.input]
    matrix = build_comparison_matrix(cards)
    json_path = export_comparison_json(matrix, args.json_output)
    markdown_path = export_comparison_markdown(matrix, args.markdown_output)
    print(f"Comparison JSON: {json_path}")
    print(f"Comparison Markdown: {markdown_path}")
    return 0


def _run_extract_pdf_text(args: argparse.Namespace) -> int:
    extracted = extract_pdf_text(args.pdf, page_range=args.pages)
    json_path = export_extracted_pdf_json(extracted, args.output)
    print(f"Extracted JSON: {json_path}")
    if args.text_output:
        text_path = export_extracted_pdf_text(extracted, args.text_output)
        print(f"Extracted text: {text_path}")
    if extracted.warnings:
        print("Extraction warnings:")
        for warning in extracted.warnings:
            print(f"- {warning}")
    return 0


def _run_batch_analyze(args: argparse.Namespace) -> int:
    inputs = _load_batch_inputs(args)
    if not inputs:
        raise SystemExit("batch-analyze requires --manifest and/or --paper-id.")
    output_dir = Path(args.output_dir)
    summary_output = args.summary_output or str(output_dir / "batch_summary.json")
    summary = run_paper_card_batch(
        inputs,
        output_dir=output_dir,
        llm_client=build_default_llm_client(mock=args.mock),
        summary_output=summary_output,
    )
    print(f"Batch total: {summary.total}")
    print(f"Succeeded: {summary.succeeded}")
    print(f"Failed: {summary.failed}")
    print(f"Summary: {summary_output}")
    return 0


def _load_batch_inputs(args: argparse.Namespace) -> list[BatchPaperInput]:
    inputs: list[BatchPaperInput] = []
    if args.manifest:
        inputs.extend(load_batch_manifest(args.manifest))
    if args.paper_id:
        with PaperStore(args.db) as store:
            for paper_id in args.paper_id:
                paper = store.get_paper(paper_id)
                if paper is None:
                    inputs.append(BatchPaperInput(id=paper_id))
                else:
                    inputs.append(input_from_paper_metadata(paper))
    return inputs


def _run_review_outline(args: argparse.Namespace) -> int:
    matrices = [load_comparison_matrix_json(path) for path in args.matrix]
    outline = build_literature_review_outline(matrices, title=args.title)
    markdown_path = export_literature_review_markdown(outline, args.output)
    print(f"Review outline: {markdown_path}")
    if args.json_output:
        json_path = export_literature_review_json(outline, args.json_output)
        print(f"Review outline JSON: {json_path}")
    return 0


def _run_extract_gaps(args: argparse.Namespace) -> int:
    matrices = [load_comparison_matrix_json(path) for path in args.matrix]
    outlines = [
        load_literature_review_outline_json(path)
        for path in (args.review_outline or [])
    ]
    result = extract_research_gaps(matrices, outlines)
    markdown_path = export_research_gap_markdown(result, args.output)
    print(f"Research gaps: {markdown_path}")
    if args.json_output:
        json_path = export_research_gap_json(result, args.json_output)
        print(f"Research gaps JSON: {json_path}")
    return 0


def _run_generate_ideas(args: argparse.Namespace) -> int:
    gap_results = [load_gap_extraction_json(path) for path in args.gaps]
    try:
        result = generate_candidate_ideas(
            gap_results,
            min_ideas=args.min_ideas,
            max_ideas=args.max_ideas,
            constraints=args.constraint or [],
        )
    except IdeaGenerationError as exc:
        raise SystemExit(str(exc)) from exc
    markdown_path = export_candidate_idea_markdown(result, args.output)
    print(f"Candidate ideas: {markdown_path}")
    if args.json_output:
        json_path = export_candidate_idea_json(result, args.json_output)
        print(f"Candidate ideas JSON: {json_path}")
    return 0


def _run_plan_reproduction(args: argparse.Namespace) -> int:
    if not args.idea and not args.paper_card:
        raise SystemExit("plan-reproduction requires --idea and/or --paper-card.")
    result = plan_reproduction(
        idea_results=[load_idea_generation_json(path) for path in (args.idea or [])],
        paper_cards=[load_paper_card_json(path) for path in (args.paper_card or [])],
        hardware=args.hardware,
        max_plans=args.max_plans,
    )
    markdown_path = export_reproduction_plan_markdown(result, args.output)
    print(f"Reproduction plan: {markdown_path}")
    if args.json_output:
        json_path = export_reproduction_plan_json(result, args.json_output)
        print(f"Reproduction plan JSON: {json_path}")
    return 0


def _run_workspace_init(args: argparse.Namespace) -> int:
    workspace = create_workspace(args.name, root=args.root)
    print(f"Workspace: {workspace.root}")
    print(f"Database: {workspace.db_path}")
    return 0


def _run_workspace_status(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.name, root=args.root)
    status = workspace_status(workspace)
    for key, value in status.items():
        print(f"{key}: {value}")
    return 0


def _run_workspace_search(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.name, root=args.root)
    safe_topic = _slugify_for_cli(args.topic) or "research_report"
    report_path = Path(workspace.reports_dir) / f"{safe_topic}.md"
    result = run_research_pipeline(
        topic=args.topic,
        limit=args.limit,
        db_path=workspace.db_path,
        report_path=report_path,
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


def _run_workspace_batch_analyze(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.name, root=args.root)
    with PaperStore(workspace.db_path) as store:
        papers = store.list_papers(limit=args.top)
    if not papers:
        raise SystemExit(f"No papers found in workspace database: {workspace.db_path}")
    inputs = [input_from_paper_metadata(paper) for paper in papers]
    summary_path = Path(workspace.cards_dir) / "batch_summary.json"
    summary = run_paper_card_batch(
        inputs,
        output_dir=workspace.cards_dir,
        llm_client=build_default_llm_client(mock=args.mock),
        summary_output=summary_path,
    )
    print(f"Batch total: {summary.total}")
    print(f"Succeeded: {summary.succeeded}")
    print(f"Failed: {summary.failed}")
    print(f"Summary: {summary_path}")
    return 0


def _run_workspace_compare(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.name, root=args.root)
    card_paths = sorted(workspace.card_json_dir.glob("*.json"))
    if len(card_paths) < 2:
        raise SystemExit("workspace-compare requires at least two card JSON files.")
    cards = [load_paper_card_json(path) for path in card_paths]
    matrix = build_comparison_matrix(cards)
    stem = _slugify_for_cli(args.name_output) or "comparison"
    json_path = Path(workspace.comparisons_dir) / f"{stem}.json"
    markdown_path = Path(workspace.comparisons_dir) / f"{stem}.md"
    export_comparison_json(matrix, json_path)
    export_comparison_markdown(matrix, markdown_path)
    print(f"Comparison JSON: {json_path}")
    print(f"Comparison Markdown: {markdown_path}")
    return 0


def _run_workspace_review_outline(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.name, root=args.root)
    matrix_path = Path(args.matrix) if args.matrix else _latest_file(workspace.comparisons_dir, "*.json")
    if matrix_path is None:
        raise SystemExit("No comparison matrix JSON found in workspace.")
    outline = build_literature_review_outline(
        [load_comparison_matrix_json(matrix_path)],
        title=args.title,
    )
    stem = _slugify_for_cli(args.name_output) or "review_outline"
    markdown_path = Path(workspace.reviews_dir) / f"{stem}.md"
    json_path = Path(workspace.reviews_dir) / f"{stem}.json"
    export_literature_review_markdown(outline, markdown_path)
    export_literature_review_json(outline, json_path)
    print(f"Review outline: {markdown_path}")
    print(f"Review outline JSON: {json_path}")
    return 0


def _run_workspace_extract_gaps(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.name, root=args.root)
    matrix_path = Path(args.matrix) if args.matrix else _latest_file(workspace.comparisons_dir, "*.json")
    if matrix_path is None:
        raise SystemExit("No comparison matrix JSON found in workspace.")
    review_path = (
        Path(args.review_outline)
        if args.review_outline
        else _latest_file(workspace.reviews_dir, "*.json")
    )
    outlines = [load_literature_review_outline_json(review_path)] if review_path else []
    result = extract_research_gaps([load_comparison_matrix_json(matrix_path)], outlines)
    stem = _slugify_for_cli(args.name_output) or "research_gaps"
    markdown_path = workspace.gaps_path / f"{stem}.md"
    json_path = workspace.gaps_path / f"{stem}.json"
    export_research_gap_markdown(result, markdown_path)
    export_research_gap_json(result, json_path)
    print(f"Research gaps: {markdown_path}")
    print(f"Research gaps JSON: {json_path}")
    return 0


def _run_workspace_generate_ideas(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.name, root=args.root)
    gaps_path = Path(args.gaps) if args.gaps else _latest_file(workspace.gaps_path, "*.json")
    if gaps_path is None:
        raise SystemExit("No gap extraction JSON found in workspace.")
    try:
        result = generate_candidate_ideas(
            [load_gap_extraction_json(gaps_path)],
            min_ideas=args.min_ideas,
            max_ideas=args.max_ideas,
            constraints=args.constraint or [],
        )
    except IdeaGenerationError as exc:
        raise SystemExit(str(exc)) from exc
    stem = _slugify_for_cli(args.name_output) or "candidate_ideas"
    markdown_path = workspace.ideas_path / f"{stem}.md"
    json_path = workspace.ideas_path / f"{stem}.json"
    export_candidate_idea_markdown(result, markdown_path)
    export_candidate_idea_json(result, json_path)
    print(f"Candidate ideas: {markdown_path}")
    print(f"Candidate ideas JSON: {json_path}")
    return 0


def _run_workspace_plan_reproduction(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.name, root=args.root)
    idea_path = Path(args.idea) if args.idea else _latest_file(workspace.ideas_path, "*.json")
    paper_card_paths = [Path(path) for path in (args.paper_card or [])]
    if idea_path is None and not paper_card_paths:
        raise SystemExit("No candidate idea JSON or paper card JSON found for reproduction planning.")
    result = plan_reproduction(
        idea_results=[load_idea_generation_json(idea_path)] if idea_path else [],
        paper_cards=[load_paper_card_json(path) for path in paper_card_paths],
        hardware=args.hardware,
        max_plans=args.max_plans,
    )
    stem = _slugify_for_cli(args.name_output) or "reproduction_plan"
    markdown_path = workspace.reproduction_path / f"{stem}.md"
    json_path = workspace.reproduction_path / f"{stem}.json"
    export_reproduction_plan_markdown(result, markdown_path)
    export_reproduction_plan_json(result, json_path)
    print(f"Reproduction plan: {markdown_path}")
    print(f"Reproduction plan JSON: {json_path}")
    return 0


def _latest_file(directory: str | Path, pattern: str) -> Path | None:
    files = sorted(Path(directory).glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _slugify_for_cli(value: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in value.lower()).strip("-")


if __name__ == "__main__":
    raise SystemExit(main())
