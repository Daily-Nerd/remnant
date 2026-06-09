# REMNANT — Top 5 Priorities

**Date:** 2026-06-08
**Source:** Synthesized from 6-critic review
**Selection criterion:** Highest-leverage changes — where failure is immediate, silent, and foundational.

These are ordered by blast radius, not difficulty. Fix them in order.

---

## Priority 1 — Integrate Semantic Scholar for Citation Counts

**Problem** (corpus-ingestion F1, severity 10/10)

citation_count is always 0 in both arXiv and PubMed adapters. Neither API returns citation data.
The field defaults to 0 and is never written. Downstream consequences:

- ConceptNode.importance_weight = len(docs) / 50.0 (cluster size, not importance)
- decay/scorer.py citation_velocity is always 0
- All decay scores are noise built on zero data
- The system cannot distinguish a foundational concept from a throwaway paper

Every user-facing output — decay alerts, collision scores, concept importance rankings — is
computed on a field that has never contained real data. This is not a missing feature. It is
a silent data integrity failure that invalidates the core value proposition.

**Proposed fix**

Add a Semantic Scholar enrichment step in the ingestion pipeline:

```python
# ingestion/semantic_scholar.py
import httpx

SS_BASE = "https://api.semanticscholar.org/graph/v1"

def enrich_citation_count(doc: IngestedDocument) -> IngestedDocument:
    """
    Fetches citation count from Semantic Scholar by arXiv ID or title search.
    Free tier: 100 req/5 min. Add tenacity retry with 60s backoff on 429.
    """
    arxiv_id = doc.raw_metadata.get("arxiv_id", "")
    if arxiv_id:
        url = f"{SS_BASE}/paper/arXiv:{arxiv_id}?fields=citationCount,externalIds"
    else:
        url = f"{SS_BASE}/paper/search?query={httpx.QueryParams(query=doc.title)}&fields=citationCount"
    
    resp = httpx.get(url, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        paper = data if arxiv_id else (data.get("data") or [{}])[0]
        doc = doc.model_copy(update={
            "citation_count": paper.get("citationCount", 0),
            "semantic_scholar_id": paper.get("paperId", ""),
        })
    return doc
```

Call enrich_citation_count() after each adapter fetch, before storing the document.
Add semantic_scholar_id: str = "" to IngestedDocument.
Add a tenacity @retry decorator: wait_exponential(min=60, max=300) on HTTPStatusError 429.

For the decay model, also collect citationsPerYear from Semantic Scholar to get the
3-window trajectory needed by citation_decay_v2 (citations_recent, citations_mid, peak_citations).

**Effort estimate:** 1 day

**Impact if not fixed:** Every decay score, importance weight, and collision relevance score
produced by REMNANT is computed on data that is always 0. The system cannot generate meaningful
alerts. The civilizational memory claim is entirely unsupported by actual data. Any demo or
user test will produce nonsense rankings.

---

## Priority 2 — Remove Hallucination Permission from Translation Prompt

**Problem** (translation-broker F2, severity 10/10)

Line 44 of _TRANSLATE_PROMPT:

    "Suggest 2–3 specific papers or resources ... (can be approximate if exact titles unknown)."

"Can be approximate if exact titles unknown" is an instruction to fabricate citations.
The LLM will produce plausible author names, journal names, and years that do not correspond
to real papers. The suggested_papers field in TranslationResult is a list of strings with no
DOI, no URL, no arXiv ID, and no verified flag.

A researcher who receives a REMNANT translation and searches for the suggested papers will
either: (a) fail to find them and lose trust in REMNANT entirely, or (b) cite the hallucinated
papers themselves without verifying. Option (b) is an active harm.

**Proposed fix**

Step 1 (hours): Remove the permission. Change the prompt line to:
"Only suggest papers you are highly confident exist. If uncertain, omit. Do not approximate."

Step 2 (1 day): Add citation verification. After LLM response, for each suggested paper,
attempt a Semantic Scholar or arXiv title search:

```python
# translation/verifier.py
def verify_citation(raw_title: str) -> VerifiedCitation:
    """
    Attempts to find a real paper matching raw_title.
    Returns VerifiedCitation with verified=True if found, False if not.
    """
    results = semantic_scholar_search(raw_title)
    if results and title_similarity(results[0]["title"], raw_title) > 0.85:
        return VerifiedCitation(
            title=results[0]["title"],
            doi=results[0].get("externalIds", {}).get("DOI", ""),
            arxiv_id=results[0].get("externalIds", {}).get("ArXiv", ""),
            verified=True,
        )
    return VerifiedCitation(title=raw_title, verified=False)
```

