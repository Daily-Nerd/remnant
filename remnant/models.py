"""Core pydantic data models for REMNANT."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Source types ──────────────────────────────────────────────────────────

class SourceType(str, Enum):
    ARXIV = "arxiv"
    PUBMED = "pubmed"
    HACKERNEWS = "hackernews"
    GITHUB = "github"
    WEB = "web"


# ── Raw ingestion ─────────────────────────────────────────────────────────

class IngestedDocument(BaseModel):
    """Normalized document from any source."""
    id: str
    source: SourceType
    title: str
    abstract: str
    body: str | None = None
    authors: list[str] = Field(default_factory=list)
    published_at: datetime
    url: str
    domain_tags: list[str] = Field(default_factory=list)
    citation_count: int = 0
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


# ── Knowledge graph nodes ─────────────────────────────────────────────────

class ConceptNode(BaseModel):
    """A single abstract concept — may be expressed in many documents/fields."""
    id: str
    label: str                          # e.g. 'Eventual Consistency'
    description: str                    # 1-paragraph canonical summary
    domains: list[str]                  # fields where this concept appears
    embedding: list[float] | None = None
    first_seen: datetime
    last_cited: datetime
    peak_citation_year: int | None = None
    importance_weight: float = 0.5      # 0–1, derived from peak citation count
    decay_score: float = 0.0            # 0–1, higher = more invisible


class DocumentNode(BaseModel):
    """A specific document in the graph."""
    id: str
    source: SourceType
    title: str
    url: str
    published_at: datetime
    concept_ids: list[str] = Field(default_factory=list)


# ── Decay ─────────────────────────────────────────────────────────────────

class DecayReport(BaseModel):
    """Decay analysis output for a single concept."""
    concept: ConceptNode
    citation_velocity: float            # citations/year, recent vs peak
    cross_domain_penetration: float     # 0–1, how many domains absorbed this
    recency_of_synthesis: float         # 0–1, how recent is the last review
    decay_score: float                  # composite 0–1
    alert: bool                         # True if above threshold
    alert_reason: str = ""


# ── Collision detection ───────────────────────────────────────────────────

class CollisionCandidate(BaseModel):
    """A concept the input text is approaching — potential re-derivation alert."""
    concept: ConceptNode
    similarity: float                   # cosine similarity to input embedding
    relevance_score: float              # similarity × decay × importance
    alert: bool
    summary: str                        # plain-English explanation


class CollisionReport(BaseModel):
    query: str
    candidates: list[CollisionCandidate]
    top_alert: CollisionCandidate | None = None


# ── Translation ───────────────────────────────────────────────────────────

class TranslationRequest(BaseModel):
    concept_id: str
    from_field: str
    to_field: str


class TranslationResult(BaseModel):
    concept: ConceptNode
    from_field: str
    to_field: str
    translation: str                    # full document in target-field vocabulary
    key_analogies: list[str]            # 3–5 bridge analogies
    suggested_papers: list[str]         # URLs of bridging literature
