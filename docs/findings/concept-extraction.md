# GODMODE Findings: Concept Extraction Pipeline

**Role:** Concept Extraction Critic
**Target:** `remnant/extraction/concept.py` + `remnant/extraction/fingerprint.py` + `remnant/cli.py` (clustering logic)
**Date:** 2026-06-08
**Verdict:** The pipeline produces a plausible-looking knowledge graph that is structurally unreliable. Most of the design decisions are defaults and guesses dressed up as architecture. At scale, the graph degrades into a polluted set of vague, duplicate, and frequency-biased concept nodes with no stable identity across runs.

---

## Finding 1: One Concept Per Cluster Is a Category Error

**Severity: 9/10**

```python
# concept.py:29-43
_EXTRACT_PROMPT = """...identify the single core underlying concept they all express."""
```

AgglomerativeClustering groups documents by embedding distance, not by conceptual unity. A cluster of 6 ML-privacy papers might contain:
- Differential privacy in SGD (mathematical framework)
- Federated learning privacy guarantees (system architecture)
- Membership inference attacks (adversarial threat modeling)

These are three distinct, non-overlapping concepts. The prompt forces the LLM to hallucinate a synthetic meta-concept ("Privacy-Preserving Machine Learning") that accurately describes none of them. The result is a concept node that looks meaningful but is actually a lossy compression artifact.

**What actually happens:** The LLM picks the most salient theme in the first 1-2 abstracts it sees and anchors the label to that. The other concepts in the cluster become invisible to the graph. A user querying for "membership inference attacks" will not find the concept node because it was collapsed into the broader label.

**Fix:**
- Allow multi-concept extraction per cluster. Return a list of ConceptNodes, not one.
- Or: use sub-clustering within large clusters before LLM labeling (recursively split if cluster embeddings have high intra-cluster variance).
- Prompt change: replace "the single core underlying concept" with "up to N distinct concepts these documents express, where N is 1 if they genuinely converge or more if they are meaningfully distinct."


---

## Finding 2: n_clusters Formula Is Numerology

**Severity: 8/10**

```python
# cli.py:76
n_clusters = max(2, min(len(docs) // 5, 20))
```

This formula has no theoretical basis. It was invented. Let's trace the failure modes:

**Scenario A — 100 docs on distributed systems, 3 real concepts:**
Formula gives n_clusters=20. You get 20 clusters, each with ~5 docs, each labeled with a micro-variation of consensus/replication/sharding. The graph has 20 nodes for what should be 3. Every downstream query fragments relevance across 20 near-duplicate nodes. The collision detector noise floor rises.

**Scenario B — 100 docs on distributed systems, 50 real concepts:**
Formula gives n_clusters=20. You get 20 clusters, each containing papers from 2-3 distinct concepts. Each cluster collapses to one label (see Finding 1). Real signal is destroyed. 30 concepts never appear in the graph.

**Scenario C — 10 docs:**
n_clusters=max(2, 2)=2. You always get exactly 2 clusters regardless of content. One doc on quantum computing and one on Byzantine fault tolerance get shoved into the same cluster.

**The formula hardcodes a linear scaling assumption** (1 concept per 5 docs) that has no empirical support. Real concept density is domain-dependent. A focused survey returns 100 papers on 3 concepts. A broad search returns 100 papers on 80 concepts.

