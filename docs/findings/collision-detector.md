# Collision Detector — Critical Findings

**Role:** Collision Detector Critic
**Target:** `remnant/collision/detector.py` + supporting modules
**Date:** 2026-06-08
**Verdict:** The current implementation cannot reliably distinguish "approaching a concept"
from "mentioning a concept." It is a semantic search engine wearing a collision detector
mask. Most of the seven listed failure modes are not edge cases — they are the default
behavior. The system will fire wrong alerts routinely in production.

---

## Finding 1 — Cosine similarity cannot detect "approaching" vs. "mentioning"
**Severity: 9/10**

The fundamental premise is broken. Cosine similarity on sentence-transformer embeddings
measures semantic proximity of meaning, not epistemic stance toward that meaning.

"How do I handle network timeouts?" and "I implemented idempotent retry with exponential
backoff for distributed network timeout recovery" both embed close to every distributed
systems paper on fault tolerance, circuit breakers, and eventual consistency. They embed
close for the same reason: they share conceptual vocabulary.

The model (all-MiniLM-L6-v2) has zero ability to answer "is this person approaching this
concept for the first time, or are they citing it as prior knowledge?" It was not trained
to make that distinction. No sentence-transformer was.

A practitioner who writes "as in Lamport's seminal work on time in distributed systems..."
is NOT approaching Lamport clocks — they already know it. The system will still fire a
collision alert at 0.80+ similarity.

**Redesign required.** Approaching-detection needs either:
- Explicit linguistic stance markers ("how to", "trying to", "I don't understand why",
  "what's the best way", "can someone explain") extracted before embedding
- A separate classification head trained on (query, concept, is_approaching) triples
- Or query intent classification via LLM before the embedding step


## Finding 2 — Composite score collapses indistinguishable values
**Severity: 8/10**

```python
relevance = sim * concept.decay_score * concept.importance_weight
```

Three independent signals multiplied together produce a single uninterpretable float.

Example from the task body: 0.72 × 0.9 × 0.5 = 0.324, same as 0.45 × 0.71 × 1.0 = 0.324.
These represent completely different situations:
- First: high similarity + strong decay + moderate importance (strong directional signal)
- Second: moderate similarity + moderate decay + full importance (weak, scattered signal)

The ranking cannot distinguish these. The system ranks them identically.

The formula also has a mathematical property that makes it worse: multiplying three [0,1]
values always collapses toward zero. Most real scores land in [0.1, 0.35]. The dynamic
range disappears. A concept at 0.72 sim and one at 0.55 sim might sort to adjacent ranks
after the multiplications.

**Redesign required.** Use a weighted additive combination with interpretable components:
```
score = (w1 * sim) + (w2 * decay_score) + (w3 * importance_weight)
```
Or rank on similarity first, use decay/importance as secondary sort keys. Never collapse
three independent signals into one multiplicative value you can't debug.


## Finding 3 — COLLISION_SIMILARITY_THRESHOLD=0.72 was not tested against anything
**Severity: 8/10**

This number appears in config.py with no comment, no cite, no test file that validates it.

all-MiniLM-L6-v2 cosine similarities are notoriously inflated. On STS benchmarks, random
unrelated sentences in the same domain routinely score 0.5–0.65. The "semantic space" is
not uniform — topics cluster and cross-topic similarities are high even when conceptually
distant. A populated knowledge graph with hundreds of concepts will produce false positives
constantly at 0.72.

Specific unknowns:
- What is the false positive rate at 0.72 on a graph with 500 concepts? 5000?
- What is the false negative rate? (Concept being approached but similarity = 0.68)
- Was this threshold derived from any labeled dataset?
- Does the secondary gate (`decay_score > 0.4`) compensate? No — it adds a second
  uncalibrated filter on top of an uncalibrated threshold.

There is also a silent second threshold on line 51: `if sim < 0.40: continue`. Two magic
numbers, zero calibration for either.

**Redesign required.** Build a labeled evaluation set: (query, concept, ground_truth_collision)
pairs. Plot precision/recall curves. Pick a threshold from data. Document it with numbers.


## Finding 4 — Intent blindness: embedding raw text destroys stance information
**Severity: 9/10**

```python
query_vec = embed_one(query)
```

