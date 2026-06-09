# Translation Broker — Critical Findings

**Reviewer:** T4 Translation Broker Critic
**Target:** `remnant/translation/broker.py`
**Mode:** GODMODE — no hedging, full critical freedom

---

## Summary Verdict

The translation broker is a single LLM prompt dressed up as a knowledge translation engine.
It has no grounding, no validation, no quality signal, no feedback loop, and it explicitly
invites hallucination in its own prompt text. The KnowledgeGraph parameter is a prop — it's
passed in and immediately used only to fetch a label and a truncated description string.
Everything valuable about the graph (relationships, citations, co-occurrences, cross-domain
edges) is thrown away before the LLM ever sees it.

This is not a translation engine. It is an autocomplete wrapper with delusions of rigor.

---

## Finding 1 — Single LLM Call, Zero Grounding

**Severity: 9/10**

The entire translation lives in `_TRANSLATE_PROMPT`, a 23-line string filled with
`{placeholders}`. The only inputs are: field names, concept label, and 800 characters of
description. The LLM produces the translation entirely from its parametric memory with
zero retrieval, zero verification, zero grounding against actual literature.

The error rate is unknowable because there is no oracle to check against. For well-covered
concepts in popular domains (physics → economics), error may be modest. For obscure concepts
in specialized subfields, error could be near-total — the model will produce confident,
fluent, wrong analogies because fluency is not correctness.

**How you would know:** You don't, currently. The function returns without any confidence
estimate, any self-critique pass, or any flagging of uncertainty.

**Fix:** Before calling the LLM, retrieve 5–10 actual cross-domain papers or prior
translations from the graph (or a vector store built from the corpus). Inject them as
few-shot examples. Run a second LLM pass that scores the translation against those examples.
Require explicit uncertainty markers ("I am uncertain whether this analogy holds") and
surface them in the `TranslationResult`.

---

## Finding 2 — Explicit Permission to Hallucinate Citations

**Severity: 10/10**

Line 44 of the prompt:

    "Suggest 2–3 specific papers or resources ... (can be approximate if exact titles unknown)."

"Can be approximate if exact titles unknown" is not a safety net. It is an instruction to
fabricate. The LLM will produce plausible-sounding author names, plausible journal names,
plausible years. Downstream users will search for them, fail to find them, and either lose
trust in REMNANT entirely or — worse — cite the hallucinated papers themselves.

The `suggested_papers` field in `TranslationResult` has no `verified: bool` flag. There is
no DOI, no URL, no arXiv ID. It is a list of strings that may or may not correspond to
anything that exists in the physical universe.

**Fix:**
1. Remove the "can be approximate" permission immediately. Replace with: "Only cite papers
   you are highly confident exist. If uncertain, omit."
2. Add a post-processing verification step: attempt DOI/arXiv lookup for each suggested
   paper. Flag unverified citations as `unverified=True` in the schema.
3. Better: generate papers as search queries, not citations. Have the system retrieve actual
   papers from Semantic Scholar or arXiv, then inject the real titles back into the result.
   The LLM should suggest *directions*, not invent *sources*.

---

## Finding 3 — "Use Their Vocabulary" Is a Statistical Lie

**Severity: 8/10**

The prompt instructs the LLM to "use their vocabulary, their familiar analogies, their
typical problems." The LLM cannot do this for a highly specialized subfield. It knows the
population-weighted average of all text it was trained on. For semiconductor fab engineers,
process integration architects, or wetlands ecologists, the vocabulary the LLM "knows" is
mostly popular-press representations of those fields, not the actual practitioner vocabulary.

Translating phase transitions to semiconductor fab engineers is a specific example worth
examining: a fab engineer cares about nucleation kinetics, grain boundary migration,
phase diagrams at specific process nodes, dopant diffusion coefficients. The LLM will
produce an analogy involving "threshold switching" or "state changes in materials" — correct
at the pop-science level, useless at the engineering level where the practitioners already
know the surface-level version and need the deep structural analogy.

The more specialized the target field, the worse this gets. The LLM's coverage of
specialized vocabulary is inversely proportional to the size of that field's internet
footprint.

