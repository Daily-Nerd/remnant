# REMNANT Architecture v2

**Date:** 2026-06-08
**Status:** Revised after 6-critic review
**Author:** T7 Architect (synthesis run)

This document supersedes ARCHITECTURE.md. It is built entirely from critic findings.
Nothing here is defensive. Every change references a specific finding.

---

## What the Critics Proved

Before describing the new architecture, here is the honest summary of what the critics found:

- The decay mechanism is built on data that is never collected. citation_count is always 0 in
  both adapters. Every decay score, importance weight, and collision alert produced by the
  current system is noise. (corpus-ingestion F1, sev 10)
- The translation broker explicitly permits hallucinated citations in its own prompt.
  (translation-broker F2, sev 10)
- The collision detector cannot distinguish "approaching a concept" from "citing a concept."
  Both fire the same alert. (collision-detector F1+F4, sev 9)
- The concept graph is non-idempotent. Re-running ingestion on the same papers produces a
  different graph with different node IDs. (concept-extraction F4+F7, sev 9)
- The model has no ground truth dataset and cannot be validated. (decay-model F7, sev 9)
- The flagship bacteriophage example in the README is outside the system's corpus by design.
  (corpus-ingestion F3, sev 9)

These are not implementation polish items. They are load-bearing failures. The architecture
below is designed to fix the foundations before adding capability.

---

## Component Map: v1 vs v2

### REMOVED