The entire query is embedded as a bag of meaning. The embedding space cannot represent
the difference between:
- "What is eventual consistency?" (learning it)
- "Our system uses eventual consistency." (has deployed it)
- "Eventual consistency is insufficient for our use case." (already surpassed it)

All three will have cosine similarity > 0.85 with a ConceptNode for "Eventual Consistency."
All three will trigger the same collision alert. Two of the three are false positives.

The problem is architectural: you need the semantic content AND the pragmatic frame
(intent, tense, stance) to distinguish discovery from mastery. Sentence embeddings
discard the frame.

**Redesign required.** Run an LLM classifier on the query before embedding:
- Classify intent: {exploring, implementing, troubleshooting, citing, evaluating}
- Only "exploring" and "implementing" are valid collision signals
- Or extract keyphrases and classify each keyphrase's stance separately


## Finding 5 — No feedback loop, the system cannot improve
**Severity: 7/10**

When the system fires a wrong alert, nothing changes. There is no mechanism anywhere in
the codebase to:
- Mark an alert as false positive
- Record that a collision did not actually occur
- Update thresholds based on outcomes
- Update concept embeddings if descriptions are wrong
- Track whether users ignored the alert

The system fires alerts into a void and forgets them. Every run starts from exactly the
same calibration as day one. There is no learning, only drift — as the graph grows, the
false positive rate silently increases and nobody knows.

This is not just missing functionality — it makes the threshold problem (Finding 3)
permanently unsolvable. You cannot calibrate what you do not measure.

**Redesign required.** Minimum viable feedback loop:
1. Log every CollisionReport to a database with a UUID
2. Surface a thumbs-up/thumbs-down endpoint per alert
3. Aggregate feedback weekly, rerun threshold calibration
4. Track precision/recall over time as a system health metric


## Finding 6 — "Collision detected" has no delivery context; alert is a string
**Severity: 6/10**

```python
top_alert = next((c for c in top if c.alert), None)
return CollisionReport(query=query, candidates=top, top_alert=top_alert)
```

The CollisionReport is returned to... the caller. That's it. There is no delivery
mechanism, no notification channel, no webhook, no email trigger, no UI component.

The `_build_summary` function produces a formatted string with an emoji prefix. This
suggests the intended UX is a text string, but the text string is never delivered to
any user via any channel in this codebase.