**Fix:**
1. Allow callers to inject a practitioner vocabulary file — a list of key terms, canonical
   references, and example phrasings from real papers in the target domain.
2. Build a retrieval augmentation step: before translation, fetch the 5 most-cited papers
   in the target domain related to the concept's themes. Extract their abstract vocabulary
   and inject it into the prompt as grounding.
3. At minimum, add a `practitioner_context` field to `TranslationRequest` that callers can
   populate with domain-specific anchors.

---

## Finding 4 — No Quality Metric for Translation

**Severity: 9/10**

There is no number, score, rubric, or signal of translation quality anywhere in the codebase.
`TranslationResult` returns a translation string. That string might be brilliant or it might
be sophisticated-sounding nonsense. The caller has no way to distinguish.

"Phase transitions → organizational behavior" is the canonical example: the LLM will produce
a fluent, confident, structurally coherent translation that maps critical slowing down to
organizational warning signs before collapse. Is that correct? Is the structural analogy
sound? Is it useful to an OB researcher? The broker cannot tell you. It does not know.

Without a quality metric, REMNANT cannot:
- Rank multiple translation attempts to pick the best one
- Detect when a translation is likely hallucinated vs. grounded
- Improve over time (no signal to optimize against)
- Set user expectations ("this translation is high-confidence" vs. "speculative")

**Fix:**
1. Add a `confidence_score: float` field to `TranslationResult` computed by a second LLM
   pass that critiques the translation against the original concept description.
2. Implement a structural validity check: does the translation correctly preserve the key
   properties of the original concept (symmetry, scale, directionality)? This can be
   prompted explicitly.
3. Where ground truth exists (human-verified analogies in the literature), compute
   semantic similarity between generated and ground-truth translations as an offline metric.

---

## Finding 5 — One-Shot Translation With No Feedback Loop

**Severity: 7/10**

The function makes one API call and returns. There is no retry, no self-critique pass,
no mechanism for iterative refinement, and no path for a domain expert to provide
feedback that improves future translations.

Real cross-domain translation — the kind that produces insight rather than plausible
text — requires iteration. A physicist and an organizational behavior researcher working
together to translate "criticality" spend hours on it. They reject candidate analogies,
tighten the mapping, discover edge cases where the analogy breaks down. The broker
produces its output in one pass and declares the job done.

