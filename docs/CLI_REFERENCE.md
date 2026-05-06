# AutoResearcher CLI Reference

This reference lists the stable v1.0 command surface. Use `python -m
autoresearcher ...` when running from source, or `autoresearcher ...` after
installing the package in editable mode.

## LLM Provider Setup

For DeepSeek V4-Pro, copy the example environment file and fill in your API key:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set:

```text
AUTORESEARCHER_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-deepseek-api-key
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_THINKING=enabled
DEEPSEEK_REASONING_EFFORT=high
```

Run analysis commands without `--mock` to use the configured model.

## Discovery and Storage

Search papers and write a SQLite database plus Markdown report:

```powershell
python -m autoresearcher "Adaptive / Corrective RAG + Evaluation" `
  --limit 10 `
  --db data/autoresearcher.sqlite `
  --report reports/rag.md
```

## Single-paper Analysis

Analyze one paper from title and abstract:

```powershell
python -m autoresearcher analyze `
  --title "Paper title" `
  --abstract "Paper abstract" `
  --mock `
  --json-output outputs/cards/paper.json `
  --output outputs/cards/paper.md
```

Analyze one paper stored in SQLite:

```powershell
python -m autoresearcher analyze `
  --paper-id "paper-id" `
  --db data/autoresearcher.sqlite `
  --mock `
  --json-output outputs/cards/paper.json `
  --output outputs/cards/paper.md
```

## PDF Text Extraction

```powershell
python -m autoresearcher extract-pdf-text `
  --pdf papers/example.pdf `
  --output outputs/text/example.json `
  --text-output outputs/text/example.txt
```

## Batch Paper Cards

```powershell
python -m autoresearcher batch-analyze `
  --manifest inputs/batch_manifest.json `
  --mock `
  --output-dir outputs/batches/rag_cards
```

## Multi-paper Comparison

```powershell
python -m autoresearcher compare `
  --input outputs/cards/paper_a.json `
  --input outputs/cards/paper_b.json `
  --json-output outputs/comparisons/rag_matrix.json `
  --markdown-output outputs/comparisons/rag_matrix.md
```

## Literature Review Outline

```powershell
python -m autoresearcher review-outline `
  --matrix outputs/comparisons/rag_matrix.json `
  --title "Adaptive and Corrective RAG Review Outline" `
  --output outputs/reviews/rag_outline.md `
  --json-output outputs/reviews/rag_outline.json
```

## Research Gaps

```powershell
python -m autoresearcher extract-gaps `
  --matrix outputs/comparisons/rag_matrix.json `
  --review-outline outputs/reviews/rag_outline.json `
  --output outputs/gaps/rag_gaps.md `
  --json-output outputs/gaps/rag_gaps.json
```

## Candidate Ideas

```powershell
python -m autoresearcher generate-ideas `
  --gaps outputs/gaps/rag_gaps.json `
  --constraint "single GPU" `
  --output outputs/ideas/candidate_ideas.md `
  --json-output outputs/ideas/candidate_ideas.json
```

## Reproduction Plans

From candidate ideas:

```powershell
python -m autoresearcher plan-reproduction `
  --idea outputs/ideas/candidate_ideas.json `
  --hardware "single GPU" `
  --output outputs/reproduction/idea_plan.md `
  --json-output outputs/reproduction/idea_plan.json
```

From paper cards:

```powershell
python -m autoresearcher plan-reproduction `
  --paper-card outputs/cards/paper_a.json `
  --hardware "single GPU" `
  --output outputs/reproduction/paper_plan.md `
  --json-output outputs/reproduction/paper_plan.json
```

## Workspace Workflow

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

Build paper cards from stored papers:

```powershell
python -m autoresearcher workspace-batch-analyze `
  --name rag_review `
  --top 5 `
  --mock
```

Create downstream artifacts:

```powershell
python -m autoresearcher workspace-compare --name rag_review --name-output rag_matrix
python -m autoresearcher workspace-review-outline --name rag_review --title "RAG Review" --name-output rag_outline
python -m autoresearcher workspace-extract-gaps --name rag_review --name-output rag_gaps
python -m autoresearcher workspace-generate-ideas --name rag_review --constraint "single GPU" --name-output candidate_ideas
python -m autoresearcher workspace-plan-reproduction --name rag_review --hardware "single GPU" --name-output reproduction_plan
```

Check artifact counts:

```powershell
python -m autoresearcher workspace-status --name rag_review
```

## Integrity Rules

- Tests and mock mode do not call external APIs.
- Missing paper information remains `not specified`.
- Gap extraction does not invent gaps from missing fields.
- Candidate ideas require evidence and at least two related papers.
- Reproduction commands are templates and are not executed automatically.