Unanswered design questions:
- When does detect() get called? On every keystroke? On save? On submit?
- Is this synchronous (blocking the user's workflow) or async (background notification)?
- Is the alert inline in a writing tool? An email? A Slack message?
- Does the user see all candidates or just the top alert?
- Can the user dismiss/acknowledge an alert?

Without delivery context, the alert is an intention, not a product feature.

**Redesign required.** Define the delivery contract before building more detection logic.
Detection precision doesn't matter if nobody sees the alert correctly.


## Finding 7 — Adversarial vocabulary novelty: the inverse failure
**Severity: 7/10**

The task raises this correctly. A researcher deliberately using new vocabulary for a known
concept will produce LOW cosine similarity against the existing ConceptNode, which uses
the established vocabulary in its description. The system will MISS the collision.

This is the opposite failure mode from Finding 1: instead of too many false positives from
semantic surface similarity, you get false negatives from semantic vocabulary distance.

Concrete case: A paper describing "gradient accumulation debt" is actually re-discovering
technical debt in ML training pipelines. The phrase "gradient accumulation debt" does not
appear in the ConceptNode for "Technical Debt." Cosine similarity: ~0.45. Below threshold.
Collision missed.

Is it correct behavior? No. The conceptual collision is real; the vocabulary novelty is
irrelevant. A system meant to prevent re-derivation needs concept-level matching, not
vocabulary-level matching.

**Redesign required.** Embed multiple paraphrases of each concept at indexing time.
Or use an LLM to extract the core concept claims from the query and match those against
concept definitions, not raw text vs. raw text.


## Finding 8 — Embedding register mismatch: descriptions vs. forum posts
**Severity: 8/10**

This is not in the task brief but it is a critical flaw.

ConceptNode.description is "a 1-paragraph canonical summary" — formal, encyclopedic,
domain-specific vocabulary. The query docstring says "Any text — a question, issue
description, forum post, etc."

These two text registers have different embedding distributions. A Wikipedia-style
paragraph on "Paxos consensus protocol" is semantically dense and formal. A Stack Overflow
question asking "why does my distributed cache lose writes?" is informal, query-framed,
and symptom-focused.

The cosine similarity between these two is measuring register distance as much as concept
distance. The system will miss collisions for informal queries against formal concepts,
and may spuriously fire on formal queries against tangentially formal descriptions.

**Redesign required.** Either:
- Index each concept with embeddings from multiple register examples (formal, informal,
  question-form, problem-statement form)
- Or normalize the query to a canonical form before embedding using an LLM step


## Finding 9 — O(N) full graph scan with no ANN indexing
**Severity: 5/10**

```python
for c in graph.all_concepts():
    if c.embedding:
        concepts.append(c)
        embeddings.append(c.embedding)
matrix = np.array(embeddings, dtype=np.float32)
similarities = batch_similarity(query_vec, matrix)
```

Every call to detect() loads all concept embeddings from the graph into memory, constructs
a float32 matrix, and computes dot products across the entire corpus. This is O(N) in
concept count.

For a graph with 10,000 concepts (a few weeks of crawling), this is slow but tolerable.
For 100,000 concepts, this allocates ~1.5GB and takes seconds per query. For 1M+ concepts,
it is unusable.

Additionally, embeddings are stored as `list[float]` in Pydantic models — no memory
pooling, no GPU tensor, no persistent index.

**Redesign required.** Use FAISS (CPU) or hnswlib for approximate nearest neighbor search.
Build the index once at startup, update it incrementally on new concept ingestion. The
top_k query becomes a single FAISS.search() call with sub-millisecond latency at any scale.


## Finding 10 — decay_score semantics counterintuitive despite being intentional
**Severity: 4/10**

The field is documented: `# 0–1, higher = more invisible`. High decay = the concept has
become so widely assumed that nobody cites it explicitly anymore — it has "decayed" from
the citation record.

The alert condition `concept.decay_score > 0.4` fires on FORGOTTEN concepts. The relevance
formula boosts forgotten concepts via multiplication. This is architecturally intentional:
the system should alert louder when you're about to re-derive something so established it's
invisible.

But the name "decay_score" reads as "how much has this concept degraded in quality." Every
engineer reading this code without the docs will misinterpret it. The field name is a
maintenance liability.

**Minor redesign.** Rename to `invisibility_score` or `absorption_score` with a one-line
comment explaining the inversion. This is a naming bug, not a logic bug — but it will
cause wrong contributions over time.


---

## Summary Verdict

| Finding | Severity | Category |
|---------|----------|----------|
| F1: Cosine cannot detect "approaching" vs "mentioning" | 9/10 | Architectural |
| F4: Intent blindness — stance destroyed by embedding | 9/10 | Architectural |
| F2: Composite score collapses to indistinguishable values | 8/10 | Scoring |
| F3: Threshold 0.72 untested, uncalibrated | 8/10 | Calibration |
| F8: Register mismatch — descriptions vs. forum posts | 8/10 | Architectural |
| F7: Adversarial vocabulary novelty produces false negatives | 7/10 | Robustness |
| F5: No feedback loop, cannot improve | 7/10 | Systemic |
| F6: No delivery mechanism — alert is a string going nowhere | 6/10 | Product |
| F9: O(N) scan, no ANN index | 5/10 | Performance |
| F10: decay_score naming inversion | 4/10 | Naming |

Two findings are architectural show-stoppers that cannot be patched:

**F1 and F4 are the same root cause stated twice.** The system embeds raw text and compares
to concept embeddings without capturing any stance, intent, or epistemic relationship.
Cosine similarity on sentence-transformer embeddings is a vocabulary proximity measure. It
is not, and has never been, a re-derivation detector. No threshold tuning fixes this. No
formula changes fix this. The entire detection pipeline needs an intent classification
layer before the embedding comparison step.

## Minimum Viable Redesign

```
query
  → LLM intent classifier → if NOT {exploring | implementing}: skip detection
  → keyphrase extractor
  → per-keyphrase: ANN search over concept space (FAISS, top_k=20)
  → LLM re-ranking: "Is this query approaching concept X or citing/referencing it?"
  → weighted score: intent_confidence × similarity × invisibility_score
  → alert if score > calibrated_threshold (derived from labeled eval set)
  → log to feedback DB with UUID
  → deliver via configured channel (webhook/email/inline)
```

This is heavier but it is correct. The current implementation is fast and wrong.
A fast wrong system trains users to ignore alerts, which is worse than no system.