**Fix:**
1. Add a multi-pass pipeline: draft → self-critique ("identify 3 ways this analogy might
   fail") → revision → final.
2. Add a `feedback` field to `TranslationRequest` for expert corrections from prior runs.
   When feedback is present, inject it into the prompt as "a domain expert previously
   flagged these issues: ...".
3. Store translation results in the knowledge graph with a `validated: bool` flag.
   Validated translations become few-shot examples for future calls.

---

## Finding 6 — Translation Is Unidirectional Only (A→B Missing B→A)

**Severity: 6/10**

The broker takes `from_field` and `to_field`. It translates one way. The bidirectional
case — what does `to_field` know that `from_field` has not absorbed? — is never modeled.

This is a fundamental missed value proposition. The whole thesis of cross-domain knowledge
transfer is that both domains benefit. Physics may have formalisms organizational behavior
lacks; organizational behavior has empirical datasets and intervention studies that physics
analogues have never been tested against. By modeling translation as one-way export,
REMNANT becomes a lookup tool instead of a discovery tool.

**Fix:**
1. Add `TranslationRequest.bidirectional: bool = False`. When True, run both directions
   and return a `BidirectionalTranslationResult` that includes the reverse translation and
   a "what B knows that A could use" section.
2. More ambitiously: use the knowledge graph to identify concepts in `to_field` that
   structurally resemble the source concept and surface them as "counterpart concepts."
   This turns translation into genuine discovery.

---

## Finding 7 — No Unit Test Is Possible Without Ground Truth

**Severity: 8/10**

There are no tests in the codebase for `translate()`. This is rational — you cannot write
a meaningful unit test for a function that calls an LLM and returns free text — but the
absence is still a critical gap because it means the system has no automated quality
regression detection.

Ground truth for cross-domain concept translation does not generally exist as a labeled
dataset. However, partial ground truth does exist:
- Published analogies between domains in the literature (physics → economics, etc.)
- Expert-curated concept mappings in interdisciplinary review papers
- Cases where concepts were explicitly imported between domains with documented attribution

None of this is being used. The tests directory exists but contains nothing for translation.

**Fix:**
1. Build a golden-set of 20–50 well-documented cross-domain translations from the literature.
   Use them as regression tests: generate a translation, compute semantic similarity to the
   ground truth, fail if similarity drops below threshold.
2. For structural testing: parameterize tests on concept properties (is the translation
   directionality-preserving? does it correctly represent scale?). These can be LLM-judged
   and are more stable than text-match tests.
3. Add smoke tests that verify the function returns valid JSON with all required fields,
   that `key_analogies` has at least one entry, that `translation` is non-empty. These
   won't catch wrong translations but they catch regressions in the pipeline.

---

## Additional Issues Not in the Task Brief

### A — KnowledgeGraph Is Ignored After Lookup (Severity: 7/10)

The `graph: KnowledgeGraph` parameter is passed to `translate()` but used only to call
`graph.get_concept(request.concept_id)`. After that, the graph is dropped. None of its
cross-domain edges, citation links, co-occurrence data, or related concepts are passed
to the LLM. The function signature implies graph-grounded translation; the implementation
delivers prompt-only hallucination.

**Fix:** Before building the prompt, query the graph for concepts already connected to the
target concept, related concepts in the target domain, and existing citations. Inject these
as context: "Related concepts in {to_field} already in the graph: ...".

### B — Description Truncated to 800 Characters (Severity: 5/10)

Line 67: `concept.description[:800]`. For a rich concept description that runs 2000+
characters, this silently discards more than half the context. The LLM translates based
on a truncated, potentially mid-sentence description.

**Fix:** Use the first N tokens, not the first 800 bytes. Handle truncation explicitly:
log when truncation occurs, prefer summarization over hard cut.

### C — JSON Failure Silently Degrades (Severity: 6/10)

Lines 78–79: on `json.JSONDecodeError`, the raw LLM text is used as the translation,
and `key_analogies`/`suggested_papers` silently become empty lists. The caller has no
idea the parsing failed. This means a malformed response (e.g., LLM produces markdown
fences despite instructions) degrades silently to a worse result with no error surfaced.

**Fix:** Log the parse failure. Return a `TranslationResult` with a `parse_failed: bool`
field. At minimum, raise or warn.

### D — Global Singleton Client Is Thread-Unsafe (Severity: 4/10)

`_client` is a module-level global initialized on first call. Under concurrent requests
(e.g., async web framework), two threads can race on `_client is None` check and both
initialize. While the OpenAI client itself may be thread-safe, this pattern is wrong.

**Fix:** Use a lock or initialize at module load time.

### E — max_tokens=1200 May Truncate Translations (Severity: 5/10)

A 3–5 paragraph translation plus 3–5 analogies plus 2–3 papers in JSON easily exceeds
1200 tokens. When it does, the JSON is truncated, the parse fails, and finding C above
fires. The output silently degrades.

**Fix:** Raise max_tokens to at least 2000. Add structured output (JSON mode) to
prevent truncation-induced parse failures.

---

## Priority Fix Order

| Priority | Fix | Impact |
|---|---|---|
| 1 | Remove "can be approximate" citation permission + add verification | Stops active hallucination |
| 2 | Inject graph context (edges, related concepts) into prompt | Grounds the translation |
| 3 | Add confidence_score via second LLM critique pass | Enables quality filtering |
| 4 | Build 20-item golden translation set for regression tests | Detects quality regressions |
| 5 | Add practitioner_context to TranslationRequest | Fixes vocabulary accuracy |
| 6 | Multi-pass pipeline with self-critique | Improves translation depth |
| 7 | Bidirectional translation support | Unlocks discovery use case |
| 8 | Fix JSON truncation (raise max_tokens, log parse failures) | Stops silent degradation |
| 9 | Fix global singleton client | Thread safety |

---

*Written in GODMODE. No findings were softened.*
