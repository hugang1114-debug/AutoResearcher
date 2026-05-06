# AutoResearcher

AutoResearcher is a Python research-workflow tool for searching papers,
organizing reading notes, and preparing reliable inputs for literature review
and later idea mining.

The v1.0 goal is **Integrated Literature Workflow**: keep the current workflow
stable from paper search and paper cards through comparison, review outline,
gap extraction, candidate ideas, and reproduction planning.

This project is not intended as a presentation demo. It is meant to support a
repeatable research workflow: collect papers, read them systematically, prepare
review material, and screen ideas that can later become independent experiments.

## Features

- Python src-layout package.
- CLI entry point: `autoresearcher`.
- arXiv search client.
- Semantic Scholar search client.
- `PaperMetadata` data model.
- SQLite persistence.
- Deduplication by source id, DOI/arXiv id, URL, and normalized title.
- Simple topic relevance ranking.
- Markdown report export.
- Evidence-based paper analysis with Pydantic validation.
- Markdown paper card generation for close reading and literature review.
- JSON and Markdown multi-paper comparison matrices.
- Local PDF text extraction with coarse section splitting.
- Batch paper-card generation with per-paper failure reporting.
- Literature review outline generation from comparison matrices.
- Local workspaces for repeatable literature workflows.
- Evidence-backed research gap candidate extraction.
- Candidate research idea cards generated from gap evidence.
- Reproduction plans for selected papers or candidate ideas.
- Evidence-constrained research idea generation from multiple paper cards.
- Pytest test suite.

The technical roadmap from v0.3 to v1.0 is documented in
[docs/ROADMAP.md](docs/ROADMAP.md). The full command reference is in
[docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md).

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pip install -r requirements-dev.txt
```

## Usage

Run a topic search:

```powershell
autoresearcher "retrieval augmented generation evaluation" --limit 5
```

Equivalent module invocation:

```powershell
python -m autoresearcher.cli "retrieval augmented generation evaluation" --limit 5
```

Package invocation:

```powershell
python -m autoresearcher "retrieval augmented generation evaluation" --limit 5
```

Useful options:

```powershell
autoresearcher "large language model agents" `
  --limit 10 `
  --db data/autoresearcher.sqlite `
  --report reports/llm-agents.md
```

The command prints a short summary and writes:

- SQLite database: `data/autoresearcher.sqlite`
- Markdown report: `reports/research_report.md`

## Recommended v1.0 Workflow

For a local literature workflow, use a workspace and move through the artifacts
one step at a time:

```powershell
python -m autoresearcher workspace-init --name rag_review

python -m autoresearcher workspace-search `
  --name rag_review `
  "Adaptive / Corrective RAG + Evaluation" `
  --limit 10

python -m autoresearcher workspace-batch-analyze `
  --name rag_review `
  --top 5 `
  --mock

python -m autoresearcher workspace-compare `
  --name rag_review `
  --name-output rag_matrix

python -m autoresearcher workspace-review-outline `
  --name rag_review `
  --title "Adaptive and Corrective RAG Review" `
  --name-output rag_outline

python -m autoresearcher workspace-extract-gaps `
  --name rag_review `
  --name-output rag_gaps

python -m autoresearcher workspace-generate-ideas `
  --name rag_review `
  --constraint "single GPU" `
  --name-output candidate_ideas

python -m autoresearcher workspace-plan-reproduction `
  --name rag_review `
  --hardware "single GPU" `
  --name-output reproduction_plan
