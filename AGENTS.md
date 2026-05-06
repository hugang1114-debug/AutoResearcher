# AGENTS.md

## Project Identity

This repository is AutoResearcher.

AutoResearcher is not intended to be my final research project or thesis topic. It is a long-term research workflow tool for helping me:

1. collect papers;
2. deduplicate and rank papers;
3. perform structured close reading;
4. generate evidence-based paper cards;
5. compare multiple papers;
6. prepare literature review materials;
7. discover candidate research ideas for separate experimental projects.

The tool should help me think more systematically. It must not pretend to fully automate research.

## Current Development Stage

Current version: v0.1

Implemented or expected v0.1 features:

- paper search;
- paper metadata normalization;
- deduplication;
- simple ranking;
- local storage;
- markdown report export.

Next target: v0.2

v0.2 should focus on evidence-based paper analysis, not full literature review generation and not automatic paper reproduction.

## Development Principles

- Keep the code simple, readable, and testable.
- Do not rewrite the whole project unless explicitly requested.
- Prefer incremental changes over large architectural rewrites.
- Preserve existing v0.1 functionality.
- Add tests for every new module.
- Do not introduce heavy dependencies unless clearly justified.
- If a dependency is added, explain why it is necessary.
- Use existing project conventions before inventing new ones.

## Python Conventions

- Use Python 3.10+.
- Prefer src-layout if already used.
- Use Pydantic for structured data models.
- Use pytest for tests.
- Use type hints where useful.
- Keep CLI commands stable and documented.
- Do not call external APIs in tests; use mocks or fixtures.

## Research Integrity Rules

This project must prioritize accuracy over fluency.

When analyzing papers:

- Do not fabricate claims.
- Do not infer datasets, metrics, baselines, or results unless they are present in the provided abstract, PDF text, or metadata.
- If information is missing, write "not specified".
- Every important conclusion should include evidence.
- Evidence should include source section when possible, such as abstract, introduction, method, experiment, limitation, or unknown.
- If evidence is weak or missing, lower the confidence score.
- Possible extensions must be grounded in observed limitations, method weaknesses, evaluation gaps, or missing experimental settings.
- Do not generate impressive-sounding but unsupported research ideas.

## Paper Analysis Output Requirements

A structured paper card should include at least:

- title;
- basic metadata;
- research problem;
- motivation;
- method;
- datasets;
- metrics;
- baselines;
- main results;
- limitations;
- reproduction notes;
- possible extensions;
- evidence table;
- confidence and missing information.

The output should be useful for human close reading and later literature review writing.

## Literature Review Direction

Do not jump directly from single-paper summaries to final research ideas.

The intended workflow is:

1. single-paper evidence-based paper cards;
2. multi-paper comparison matrix;
3. taxonomy or literature review outline;
4. research gaps;
5. candidate idea cards;
6. separate experimental project for validating selected ideas.

## CLI and Documentation Expectations

When adding a feature:

- expose it through CLI if appropriate;
- update README with minimal usage examples;
- add or update tests;
- explain limitations clearly;
- include a small runnable example.

## Testing Commands

Use the repository's existing test command if available.

Common default command:

`pytest`

Before finishing a task, run relevant tests and report the result.

## Review Guidelines

Before finalizing changes, check:

- whether existing v0.1 behavior still works;
- whether new code has tests;
- whether paper analysis avoids hallucination;
- whether missing information is handled as "not specified";
- whether README examples match actual commands;
- whether the implementation is over-engineered.