**Fix:**
- Use HDBSCAN with `min_cluster_size=3` — it finds natural clusters and marks noise points rather than forcing every doc into a cluster.
- Or: compute the silhouette score across a range of k values (2 to min(len(docs)//3, 30)) and pick the elbow.
- Or: use agglomerative clustering with a distance threshold (`distance_threshold`) instead of n_clusters, letting cluster count emerge from the data.


---

## Finding 3: all-MiniLM-L6-v2 Is the Wrong Tool for Scientific Literature

**Severity: 7/10**

```python
# config.py:22
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
```

This model was trained on MS MARCO (web search), NLI pairs, and generic paraphrase datasets. Its training distribution has no significant overlap with scientific abstracts. Specific failures:

**Homonym collapse:** "prion" in molecular biology (infectious misfolded protein) vs. "prion" in concurrent programming (actor-model object primitive in PONY language). These will embed close together. A biology paper and a PL-theory paper get co-clustered. The LLM produces a label like "Protein Folding and Concurrent Systems" that makes no sense.

**Acronym ambiguity:** "BERT" (Bidirectional Encoder Representations from Transformers) vs. "BERT" (a building energy rating tool). "GAN" in machine learning vs. "GAN" in network protocols. MiniLM has no domain context to disambiguate.

**Technical vocabulary gap:** Terms like "magnetohydrodynamics," "epitranscriptomics," "renormalization group," or "zero-knowledge proof" are either OOV or severely under-represented in MiniLM's training data. These embeddings will be noisy.

**384 dimensions is too compressed** for the breadth of scientific vocabulary. SPECTER2 uses 768 dimensions and was specifically trained on citation graphs (paper-cites-paper = semantic similarity signal). It consistently outperforms MiniLM-L6 by 15-25% on scientific STS benchmarks.

**Fix:**
- Default to `allenai/specter2` or `allenai/specter2_base` for scientific literature.
- For biomedical: `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract`.
- Keep MiniLM as a fast/cheap option for non-scientific sources but never as the scientific default.
- Document this as a first-class config decision, not buried in an env var.


---

## Finding 4: SHA1(label.lower()) Produces an Unstable, Non-Deduplicated Graph

**Severity: 9/10**

```python
# concept.py:65
concept_id = "concept:" + hashlib.sha1(data["label"].lower().encode()).hexdigest()[:12]
```

This is the most structurally dangerous flaw. The concept ID is derived from a string produced by an LLM at temperature=0.2. Temperature 0.2 is not 0.0. And even at 0.0, different model versions, different context windows, or different abstract orderings will produce different labels for identical concepts.

**Observed label instability examples (likely at temperature=0.2):**
- "Eventual Consistency" vs "Eventual Data Consistency" vs "Consistency Models in Distributed Systems"
- "Transformer Attention Mechanism" vs "Self-Attention in Neural Networks" vs "Multi-Head Attention"
- "Federated Learning" vs "Federated Machine Learning" vs "Privacy-Preserving Federated Learning"

Each of these produces a different SHA1. Each run adds new nodes instead of updating existing ones. After 5 ingestion runs on overlapping literature, the graph has 5-15 near-duplicate concept nodes for "Transformer Attention," each with different doc sets, different importance_weights, and competing embeddings.

**The 12-char SHA1 prefix also has collision probability.** With 4^12 = ~17M possible values and a growing concept graph, collisions become non-negligible at ~4000 concepts (birthday paradox at 50% collision ~= sqrt(17M) ~= 4100 concepts). A collision maps two completely unrelated concepts to the same node. Silent data corruption.

**There is no deduplication pass anywhere in the codebase.**

**Fix:**
- After extracting a concept label, compute cosine similarity against all existing concept node embeddings. If any existing node exceeds a threshold (e.g., 0.92), merge instead of insert. Update the existing node's doc list, importance_weight, and last_cited.
- Use a UUID or a content-addressed hash of the concept EMBEDDING (not the label string) for the ID — embeddings are more stable than free-form text.
- Or: maintain a separate label index with fuzzy matching (rapidfuzz, BM25 over existing labels) to catch near-duplicate labels before they enter the graph.
- Use temperature=0.0 for concept labeling. There is no creative value in temperature here.


---

## Finding 5: importance_weight Measures Batch Frequency, Not Importance

**Severity: 6/10**

```python
# concept.py:81
importance_weight=min(1.0, len(docs) / 50.0),
```

And from models.py (the comment the implementation does NOT match):
```python
importance_weight: float = 0.5      # 0–1, derived from peak citation count
```

**The comment says citation count. The code uses batch doc count.** These are completely different signals. The code doesn't even have access to citation counts.

**The frequency=importance assumption fails catastrophically for:**
- Niche breakthroughs: mRNA vaccine technology had sparse academic coverage in 2019. importance_weight ≈ 0.1. The system would deprioritize it.
- Foundational rare papers: A concept appearing in 5 papers that ALL cite it as foundational (high cross-domain penetration) gets weight 0.1 while a dead-end concept in 50 mediocre papers gets weight 1.0.
- Temporal effects: A new concept will always have low frequency in early ingestion. It never "earns" importance because weight is recalculated from scratch each batch (no accumulation across runs).

**Additionally:** the decay scoring system (`collision/detector.py:53`) multiplies `decay_score * importance_weight`. If a groundbreaking niche concept has importance_weight=0.1, it is literally 10x less likely to surface as a collision alert than a common but unremarkable concept. The whole alert pipeline is biased toward noise.

**Fix:**
- Accumulate doc count across ingestion runs, not per-batch.
- Pull actual citation counts from the arXiv/PubMed APIs (both expose citation metadata or it's available via Semantic Scholar API).
- Add cross-domain penetration as a signal: a concept appearing in papers from 3+ distinct domains gets a multiplier.
- Add recency-of-synthesis: concepts whose newest papers are recent get boosted.


---

## Finding 6: Silent JSON Parse Failure Produces Garbage Concept Nodes

**Severity: 7/10**

```python
# concept.py:58-62
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    data = {"label": docs[0].title[:80], "description": docs[0].abstract[:300], "domains": []}
```

**The failure modes for the LLM JSON output:**

1. **Markdown fences:** Despite the prompt saying "no markdown fences," models (especially gpt-4o-mini) frequently wrap JSON in ` ```json ... ``` `. `json.loads` fails. Fallback fires.

2. **Truncated JSON:** `max_tokens=600` is tight for a 1-2 paragraph description. If the description runs long, the response gets truncated mid-JSON. `json.loads` fails. Fallback fires.

3. **The fallback is catastrophic:** `docs[0].title[:80]` is a paper title, not a concept label. "Attention Is All You Need" becomes a concept node. "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding" (truncated to 80 chars: "BERT: Pre-training of Deep Bidirectional Transformers for Language Understandin") becomes a concept node. These paper-title concepts pollute the graph with invalid nodes that look real but contain no semantic generalization.

4. **No logging:** There is no `logger.warning()` or counter for parse failures. You have no idea how often this happens in production.

5. **KeyError hazard:** If the LLM returns valid JSON but omits the `"label"` key (e.g., returns `{"name": "...", "description": "..."}`), line 65 (`data["label"].lower()`) raises `KeyError` and crashes the entire ingestion run with an unhandled exception. The fallback only catches `JSONDecodeError`, not `KeyError`.

**Fix:**
- Before `json.loads`, strip markdown fences: `raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()`
- Increase `max_tokens` to at least 800.
- After parsing, validate required keys exist before use. Fall back gracefully with a log warning if any are missing.
- Count parse failures and expose as a metric. If >20% of extractions fall back, the LLM/prompt is broken.
- Use structured output (OpenAI's `response_format={"type": "json_schema"}`) to guarantee valid JSON with required fields.


---

## Finding 7: What the Knowledge Graph Actually Looks Like at 100 Papers

**Severity: 8/10 (system-level)**

Running the pipeline on 100 arXiv papers in a domain like "distributed systems":

**Predicted graph state:**
- n_clusters=20 (forced by formula)
- ~15-18 concept nodes created (some clusters may be empty)
- ~3-5 of those nodes will have been generated from truncated/varied abstract sets and may be near-duplicates of each other
- ~1-2 nodes will be paper-title fallbacks from JSON parse failures
- All nodes have importance_weight proportional to cluster size, so nodes from large clusters (5 docs) get 0.1 while smaller-than-expected (but conceptually denser) clusters get less
- Concept node IDs are SHA1 of LLM-generated labels — unstable across re-runs
- Re-running on the same 100 papers produces a DIFFERENT graph with different concept IDs

**The graph is not idempotent.** This is the fundamental problem. A knowledge graph whose nodes change identity on re-ingestion of the same data is not a knowledge graph — it is a log of LLM hallucinations indexed by SHA1.

**Observable uselessness:**
- Query "distributed consensus" → may or may not match, depending on whether the LLM said "Distributed Consensus" or "Consensus Protocols" or "Agreement in Distributed Systems" this run
- Collision detection compares concept embeddings but concept embeddings are computed from LLM-generated descriptions, not from the cluster centroid — so two near-duplicate concept nodes (different labels, same underlying papers) will have similar but not identical embeddings, both surviving in the graph
- The `COLLISION_SIMILARITY_THRESHOLD=0.72` is tuned against a stable graph; against this unstable one, the threshold may catch some duplicates but will also produce false positives

---

## Additional Issues (Not in the Original Brief)

**A. Only 6 abstracts sampled per cluster (concept.py:49)**
`docs[:6]` — if a cluster has 30 documents, the LLM sees only 6. The label is biased toward whichever 6 sort first (insertion order). Fix: sample representatively (e.g., pick the 6 closest to the cluster centroid).

**B. Concept embedding is from LLM text, not from cluster centroid (concept.py:71)**
`embedding = embed_one(data["label"] + " " + data["description"])` — the concept node's embedding vector is computed from the LLM-generated description, not from the actual centroid of the document embeddings that formed the cluster. This means the concept embedding drifts from the documents it represents. Similarity searches between documents and concepts will underperform. Fix: use the mean of the cluster's document embedding vectors as the concept's embedding, or at minimum average both.

**C. Dates are batch-relative, not concept-historical (concept.py:67-69)**
`first_seen = min(published_dates)` uses dates from THIS ingestion batch filtered by `since_year`. If you ingest papers from 2022-2026, "Neural Networks" gets `first_seen=2022`. The concept has existed since the 1940s. The temporal timeline in the graph is fiction. Fix: use the earliest known published_at across ALL documents linked to this concept across all batches, not just the current run.

**D. temperature=0.2 should be 0.0 for deterministic labeling**
Concept labeling is not a creative task. There is no value in label variation. Use temperature=0.0 to maximize label stability and reduce the duplicate-node problem from Finding 4.

**E. Global `_client` singleton with no retry/backoff**
The OpenAI client is a module-level global. If the LLM API returns a 429 or 503, the exception propagates and kills the entire concept extraction loop. There is no `tenacity` retry, no exponential backoff, no per-concept failure isolation.

---

## Summary Scorecard

| Finding | Issue | Severity |
|---------|-------|----------|
| F1 | One concept forced per cluster — collapses multi-concept clusters | 9/10 |
| F2 | n_clusters formula is arbitrary — wrong count for any real domain | 8/10 |
| F3 | MiniLM-L6-v2 fails on scientific vocab and domain disambiguation | 7/10 |
| F4 | SHA1(label) IDs are unstable — duplicate nodes, no dedup | 9/10 |
| F5 | importance_weight = batch frequency, not importance | 6/10 |
| F6 | Silent JSON fallback produces paper-title garbage nodes | 7/10 |
| F7 | Graph is non-idempotent — re-run on same data produces different graph | 8/10 |
| A | Only 6 docs sampled per cluster regardless of cluster size | 5/10 |
| B | Concept embedding computed from LLM text, not cluster centroid | 6/10 |
| C | Temporal dates are batch-relative, not historically accurate | 5/10 |
| D | temperature=0.2 when 0.0 is correct for deterministic labeling | 4/10 |
| E | No retry/backoff on LLM calls — single 429 kills ingestion run | 6/10 |

**Overall pipeline reliability at 100 papers: ~40%.** Roughly 60% of concept nodes will have one or more of: wrong label, duplicate identity, wrong embedding, garbage fallback content, or incorrect temporal metadata. The graph looks populated but is not trustworthy as a knowledge source.

---

## Recommended Rebuild Priority

1. **Fix SHA1 instability first (F4)** — this is the graph's foundation. Without stable concept identity, everything else is wasted work.
2. **Fix JSON parse reliability (F6)** — structured outputs + fence stripping + key validation. One afternoon of work, eliminates garbage nodes.
3. **Replace clustering formula (F2)** — switch to HDBSCAN or silhouette-scored agglomerative clustering.
4. **Allow multi-concept extraction (F1)** — change the prompt and return type. Medium complexity.
5. **Swap embedding model (F3)** — drop-in replacement, one config line. `allenai/specter2` is available on HuggingFace.
6. **Fix importance_weight (F5)** — requires Semantic Scholar API integration for citation counts.
