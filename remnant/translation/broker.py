"""
Translation Broker — express a concept from Field A in Field B's vocabulary.

This is the highest-value output REMNANT produces: not just surfacing forgotten
knowledge, but making it legible to practitioners who would never encounter it
in its original form.
"""
from __future__ import annotations

import json

from openai import OpenAI

from remnant.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
from remnant.graph.knowledge_graph import KnowledgeGraph
from remnant.models import TranslationRequest, TranslationResult

_client: OpenAI | None = None


def _llm() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY or "sk-placeholder")
    return _client


_TRANSLATE_PROMPT = """You are an expert cross-disciplinary knowledge translator.

A concept from {from_field} needs to be explained to a {to_field} practitioner
who has never encountered it.

CONCEPT:
Label: {label}
Description: {description}
Original field: {from_field}

Your task:
1. Write a 3–5 paragraph explanation of this concept for a {to_field} practitioner.
   Use their vocabulary, their familiar analogies, their typical problems.
   Do NOT assume they know {from_field} terminology.
2. List 3–5 key analogies that bridge {from_field} to {to_field}.
3. Suggest 2–3 specific papers or resources in {to_field}-adjacent literature
   that connect to this concept (can be approximate if exact titles unknown).

Return JSON only, no markdown fences:
{{
  "translation": "<full explanation for the {to_field} practitioner>",
  "key_analogies": ["<analogy 1>", "<analogy 2>", ...],
  "suggested_papers": ["<paper/resource 1>", ...]
}}
"""


def translate(request: TranslationRequest,
              graph: KnowledgeGraph) -> TranslationResult:
    """Produce a cross-domain translation for a concept."""
    concept = graph.get_concept(request.concept_id)
    if concept is None:
        raise ValueError(f"Concept {request.concept_id!r} not found in graph.")

    prompt = _TRANSLATE_PROMPT.format(
        from_field=request.from_field or (concept.domains[0] if concept.domains else "science"),
        to_field=request.to_field,
        label=concept.label,
        description=concept.description[:800],
    )

    resp = _llm().chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1200,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"translation": raw, "key_analogies": [], "suggested_papers": []}

    return TranslationResult(
        concept=concept,
        from_field=request.from_field or (concept.domains[0] if concept.domains else "science"),
        to_field=request.to_field,
        translation=data.get("translation", ""),
        key_analogies=data.get("key_analogies", []),
        suggested_papers=data.get("suggested_papers", []),
    )