```

Check the workspace:

```powershell
python -m autoresearcher workspace-status --name rag_review
```

This flow is intentionally staged. If a step produces weak or mostly
`not specified` artifacts, fix the upstream paper cards before continuing.

### Semantic Scholar API Key

Semantic Scholar supports authenticated requests with the `x-api-key` header.
AutoResearcher reads the key from an environment variable:

```powershell
$env:SEMANTIC_SCHOLAR_API_KEY = "your-semantic-scholar-api-key"
```

Do not commit API keys to GitHub. The Semantic Scholar client enforces a
1-request-per-second delay and retries `HTTP 429` responses with `Retry-After`
or exponential backoff.

## Evidence-based Paper Analyzer v0.2

The v0.2 analyzer lives under `autoresearcher.analyzers`. It analyzes one paper
at a time from metadata, abstract, and extracted PDF text. It asks an LLM for
structured JSON, validates that JSON with Pydantic, and renders an evidence-based
Markdown paper card.

The key schema objects are:

- `PaperAnalysisResult`
- `EvidenceSpan`
- `PaperCard`
- `AnalysisConfidence`

Each non-`not specified` claim must include evidence:

```json
{
  "claim": "The paper evaluates retrieval failures in RAG.",
  "evidence": [
    {
      "source_section": "abstract",
      "text": "This paper evaluates retrieval failures in RAG.",
      "reason": "The sentence states the evaluation target."
    }
  ]
}
```

If the supplied abstract or PDF text does not contain enough evidence, the
analyzer must use exactly `not specified`. Unsupported claims without evidence
are downgraded to `not specified`, and confidence is reduced.

### CLI Examples

Analyze from title and abstract with deterministic mock mode:

```powershell
python -m autoresearcher analyze `
  --title "A paper title" `
  --abstract "This paper evaluates retrieval failures in RAG." `
  --mock `
  --output outputs/cards/paper_card.md
```

Analyze a paper already stored in SQLite:

```powershell
python -m autoresearcher analyze `
  --paper-id "2401.00001v1" `
  --db data/autoresearcher.sqlite `
  --mock `
  --output outputs/cards/paper_card.md
```

Export a paper card:

```powershell
python -m autoresearcher export-card `
  --paper-id "2401.00001v1" `
  --db data/autoresearcher.sqlite `
  --output outputs/cards/paper_card.md
```

If `OPENAI_API_KEY` and `AUTORESEARCHER_LLM_MODEL` are not set, the analyzer can
still run in mock mode. Pytest always uses mock clients and never calls external
APIs.

### Python Example

```python
from autoresearcher.analyzers.llm_client import build_default_llm_client
from autoresearcher.analyzers.markdown_exporter import build_paper_card_markdown
from autoresearcher.analyzers.paper_analyzer import PaperAnalyzer

client = build_default_llm_client(mock=True)
analyzer = PaperAnalyzer(client)

card = analyzer.analyze(
    title="Paper title",
    abstract="Paper abstract",
    pdf_text="Extracted PDF text",
    metadata={"source": "manual"},
)

print(build_paper_card_markdown(card))
```

The older v0.1-compatible module `autoresearcher.paper_analyzer` is still
available, but new code should use `autoresearcher.analyzers`.

For a real OpenAI-compatible endpoint, set:

```powershell
$env:OPENAI_API_KEY = "..."
$env:AUTORESEARCHER_LLM_MODEL = "your-model-name"
# Optional for compatible providers:
$env:OPENAI_BASE_URL = "https://api.openai.com/v1"
```

### DeepSeek V4-Pro

AutoResearcher also has a DeepSeek-specific client. The easiest setup is to copy
`.env.example` to `.env` and fill in your real key:

```powershell
Copy-Item .env.example .env
notepad .env
```

Put your API key here:

```text
DEEPSEEK_API_KEY=your-deepseek-api-key
```

The default DeepSeek settings are:

```text
AUTORESEARCHER_LLM_PROVIDER=deepseek
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_THINKING=enabled
DEEPSEEK_REASONING_EFFORT=high
```

`.env` is ignored by Git. Do not commit real API keys.

You can also set the same values directly in PowerShell:

```powershell
$env:AUTORESEARCHER_LLM_PROVIDER = "deepseek"
$env:DEEPSEEK_API_KEY = "your-deepseek-api-key"
$env:DEEPSEEK_MODEL = "deepseek-v4-pro"
$env:DEEPSEEK_BASE_URL = "https://api.deepseek.com"
```

Then run analysis without `--mock`:

```powershell
python -m autoresearcher analyze `
  --title "Paper title" `
  --abstract "Paper abstract" `
  --pdf-text-file outputs/text/paper.txt `
  --json-output outputs/cards/paper.json `
  --output outputs/cards/paper.md
```

## Legacy Paper Analyzer

The v0.1 `paper_analyzer` module remains for compatibility:

```python
from autoresearcher.paper_analyzer import (
    OpenAICompatibleLLMClient,
    PaperAnalyzer,
    build_paper_card,
)

client = OpenAICompatibleLLMClient.from_env()
analyzer = PaperAnalyzer(client)

