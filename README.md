# AutoResearcher

AutoResearcher v0.1 is a small Python CLI that searches arXiv and Semantic
Scholar for a research topic, normalizes paper metadata, deduplicates results,
ranks them with a simple relevance score, stores them in SQLite, and exports a
Markdown report with early research idea cards.

The v0.1 scope is intentionally small. It does not reproduce papers yet.

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
- LLM-backed paper analysis with Pydantic validation.
- Markdown paper card generation.
- Evidence-constrained research idea generation from multiple paper cards.
- Pytest test suite.

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

### Semantic Scholar API Key

Semantic Scholar supports authenticated requests with the `x-api-key` header.
AutoResearcher reads the key from an environment variable:

```powershell
$env:SEMANTIC_SCHOLAR_API_KEY = "your-semantic-scholar-api-key"
```

Do not commit API keys to GitHub. The Semantic Scholar client enforces a
1-request-per-second delay and retries `HTTP 429` responses with `Retry-After`
or exponential backoff.

## Paper Analyzer

The `paper_analyzer` module analyzes one paper at a time from a title, abstract,
and extracted PDF text. It asks an LLM for structured JSON, validates that JSON
with Pydantic, and can render the result as a Markdown paper card.

The analyzer prompt tells the LLM to use exactly `not specified` whenever the
provided material does not contain enough evidence. The Pydantic model also
normalizes empty, null, and common unknown values to `not specified`.

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

For a real OpenAI-compatible endpoint, set:

```powershell
$env:OPENAI_API_KEY = "..."
$env:AUTORESEARCHER_LLM_MODEL = "your-model-name"
# Optional for compatible providers:
$env:OPENAI_BASE_URL = "https://api.openai.com/v1"
```

Tests use a mock LLM client, so no API key is needed to run the test suite.

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
