from __future__ import annotations

import json
from typing import Any

from autoresearcher.analyzers.llm_client import NOT_SPECIFIED

DEFAULT_MAX_TEXT_CHARS = 20000


def build_paper_analysis_prompt(
    *,
    title: str,
    abstract: str = "",
    pdf_text: str = "",
    metadata: dict[str, Any] | None = None,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
) -> str:
    """Build the strict evidence-based analysis prompt."""
    metadata_text = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
    truncated_pdf_text = truncate_text(pdf_text, max_text_chars)
    return f"""Analyze this paper for an evidence-based research workflow.

Rules:
- Return one valid JSON object and no extra text.
- Do not infer or complete facts from outside knowledge.
- If the abstract/PDF text does not provide enough evidence, write exactly "{NOT_SPECIFIED}".
- Every non-"{NOT_SPECIFIED}" field must include at least one evidence span.
- Evidence spans must quote or tightly summarize text visible in the supplied abstract/PDF text.
- Do not invent datasets, metrics, baselines, results, limitations, or reproduction details.
- possible_extensions must be grounded in observed limitations or method gaps.
- Lower confidence when evidence is sparse, missing, or only from the abstract.

Required JSON shape:
{{
  "title": "string",
  "problem": {{"claim": "string", "evidence": [{{"source_section": "abstract|introduction|method|experiment|limitation|unknown", "text": "string", "reason": "string"}}]}},
  "motivation": {{"claim": "string", "evidence": []}},
  "method": {{"claim": "string", "evidence": []}},
  "datasets": {{"claim": "string", "evidence": []}},
  "metrics": {{"claim": "string", "evidence": []}},
  "baselines": {{"claim": "string", "evidence": []}},
  "main_results": {{"claim": "string", "evidence": []}},
  "limitations": {{"claim": "string", "evidence": []}},
  "reproduction_notes": {{"claim": "string", "evidence": []}},
  "possible_extensions": {{"claim": "string", "evidence": []}},
  "confidence": {{
    "level": "low|medium|high",
    "score": 0.0,
    "missing_information": ["string"],
    "rationale": "string"
  }}
}}

Metadata:
{metadata_text}

Title:
{title or NOT_SPECIFIED}

Abstract:
{abstract or NOT_SPECIFIED}

PDF text:
{truncated_pdf_text or NOT_SPECIFIED}
"""


def truncate_text(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "\n[truncated]"