analysis = analyzer.analyze(
    title="Paper title",
    abstract="Paper abstract",
    pdf_text="Extracted PDF text",
)
card_markdown = build_paper_card("Paper title", analysis)
print(card_markdown)
```

## Multi-paper Comparison Matrix v0.3

The v0.3 comparison module takes multiple v0.2 `PaperAnalysisResult` or
`PaperCard` objects and builds a comparison matrix for literature review work.
It does not call an LLM and does not generate final research ideas.

Compared dimensions:

- research problem
- motivation
- method
- datasets
- metrics
- baselines
- main results
- limitations
- reproduction notes
- possible extensions

The matrix only summarizes information already present in the paper cards. If a
dimension cannot be compared across at least two papers, the output explicitly
uses `not comparable`.

### CLI Example

First create JSON paper cards:

```powershell
python -m autoresearcher analyze `
  --title "Paper A" `
  --abstract "This paper evaluates retrieval failures in RAG." `
  --mock `
  --json-output outputs/cards/paper_a.json `
  --output outputs/cards/paper_a.md

python -m autoresearcher analyze `
  --title "Paper B" `
  --abstract "This paper studies corrective retrieval for grounded QA." `
  --mock `
  --json-output outputs/cards/paper_b.json `
  --output outputs/cards/paper_b.md
```

Then compare them:

```powershell
python -m autoresearcher compare `
  --input outputs/cards/paper_a.json `
  --input outputs/cards/paper_b.json `
  --json-output outputs/comparisons/rag_matrix.json `
  --markdown-output outputs/comparisons/rag_matrix.md
```

### Python Example

```python
from autoresearcher.comparison import (
    build_comparison_matrix,
    build_comparison_markdown,
)

matrix = build_comparison_matrix([paper_card_a, paper_card_b])
markdown = build_comparison_markdown(matrix)
print(markdown)
```

## PDF Text Extraction v0.4

The v0.4 PDF module extracts text from local PDFs and tries a simple,
heading-based section split. It is intentionally small: no OCR, no figure/table
understanding, no automatic PDF download.

```powershell
python -m autoresearcher extract-pdf-text `
  --pdf papers/example.pdf `
  --output outputs/text/example.json `
  --text-output outputs/text/example.txt
```

You can limit extraction to specific pages:

```powershell
python -m autoresearcher extract-pdf-text `
  --pdf papers/example.pdf `
  --pages 1-3 `
  --output outputs/text/example_pages.json
```

The JSON output contains:

- `source_path`
- `page_count`
- `text`
- `sections`
- `warnings`

The plain text output can be passed into the v0.2 analyzer:

```powershell
python -m autoresearcher analyze `
  --title "Paper title" `
  --abstract "Paper abstract" `
  --pdf-text-file outputs/text/example.txt `
  --mock `
  --output outputs/cards/example.md
```

## Batch Paper Card Builder v0.5

The v0.5 batch module analyzes multiple papers into v0.2 paper cards in one run.
It is designed for curated batches, not unattended large-scale crawling. One
failed paper does not stop the whole batch.

Manifest example:

```json
{
  "papers": [
    {
      "id": "paper-a",
      "title": "Paper A",
      "abstract": "This paper evaluates retrieval failures in RAG.",
      "pdf_text_file": "outputs/text/paper_a.txt",
      "metadata": {"source": "manual"}
    },
    {
      "id": "paper-b",
      "title": "Paper B",
      "abstract": "This paper studies corrective retrieval for grounded QA."
    }
  ]
}
```

Run the batch in mock mode:

```powershell
python -m autoresearcher batch-analyze `
  --manifest inputs/batch_manifest.json `
  --mock `
  --output-dir outputs/batches/rag_cards
```

Analyze papers already stored in SQLite:

```powershell
python -m autoresearcher batch-analyze `
  --paper-id "2401.00001v1" `
  --paper-id "2502.13957v2" `
  --db data/autoresearcher.sqlite `
  --mock `
  --output-dir outputs/batches/rag_cards
```

Outputs:

- `outputs/batches/rag_cards/json/*.json`
- `outputs/batches/rag_cards/markdown/*.md`
- `outputs/batches/rag_cards/batch_summary.json`

## Literature Review Outline v0.6

The v0.6 review module takes one or more v0.3 comparison matrix JSON files and
builds a review-oriented Markdown outline. It only uses matrix content and does
not generate final research ideas, research gaps, or novelty claims.