| Component | Reason |
|---|---|
| SHA1(label.lower()) as concept ID | Non-deterministic across runs; collisions at ~4K concepts (concept-extraction F4) |
| n_clusters = max(2, min(len(docs)//5, 20)) | No theoretical basis; wrong for any real domain (concept-extraction F2) |
| citation_count hardcoded 0 | Silently breaks the entire decay mechanism (corpus-ingestion F1) |
| "can be approximate" in translation prompt | Explicit hallucination permission (translation-broker F2) |
| Multiplicative composite score in collision detector | Collapses to indistinguishable values; dynamic range destroyed (collision-detector F2) |
| importance_weight = len(docs) / 50.0 | Measures batch frequency, not importance; inverted for foundational knowledge (decay-model F5, concept-extraction F5) |
| total_known_domains parameter | Epistemically unknowable denominator (decay-model F3) |
| O(N) full-graph embedding scan on each detect() call | Unusable at scale (collision-detector F9) |

### ADDED

| Component | Purpose | Fixes |
|---|---|---|
| ingestion/semantic_scholar.py | Real citation counts and velocity | corpus-ingestion F1 |
| ingestion/crossref.py | 130M+ DOIs across all disciplines | corpus-ingestion F4 |
| ingestion/openalex.py | 250M+ multilingual works | corpus-ingestion F3, F4 |
| ingestion/scheduler.py | Nightly temporal ingestion via arXiv RSS + PubMed reldate | corpus-ingestion F7 |
| extraction/cluster.py | HDBSCAN-based clustering with natural cluster count | concept-extraction F2 |
| extraction/dedup.py | Embedding-space deduplication; merge instead of insert | concept-extraction F4 |
| collision/intent.py | LLM intent classifier (exploring/implementing/citing/evaluating) | collision-detector F1, F4 |
| collision/index.py | FAISS ANN index built at startup, updated incrementally | collision-detector F9 |
| collision/feedback.py | Log every CollisionReport to DB; thumbs-up/down endpoint | collision-detector F5 |
| translation/retrieval.py | RAG step: fetch related cross-domain papers before LLM call | translation-broker F1, A |
| translation/verifier.py | DOI/arXiv lookup for every suggested citation | translation-broker F2 |
| decay/calibration.py | Ground truth dataset builder + AUROC validation harness | decay-model F7 |

### MODIFIED INTERFACES

**IngestedDocument**
```python
class IngestedDocument(BaseModel):
    # existing fields unchanged
    citation_count: int = 0          # NOW populated via Semantic Scholar enrichment
    semantic_scholar_id: str = ""    # key for citation lookups
    is_retracted: bool = False       # checked at ingest time
    body: str = ""                   # full text where available (ar5iv/PMC); abstract fallback
    language: str = "en"             # ISO 639-1; non-English documents tagged
```

**ConceptNode**
```python
class ConceptNode(BaseModel):
    # ID is now content-addressed on embedding vector, not SHA1 of label string
    # computed as "concept:" + uuid5(NAMESPACE_URL, embedding_bytes_hex[:64])
    # dedup pass: if cosine_sim(new_embedding, existing) > 0.92, merge instead of insert
    absorption_score: float = 0.5    # renamed from decay_score (collision-detector F10)
    # 0-1, higher = concept so absorbed into baseline knowledge it stops being cited explicitly
    citation_count_total: int = 0    # accumulated across all ingestion runs, not per-batch
    first_seen: str = ""             # earliest published_at across ALL batches, not current batch
```

**DecayReport**
```python
class DecayReport(BaseModel):
    # existing fields unchanged
    citations_mid: int = 0           # 3-6 year window; required for trajectory computation
    recovering: bool = False         # True if recent_citations > mid_citations * 1.1
    absorption_score: float = 0.0    # renamed from decay_score
    weights_used: dict = {}          # {citation: 0.45, domain: 0.30, synthesis: 0.25} - logged for debuggability
```

**CollisionReport**
```python
class CollisionReport(BaseModel):
    # existing fields unchanged
    report_id: str = ""              # UUID; stored in feedback DB
    intent: str = ""                 # from intent classifier: exploring/implementing/etc.
    intent_confidence: float = 0.0
    delivery_channel: str = ""       # webhook/inline/email — must be configured before alerts fire
```

**TranslationRequest / TranslationResult**
```python
class TranslationRequest(BaseModel):
    # existing fields unchanged
    practitioner_context: str = ""   # domain-specific vocabulary, canonical refs injected by caller
    feedback: str = ""               # expert corrections from prior runs; injected into prompt

class TranslationResult(BaseModel):
    translation: str = ""
    key_analogies: list[str] = []
    suggested_papers: list[VerifiedCitation] = []   # not list[str]
    confidence_score: float = 0.0    # from second LLM critique pass
    parse_failed: bool = False       # surfaced, not silently swallowed

class VerifiedCitation(BaseModel):
    title: str
    authors: list[str] = []
    year: int | None = None
    doi: str = ""
    arxiv_id: str = ""
    verified: bool = False           # True if DOI/arXiv lookup succeeded
```

---

## Data Flow: v2

```
INGESTION
  adapters (arXiv, PubMed, CrossRef, OpenAlex)
    → Semantic Scholar enrichment (citation_count, citation_velocity)
    → retraction check (PubMed PublicationType, arXiv withdrawal comment)
    → full-text fetch where available (ar5iv HTML, PMC XML)
    → IngestedDocument (with citation_count, is_retracted, body, language)
    → nightly scheduler (arXiv RSS per category, PubMed reldate)

CONCEPT EXTRACTION
  HDBSCAN clustering (min_cluster_size=3, natural cluster count)
    → multi-concept extraction per cluster (1 to N concepts, not forced 1)
    → sample by centroid proximity, not first-6 insertion order
    → LLM at temperature=0.0 with structured output (JSON schema enforced)
    → strip markdown fences; validate required keys; count failures as metric
    → embedding computed from cluster centroid mean, not LLM-generated text
    → dedup pass: cosine_sim against existing nodes > 0.92 → merge, not insert
    → stable concept ID: uuid5 of embedding bytes
    → importance_weight: log1p(total_citations) / log1p(1000)
    → first_seen: min published_at across ALL batches for this concept

DECAY SCORING
  inputs: citations_recent (0-3yr), citations_mid (3-6yr), peak_citations
    → citation_decay_v2: 3-window trajectory (not snapshot linear)
    → revival signal: recovering = (recent > mid * 1.1) → suppress alert
    → domain penetration: log-scale relative (removes fake total_known_domains)
    → synthesis decay: domain-specific horizon (cs=7yr, biology=15yr, etc.)
    → importance_weight: citation-weighted, not doc-count
    → weights: configurable via env vars (WEIGHT_CITATION, WEIGHT_DOMAIN, WEIGHT_SYNTHESIS)
    → validation: AUROC against ground truth labels from OpenAlex 1990-2005 cohort

COLLISION DETECTION
  query
    → LLM intent classifier → if NOT {exploring | implementing}: skip, return no-op
    → keyphrase extraction
    → FAISS ANN search (top_k=20) against concept embeddings (built at startup)
    → LLM re-ranking: "Is this query approaching concept X or citing/referencing it?"
    → additive score: (w1 * intent_confidence) + (w2 * similarity) + (w3 * absorption_score)
    → alert if score > calibrated_threshold (derived from labeled eval set, not magic number)
    → log CollisionReport to feedback DB with UUID
    → deliver via configured channel (must be set; alerts do not fire without a delivery target)

TRANSLATION
  TranslationRequest (concept_id, from_field, to_field, practitioner_context, feedback)
    → graph context retrieval: related concepts in to_field, cross-domain edges
    → RAG: fetch 5-10 actual cross-domain papers from corpus
    → LLM draft pass (with retrieved context, practitioner_context, feedback)
    → self-critique pass: "identify 3 ways this analogy might fail"
    → revision pass
    → citation verification: DOI/arXiv lookup for each suggested_paper
    → confidence_score via second LLM critique: "rate the structural validity 0-1"
    → TranslationResult (with verified citations, confidence_score, parse_failed flag)
```

---

## Infrastructure

| Layer | v1 | v2 | Migration path |
|---|---|---|---|
| Graph storage | NetworkX in-memory + SQLite | Kuzu (embedded, Cypher, fast) | Phase 2; NetworkX fine for <10K nodes |
| Embedding search | O(N) numpy matrix scan | FAISS IVFFlat (CPU) | Phase 1; required for collision at scale |
| Feedback storage | None | SQLite feedback table | Phase 1; simple, no new dependency |
| Citation data | None (always 0) | Semantic Scholar API | Phase 0; free tier sufficient for MVP |
| LLM client | Global singleton, no retry | Initialized at load time; tenacity retry on 429/503 | Phase 0; one-hour fix |

---

## What We Kept and Why

Not everything the critics found was a fatal flaw. These design decisions are correct and we are keeping them:

**The three-signal decay model shape (citation + domain + synthesis)**
The critics said the weights are arbitrary and the individual signals are miscalibrated — both true.
But the shape of the model (three orthogonal signals of knowledge health, combined into a composite
score) is the right abstraction. The fix is to calibrate the signals and make the weights
empirically derived, not to discard the model. (decay-model F1 fixes the weights; F2 fixes the
citation signal; the shape stays)

**The ConceptNode / KnowledgeGraph abstraction**
A graph of concept nodes with edges is the right data structure for cross-domain knowledge.
NetworkX is wrong at scale (corpus-ingestion F12) but the abstraction is correct. We migrate the
storage layer, not the model.

**Collision detection as a proactive alert, not a search**
The critics attacked the implementation (cosine similarity is wrong, threshold is uncalibrated,
no feedback loop) but not the premise. Proactive collision detection — alerting a researcher
that they are approaching a known concept — is the core value proposition and has no commercial
equivalent. The implementation needs an intent layer; the concept survives.

**The translation engine as cross-domain bridge**
The critics found hallucination risk, no quality metric, and weak grounding — all real.
But "translate a concept into another field's vocabulary" is a genuine product feature that
no existing tool offers. The fix is grounding + quality signals, not removal.

**IngestedDocument as the ingestion contract**
The schema is reasonable. citation_count was always 0 (bug, not design). The missing fields
(is_retracted, body, language, semantic_scholar_id) are extensions, not rewrites.

**The three-phase roadmap structure (crawl/walk/run)**
The critics obliterated the specific phase contents, but a phased build from foundations to
features is the right approach. The phases are redrawn in ROADMAP_V2.md.

---

## Explicit Scope Limitations (v2)

These are real constraints acknowledged here for the first time. They do not kill the value
proposition. They define it honestly.

- Corpus covers: English-language formal academic literature published after ~1990 in arXiv
  and PubMed domains (CS, physics, biology, math, quantitative econ). With CrossRef/OpenAlex
  adapters (Phase 1): expands to all disciplines with DOI-registered publications.
- Out of scope in v1: Tacit knowledge, practitioner experience, oral traditions, indigenous
  knowledge, craft knowledge. These were never in the design; they need to be stated as
  explicit exclusions rather than implicitly included by the "civilizational memory" framing.
- Out of scope in v1: Non-English scientific traditions (Soviet phage therapy literature,
  Chinese industrial standards, German engineering norms). The flagship bacteriophage example
  requires multilingual coverage; that is a Phase 2 deliverable, not current state.
- Out of scope in v1: Pre-digital literature, grey literature, classified literature,
  IP-restricted manufacturing process knowledge.

The bacteriophage example belongs on the roadmap as a milestone, not in the README as a
current capability.
