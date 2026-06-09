# REMNANT — Architecture

## Overview

REMNANT is a pipeline that continuously ingests human knowledge, models its decay,
and surfaces forgotten or cross-domain insights proactively.

```
┌─────────────────────────────────────────────────────────────────┐
│                         REMNANT PIPELINE                        │
│                                                                 │
│  [Sources]──▶[Ingestion]──▶[Extraction]──▶[Knowledge Graph]    │
│                                                  │              │
│                                           ┌──────┴──────┐      │
│                                        [Decay]    [Collision]   │
│                                           │              │      │
│                                           └──────┬──────┘      │
│                                               [Alerts]          │
│                                                  │              │
│                                          [Translation Engine]   │
└─────────────────────────────────────────────────────────────────┘
```

## Layer 1: Ingestion

**Goal:** Pull raw documents from sources and normalize them into a common schema.

Sources (v0.1):
- arXiv (via `arxiv` Python library)
- PubMed (via NCBI E-utilities API)
- Hacker News (via Algolia API)
- GitHub Issues/Discussions (via REST API)

Sources (v0.2+):
- ACM Digital Library
- IEEE Xplore
- USPTO Patents
- Stack Overflow
- Reddit (r/MachineLearning, r/compsci, etc.)

Each document is normalized to `IngestedDocument`:
```python
class IngestedDocument(BaseModel):
    id: str
    source: str
    title: str
    abstract: str
    body: str | None
    authors: list[str]
    published_at: datetime
    url: str
    domain_tags: list[str]
    raw_metadata: dict
```

## Layer 2: Concept Extraction

**Goal:** Extract the *underlying idea* independent of vocabulary.

Two stages:
1. **Embedding fingerprint** — sentence-transformers produces a 768-dim vector per document.
   Similar vectors = similar concepts, regardless of terminology.
2. **LLM concept labeling** — for clusters of similar documents, an LLM produces a
   canonical concept label and one-paragraph description. This is the "concept node."

A single concept node may be expressed across dozens of papers in different fields
using completely different vocabulary. The node captures the abstraction.

## Layer 3: Knowledge Graph

**Storage:** NetworkX in-memory graph + SQLite for persistence.

Nodes:
- `ConceptNode`: id, label, description, domains[], first_seen, last_cited
- `DocumentNode`: id, source, url, published_at

Edges:
- `EXPRESSES`: Document → Concept (with confidence score)
- `RELATED_TO`: Concept → Concept (semantic similarity > 0.75)
- `TRANSLATED_FROM`: Concept → Concept (cross-domain translation event)

## Layer 4: Decay Modeling

**Goal:** Score how "invisible" each concept is becoming relative to its importance.

Decay score = f(citation_velocity, cross_domain_penetration, recency_of_synthesis, importance_weight)

- **Citation velocity:** Rate of new citations/references — decelerating = decaying
- **Cross-domain penetration:** How many distinct fields reference this concept
- **Recency of synthesis:** When was the last review/synthesis paper written?
- **Importance weight:** Proxy from peak citation count + domain influence

Concepts with high importance_weight + high decay_score = PRIORITY ALERTS.

## Layer 5: Collision Detection

**Goal:** Detect when someone is about to re-derive something already solved.

Input: Any text signal (forum post, GitHub issue, Slack message, query).
Output: List of `CollisionCandidate` — concepts the text is approaching.

Method:
1. Embed the input text.
2. Find top-K nearest concept nodes in the graph.
3. Score relevance × decay_score × importance_weight.
4. If score > threshold: fire alert.

Alert includes: the concept, when it was established, key papers, and a
plain-English explanation of why it's relevant.

## Layer 6: Translation Engine

**Goal:** Express a concept from Field A in the vocabulary of Field B.

Input: concept_id, target_field
Output: Translation document — written for practitioners of target_field

Method:
1. Retrieve concept node + all EXPRESSES documents
2. Find documents in target_field that cite RELATED_TO concepts
3. LLM prompt: "Express [concept] for a [target_field] practitioner. 
   Use their vocabulary. Cite analogous problems they already understand."

## Alert Delivery

Current: CLI output via `rich`, JSON webhooks
Planned: Email digest, Slack/Discord integration, RSS feed