```powershell
python -m autoresearcher review-outline `
  --matrix outputs/comparisons/rag_matrix.json `
  --title "Adaptive and Corrective RAG Review Outline" `
  --output outputs/reviews/rag_outline.md `
  --json-output outputs/reviews/rag_outline.json
```

The generated outline contains:

- papers covered
- grounded topic clusters
- problem framing
- method families
- evaluation setup
- findings and limitations
- reproduction and follow-up notes
- limitations of the outline itself

## Workspace Workflow v0.7

The v0.7 workspace layer ties the existing tools together with stable local
paths. It does not add new research reasoning; it reduces file and command
fragmentation.

Create a workspace:

```powershell
python -m autoresearcher workspace-init --name rag_review
```

Search into the workspace:

```powershell
python -m autoresearcher workspace-search `
  --name rag_review `
  "Adaptive / Corrective RAG + Evaluation" `
  --limit 10
```

Analyze top stored papers into cards:

```powershell
python -m autoresearcher workspace-batch-analyze `
  --name rag_review `
  --top 5 `
  --mock
```

Build a comparison matrix:

```powershell
python -m autoresearcher workspace-compare `
  --name rag_review `
  --name-output rag_matrix
```

Build a review outline:

```powershell
python -m autoresearcher workspace-review-outline `
  --name rag_review `
  --title "Adaptive and Corrective RAG Review Outline" `
  --name-output rag_outline
```

Extract candidate research gaps:

```powershell
python -m autoresearcher workspace-extract-gaps `
  --name rag_review `
  --name-output rag_gaps
```

Generate candidate idea cards:

```powershell
python -m autoresearcher workspace-generate-ideas `
  --name rag_review `
  --name-output candidate_ideas
```

Create reproduction plans:

```powershell
python -m autoresearcher workspace-plan-reproduction `
  --name rag_review `
  --hardware "single GPU" `
  --name-output reproduction_plan
```

Check workspace status:

```powershell
python -m autoresearcher workspace-status --name rag_review
```

Workspace layout:

```text
workspaces/<name>/
  workspace.json
  data/autoresearcher.sqlite
  reports/
  papers/
  text/
  cards/json/
  cards/markdown/
  comparisons/
  reviews/
  gaps/
  ideas/
  reproduction/
```

## Research Gap Extraction v0.8

The v0.8 gap extractor takes v0.3 comparison matrix JSON files and optionally
v0.6 review outline JSON files. It produces candidate gap cards grounded in
existing fields only. It does not call an LLM and does not generate proposed
methods or final research ideas.

The extractor currently records gaps such as:

- missing or not-comparable evidence across papers
- dataset or metric mismatches
- incomplete or inconsistent baseline reporting
- stated limitations from paper cards
- possible extension directions already present in paper cards

Run it on existing artifacts:

```powershell
python -m autoresearcher extract-gaps `
  --matrix outputs/comparisons/rag_matrix.json `
  --review-outline outputs/reviews/rag_outline.json `
  --output outputs/gaps/rag_gaps.md `
  --json-output outputs/gaps/rag_gaps.json
```

Workspace version:

```powershell
python -m autoresearcher workspace-extract-gaps `
  --name rag_review `
  --matrix workspaces/rag_review/comparisons/rag_matrix.json `
  --review-outline workspaces/rag_review/reviews/rag_outline.json `
  --name-output rag_gaps
```

Output fields:

- `gap_id`
- `category`
- `title`
- `description`
- `related_papers`
- `source_dimensions`
- `evidence`
- `confidence`

Important limitation: a v0.8 gap card is a review note, not proof of novelty.
Low-confidence cards usually mean the source paper cards are missing details and
need manual checking against the original PDF.

## Candidate Research Idea Cards v0.9

The v0.9 generator takes v0.8 gap JSON files and produces candidate idea cards.
It is deterministic and does not call an LLM. It skips unsupported gaps instead
of inventing ideas. Every emitted idea must have:

- at least two related papers
- source gap ids
- evidence traced back to gap cards
- research gap
- proposed method
- experiment plan sketch
- risk
- difficulty

Run it from gap outputs:

```powershell
python -m autoresearcher generate-ideas `
  --gaps outputs/gaps/rag_gaps.json `
  --output outputs/ideas/candidate_ideas.md `
  --json-output outputs/ideas/candidate_ideas.json `
  --constraint "single GPU"
```

