"""
LLM-powered concept extraction and labeling.

Given a cluster of semantically similar documents, produce a canonical
ConceptNode: label, description, domain tags.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from openai import OpenAI

from remnant.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
from remnant.models import ConceptNode, IngestedDocument
from .fingerprint import embed_one

_client: OpenAI | None = None


def _llm() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY or "sk-placeholder")
    return _client


_EXTRACT_PROMPT = """You are an expert knowledge taxonomist.

Given the following document abstracts (from possibly different fields),
identify the single core underlying concept they all express.

Return JSON only, no markdown fences:
{{
  "label": "<short canonical concept name, e.g. 'Eventual Consistency'>",
  "description": "<1–2 paragraph plain-English description of the abstract concept>",
  "domains": ["<field1>", "<field2>", ...]
}}

Documents:
{snippets}
"""


def extract_concept(docs: list[IngestedDocument]) -> ConceptNode:
    """Given a cluster of similar documents, produce a ConceptNode via LLM."""
    snippets = "\n---\n".join(
        f"Title: {d.title}\nAbstract: {d.abstract[:400]}" for d in docs[:6]
    )
    resp = _llm().chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": _EXTRACT_PROMPT.format(snippets=snippets)}],
        temperature=0.2,
        max_tokens=600,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # fallback: use first doc title as label
        data = {"label": docs[0].title[:80], "description": docs[0].abstract[:300], "domains": []}

    # Stable ID from the label
    concept_id = "concept:" + hashlib.sha1(data["label"].lower().encode()).hexdigest()[:12]

    published_dates = [d.published_at for d in docs if d.published_at]
    first_seen = min(published_dates) if published_dates else datetime.now(timezone.utc)
    last_cited = max(published_dates) if published_dates else datetime.now(timezone.utc)

    embedding = embed_one(data["label"] + " " + data["description"])

    return ConceptNode(
        id=concept_id,
        label=data.get("label", "Unknown"),
        description=data.get("description", ""),
        domains=data.get("domains", []),
        embedding=embedding,
        first_seen=first_seen,
        last_cited=last_cited,
        importance_weight=min(1.0, len(docs) / 50.0),
    )
