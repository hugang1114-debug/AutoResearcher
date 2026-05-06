# AutoResearcher Roadmap: v0.3 to v1.0

AutoResearcher is a long-term literature workflow tool. It should help collect,
read, compare, and organize papers for later human review and separate
experimental projects. It should not pretend to fully automate research.

## v0.3: Multi-paper Comparison Matrix

Goal: compare multiple evidence-based paper cards without generating final
research ideas.

Input:
- `PaperAnalysisResult` or `PaperCard` objects.
- JSON files containing those objects for CLI usage.

Output:
- JSON comparison matrix.
- Markdown comparison matrix for literature review notes.

Core modules:
- `autoresearcher.comparison.matrix`
- CLI command: `compare`

Test focus:
- Matrix schema.
- JSON export.
- Markdown export.
- `not comparable` handling.
- CLI compare command.
- v0.1 search and v0.2 analysis remain stable.

## v0.4: Paper PDF Text Ingestion

Goal: add a small, reliable path from a PDF file to text that can feed v0.2
analysis.

Status: implemented as local PDF text extraction and coarse section splitting.

Input:
- Local PDF path.
- Optional page range.

Output:
- Extracted text file.
- Basic extraction metadata such as page count and warnings.

Core modules:
- `autoresearcher.pdf.text_extractor`
- CLI command: `extract-pdf-text`

Test focus:
- Text extraction from a small fixture PDF.
- Empty or scanned PDF failure modes.
- Page range handling.
- No network calls.

## v0.5: Batch Paper Card Builder

Goal: analyze multiple stored or local papers into evidence-based paper cards in
one repeatable run.

Status: implemented for curated manifest inputs and SQLite paper ids.

Input:
- SQLite paper ids.
- Local metadata and text files.
- Optional output directory.

Output:
- One JSON analysis file per paper.
- One Markdown paper card per paper.
- Batch summary with failures and missing information.

Core modules:
- `autoresearcher.batch.paper_card_batch`
- Existing v0.2 analyzer and v0.4 PDF text extraction.

Test focus:
- Batch continues after one failed paper.
- Mock LLM mode.
- Output naming and manifest correctness.
- No external APIs in tests.

## v0.6: Literature Review Outline

Goal: turn comparison matrices into a review-oriented outline without claiming
novel research ideas.

Status: implemented as deterministic outline generation from comparison matrix
JSON files.

Input:
- One or more v0.3 comparison matrices.

Output:
- Markdown literature review outline.
- Topic clusters grounded in compared fields.

Core modules:
- `autoresearcher.review.outline`

Test focus:
- Outline uses only matrix content.
- Missing or incomparable fields are preserved.
- No final idea cards generated.

## v0.7: Workspace Workflow Glue

Goal: tie the completed search, paper-card, comparison, and review-outline
steps into a stable local workspace layout.

Status: implemented as workspace init/status/search/batch/compare/review CLI
commands.

Input:
- Workspace name.
- Research topic.
- Stored workspace papers and card JSON files.

Output:
- Workspace directory containing database, reports, cards, comparisons, and
  review outlines.

Core modules:
- `autoresearcher.workspace.core`
- Existing search, batch, comparison, and review modules.

Test focus:
- Workspace path creation.
- Existing modules write to workspace paths.
- Status counts are stable.
- No new research claims are generated.

## v0.8: Research Gap Extraction

Goal: extract candidate gaps from limitations, evaluation mismatches, dataset
coverage, and method assumptions.

Status: implemented as deterministic extraction from comparison matrices and
optional review outlines. It records evidence-backed gap candidates but does not
generate final research ideas.

Input:
- Comparison matrix.
- Literature review outline.

Output:
- Evidence-backed gap cards.

Core modules:
- `autoresearcher.gaps.extractor`
- CLI commands: `extract-gaps`, `workspace-extract-gaps`

Test focus:
- Every gap cites source papers and fields.
- No unsupported gaps.
- `not specified` and `not comparable` do not become fake gaps.

## v0.9: Candidate Research Idea Cards

Goal: generate early candidate ideas from evidence-backed gaps, still requiring
human review before experiments.

Status: implemented as deterministic candidate idea generation from v0.8 gap
cards. Every emitted idea must trace back to gap evidence and at least two
related papers.

Input:
- Gap cards.
- Optional constraints such as compute budget or dataset availability.

Output:
- Candidate idea cards with evidence, risks, and validation plan sketches.

Core modules:
- `autoresearcher.ideas.candidate_generator`
- CLI commands: `generate-ideas`, `workspace-generate-ideas`

Test focus:
- Ideas must trace back to gap evidence.
- Ideas include risk and difficulty.
- No final claims of novelty or feasibility.

## v0.10: Reproduction Planning

Goal: produce practical reproduction plans for selected papers or candidate
ideas.

Status: implemented as template-based reproduction planning from v0.2 paper
cards and v0.9 candidate idea cards. It creates operational checklists but does
not execute experiments.

Input:
- Paper card or idea card.
- User-provided environment assumptions.

Output:
- Reproduction plan with datasets, hardware assumptions, commands, risks, and
  success checks.

Core modules:
- `autoresearcher.reproduction.planner`
- CLI commands: `plan-reproduction`, `workspace-plan-reproduction`

Test focus:
- Plan includes all required operational sections.
- Unknown hardware or data is marked `not specified`.
- No automatic experiment execution.

## v1.0: Integrated Literature Workflow

Goal: stabilize the end-to-end workflow from search to paper cards, comparison
matrices, review outlines, gap cards, candidate ideas, and reproduction plans.

Status: implemented as a stable workspace workflow with CLI documentation and
an end-to-end mock test covering cards, comparison, review outline, gap
extraction, candidate ideas, and reproduction planning.

Input:
- Research topic.
- Stored papers and local PDFs.
- Human-curated selections.

Output:
- Versioned workspace folder containing reports, paper cards, matrices, gap
  cards, candidate ideas, and reproduction plans.

Core modules:
- Stable CLI workflow over the existing modules.
- SQLite-backed project workspace metadata.
- CLI reference: `docs/CLI_REFERENCE.md`

Test focus:
- End-to-end mock workflow.
- Backward compatibility for v0.1-v0.9 outputs.
- Clear failure reports.
- No real external API calls in tests.