Step 3 (longer): Replace paper suggestions with search queries. The LLM suggests directions
("look for papers on criticality in organizational behavior from the 1990s"); the system
executes the search and injects the real titles back into the result. The LLM never invents
sources — it only proposes search strategies.

**Effort estimate:** Step 1: 1 hour. Steps 1+2: 1 day. Full Step 3: 3 days.

**Impact if not fixed:** REMNANT actively fabricates scientific citations on every translation
call. The first time a serious user checks one of the suggested papers and finds it doesn't
exist, trust is destroyed and the system becomes known as a hallucination engine. This is
worse than no translation feature at all.

---

## Priority 3 — Stable Concept Identity: Embedding-Space Deduplication

**Problem** (concept-extraction F4, severity 9/10)

Concept IDs are computed as SHA1(label.lower())[:12]. The label is an LLM output at
temperature=0.2. The same cluster of papers will produce different labels across runs:
"Eventual Consistency" vs "Eventual Data Consistency" vs "Consistency Models in Distributed
Systems" — three different SHA1 hashes, three separate nodes in the graph.

After 5 ingestion runs on overlapping literature, the graph has 5-15 near-duplicate nodes
for the same concept. The 12-char SHA1 prefix also has birthday-paradox collisions at ~4,100
concepts, silently mapping unrelated concepts to the same node.

There is no deduplication pass anywhere in the codebase. The graph is non-idempotent:
re-running ingestion on the same papers produces a different graph. A knowledge graph whose
nodes change identity on re-ingestion is not a knowledge graph.

**Proposed fix**

1. Set temperature=0.0 for concept labeling. No creative value in variation here.

2. After extracting a new concept label+description, compute its embedding and compare against
   all existing concept node embeddings:

```python
# extraction/dedup.py
def upsert_concept(graph: KnowledgeGraph, candidate: ConceptNode) -> ConceptNode:
    """
    If a sufficiently similar concept exists, merge into it instead of inserting.
    Otherwise insert as new.
    """
    existing = graph.all_concepts()
    if not existing:
        graph.add_concept(candidate)
        return candidate
    
    existing_embeddings = [c.embedding for c in existing if c.embedding]
    if not existing_embeddings:
        graph.add_concept(candidate)
        return candidate
    
    sims = cosine_similarity([candidate.embedding], existing_embeddings)[0]
    best_idx = sims.argmax()
    
    if sims[best_idx] > 0.92:
        # Merge: update existing node's doc list, citation count, importance weight
        target = existing[best_idx]
        merged = target.model_copy(update={
            "source_doc_ids": list(set(target.source_doc_ids + candidate.source_doc_ids)),
            "citation_count_total": target.citation_count_total + candidate.citation_count_total,
            "importance_weight": min(1.0, target.importance_weight + candidate.importance_weight * 0.5),
        })
        graph.update_concept(merged)
        return merged
    
    # New concept: use stable ID from embedding bytes, not SHA1 of label
    stable_id = "concept:" + str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        candidate.embedding.tobytes().hex()[:64]
    ))
    candidate = candidate.model_copy(update={"concept_id": stable_id})
    graph.add_concept(candidate)
    return candidate
```

3. Use the cluster centroid mean embedding as the concept's embedding vector, not the
   embedding of the LLM-generated label+description text.

**Effort estimate:** 2 days

**Impact if not fixed:** Every ingestion run pollutes the graph with duplicate concept nodes.
Collision detection fires alerts against near-duplicate targets, fragmenting relevance across
5-15 nodes that should be 1. The graph grows unboundedly on re-ingestion. No query against
the graph is reliable because the concept you're searching for may exist under 6 different IDs.

---

## Priority 4 — LLM Intent Classifier Before Collision Detection

**Problem** (collision-detector F1 + F4, severity 9/10 each)

The collision detector embeds the raw query text and compares it to concept node embeddings
via cosine similarity. This cannot distinguish:

- "What is eventual consistency?" (learning it — valid collision signal)
- "Our system uses eventual consistency." (deployed it — false positive)
- "Eventual consistency is insufficient for our use case." (surpassed it — false positive)

All three produce cosine similarity > 0.85 with the Eventual Consistency concept node.
All three trigger the same collision alert. Two of three are false positives.

The sentence transformer (all-MiniLM-L6-v2) measures vocabulary proximity, not epistemic
stance. It was not trained to distinguish discovery from mastery. No threshold tuning fixes
this. The fundamental problem is that stance information is discarded when raw text is embedded.

A fast wrong system trains users to ignore alerts, which is worse than no system.