Workspace version:

```powershell
python -m autoresearcher workspace-generate-ideas `
  --name rag_review `
  --gaps workspaces/rag_review/gaps/rag_gaps.json `
  --name-output candidate_ideas `
  --constraint "single GPU"
```

If the gap cards contain only missing or not-comparable information, the command
raises an error instead of generating weak ideas. The output is meant for human
screening before a separate experimental project, not as a final claim of
novelty or feasibility.

## Reproduction Planning v0.10

The v0.10 planner creates operational reproduction plans from either:

- v0.2 paper card JSON
- v0.9 candidate idea JSON

It does not execute commands. The commands are editable templates because the
paper card or idea card usually does not contain exact repository URLs, dataset
download commands, seeds, or hyperparameters.

Plan from a candidate idea file:

```powershell
python -m autoresearcher plan-reproduction `
  --idea outputs/ideas/candidate_ideas.json `
  --hardware "single GPU" `
  --output outputs/reproduction/idea_plan.md `
  --json-output outputs/reproduction/idea_plan.json
```

Plan from a paper card:

```powershell
python -m autoresearcher plan-reproduction `
  --paper-card outputs/cards/paper_a.json `
  --output outputs/reproduction/paper_a_plan.md `
  --json-output outputs/reproduction/paper_a_plan.json
```

Workspace version:

```powershell
python -m autoresearcher workspace-plan-reproduction `
  --name rag_review `
  --hardware "single GPU" `
  --name-output reproduction_plan
```

Each plan includes:

- target paper or candidate idea
- objective
- hardware assumptions
- dataset requirements
- command templates
- risks
- success checks
- missing information
- evidence back to the source card

If a field is not supported by the source card, the planner keeps it as
`not specified` or lists it under missing information. It does not infer hidden
hardware, private datasets, exact hyperparameters, or expected results.

## Idea Generator

The `idea_generator` module takes multiple Markdown paper cards, compares their
`problem`, `method`, `datasets`, `metrics`, and `limitations`, then generates
3-5 evidence-backed research idea cards. It is deterministic and does not call
an LLM. If the input cards do not contain enough evidence for at least three
ideas, it raises `IdeaGenerationError` instead of inventing unsupported ideas.

Each idea contains:

- `related_papers`
- `research_gap`
- `proposed_method`
- `experiment_plan`
- `risk`
- `difficulty`

```python
from autoresearcher.idea_generator import (
    build_idea_markdown_report,
    export_idea_markdown_report,
    generate_research_idea_cards,
)

paper_cards = [
    "... markdown from build_paper_card(...) ...",
    "... another paper card ...",
    "... another paper card ...",
]

ideas = generate_research_idea_cards(paper_cards)
report = build_idea_markdown_report(paper_cards)
export_idea_markdown_report(paper_cards, "reports/research_ideas.md")
```

## Development

Run tests:

```powershell
pytest
```

## Notes

Semantic Scholar may still rate-limit requests. If one source fails, the CLI
continues with papers from the other source and still writes the available
results.

Current limitations:

- The analyzer does not guarantee fully correct analysis.
- Human review is required before using paper cards in a literature review.
- v0.2 does not perform automatic paper reproduction.
- v0.2 does not directly generate final research ideas from one analyzed paper.
- v0.3 comparison matrices do not generate final research ideas.
- v0.3 only compares structured paper-card fields; weak cards produce weak matrices.
- v0.4 PDF extraction does not support OCR, scanned PDFs, figure/table parsing,
  or high-fidelity layout reconstruction.
- v0.5 batch analysis is for curated small batches; it does not schedule jobs,
  parallelize LLM calls, or guarantee card correctness without human review.
- v0.6 review outlines only reorganize comparison-matrix content; they do not
  extract research gaps or produce final research ideas.
- v0.7 workspaces organize files and commands; they do not improve analysis
  quality by themselves.
- v0.8 gap extraction only uses existing matrices and outlines; it does not
  prove novelty, validate feasibility, or generate final research ideas.
- v0.9 candidate ideas are only screening artifacts; they still require manual
  validation, full-paper reading, and separate experiment design.
- v0.10 reproduction plans are editable checklists; commands are templates and
  are not guaranteed to run until the original paper repositories and datasets
  are checked manually.