**Proposed fix**

Add an intent classification gate before the embedding step:

```python
# collision/intent.py
INTENT_PROMPT = """Classify the intent of the following query in one word.
Choose from: exploring, implementing, troubleshooting, citing, evaluating.
- exploring: user does not know about a concept and is encountering it for the first time
- implementing: user is actively building something using a concept
- troubleshooting: user is debugging a known concept
- citing: user is referencing prior work they already know
- evaluating: user is comparing known alternatives

Query: {query}

Respond with JSON: {{"intent": "<word>", "confidence": <0.0-1.0>}}"""

def classify_intent(query: str, llm_client) -> tuple[str, float]:
    resp = llm_client.complete(INTENT_PROMPT.format(query=query))
    data = json.loads(resp)
    return data["intent"], data["confidence"]
```

In detector.py, add as first step:

```python
intent, confidence = classify_intent(query, self._client)
if intent not in ("exploring", "implementing"):
    return CollisionReport(query=query, candidates=[], top_alert=None,
                           intent=intent, intent_confidence=confidence)
```

Also update the composite score from multiplicative to additive:
```python
# OLD (collapses dynamic range):
relevance = sim * concept.absorption_score * concept.importance_weight

# NEW (interpretable, debuggable):
relevance = (0.4 * intent_confidence) + (0.35 * sim) + (0.25 * concept.absorption_score)
```

**Effort estimate:** 2 days (includes updating detector.py, tests, and threshold recalibration)

**Impact if not fixed:** The collision detector fires on every paper that cites or references
a concept. Practitioners who write about prior work get constant false-positive alerts. Users
who receive 10 wrong alerts ignore the 11th correct one. The system's core UX breaks down
within days of first use.

---

## Priority 5 — Ground Truth Dataset and Model Validation

**Problem** (decay-model F7, severity 9/10)

There is no way to know if the decay model is right or wrong. No labeled dataset exists at
the concept level. Every weight (0.45/0.30/0.25), every threshold (decay > 0.65), every
normalization constant (/ 20.0) is unvalidated guesswork. Without ground truth, tuning
is compounding error.

The AUROC of the current model on a meaningful test set is unknown. If it is below 0.7,
the model performs no better than random assignment on its stated task and should not be
used to generate alerts.

**Proposed fix**

Build a validation cohort from OpenAlex historical data:

```python
# decay/calibration.py
"""
Build a labeled decay dataset from OpenAlex.

Method:
1. Pull 2000 concepts from OpenAlex published 1990-2005 (old enough for outcomes to manifest).
2. Compute the three raw signals as of 2015 (before the label is known).
3. Compare 2015 citation rate to 2025 citation rate.
   - Drop >70% from 2015 to 2025: label "decayed"
   - Drop <20% from 2015 to 2025: label "stable"
   - Between 20-70%: exclude from training set (ambiguous)
4. Run current decay model on 2015 snapshots. Measure AUROC against labels.
5. If AUROC < 0.70: model is no better than random. Do not ship user-facing alerts.
6. Train logistic regression on the three signals to extract calibrated weights.
   Those weights replace the 0.45/0.30/0.25 hardcodes.
"""

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_val_score

def train_decay_weights(X: np.ndarray, y: np.ndarray) -> dict:
    """
    X: (n_samples, 3) — [citation_decay, domain_gap, synthesis_decay]
    y: (n_samples,) — binary: 1=decayed, 0=stable
    Returns empirical weights and AUROC.
    """
    clf = LogisticRegression(C=1.0, max_iter=1000)
    auroc = cross_val_score(clf, X, y, cv=5, scoring="roc_auc").mean()
    clf.fit(X, y)
    weights = dict(zip(["citation", "domain", "synthesis"], clf.coef_[0]))
    return {"weights": weights, "auroc": float(auroc)}
```

Budget: ~40 person-hours for annotation of a 500-concept sample (manual labeling required for
the ambiguous middle; automated labeling for clear decayed/stable cases).

If AUROC >= 0.70 with calibrated weights: set WEIGHT_CITATION, WEIGHT_DOMAIN, WEIGHT_SYNTHESIS
env vars to the logistic regression coefficients. Do not ship alerts until this is done.

**Effort estimate:** 3-5 days (OpenAlex API exploration + annotation pipeline + validation harness)

**Impact if not fixed:** The model produces decay scores that may have zero correlation with
actual knowledge decay. Weights are arbitrary. No improvement is possible without a feedback
signal. Every tuning decision makes the model more complex and no more correct. The system
ships with a confidence it has not earned.
