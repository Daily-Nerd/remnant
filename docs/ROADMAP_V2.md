# REMNANT Roadmap v2

**Date:** 2026-06-08
**Replaces:** ROADMAP.md
**Basis:** 6-critic post-mortem review

Everything cut from v1 is noted with the critic finding that justified cutting it.
Phase 0 contains only what is required for a valid, non-misleading MVP.

---

## What Was Cut From v1 and Why

| v1 Item | Cut because |
|---|---|
| "First real user: pharma team" at Week 9-12 | Enterprise pharma sales cycle is 12-24 months minimum; will not happen in 3 months (business-gtm F1) |
| Consumer tier / individual researcher pricing | Consumer segment is not a market for epistemic infrastructure; no willingness to pay (business-gtm F4) |
| 7-source continuous indexing as MVP feature | 5 of 7 listed sources have no code; 3 are paywalled (corpus-ingestion F5) |
| Decay scoring as user-facing output in Phase 0 | No ground truth; model unvalidatable; all scores are noise until calibrated (decay-model F7) |
| Collision alerts without intent classifier | Alert fires on every citation/mention; false positives kill user trust within days (collision-detector F1+F4) |
| "Civilizational memory" framing in demo | Flagship bacteriophage example is outside corpus by design (corpus-ingestion F3) |
| Translation in Phase 0 | Prompt contains explicit hallucination permission; must not ship until fixed (translation-broker F2) |

---

## Phase 0 — Fix What Is Broken (Weeks 1-2)

**Goal:** A system that does not silently lie.
Nothing in Phase 0 adds new features. It makes the existing features tell the truth.
These are blocking. Nothing in Phase 1 is valid until Phase 0 is complete.

### 0.1 — Citation count integration (Priority 1)
- Integrate Semantic Scholar API for citation_count after each adapter fetch
- Add semantic_scholar_id: str to IngestedDocument
- Add tenacity retry for rate limits (100 req/5min free tier)
- Collect citationsPerYear for 3-window trajectory in decay_v2
- Exit criterion: citation_count > 0 for >80% of ingested documents

### 0.2 — Remove hallucination permission from translation (Priority 2)
- Remove "can be approximate" from _TRANSLATE_PROMPT
- Add verified: bool to each suggested citation in TranslationResult
- Add DOI/arXiv lookup via Semantic Scholar for each suggested paper
- Add parse_failed: bool to TranslationResult (surfaced, not swallowed)
- Raise max_tokens to 2000; add structured output (JSON schema)
- Exit criterion: No TranslationResult ships unverified citations without explicit warning flag

### 0.3 — Fix latent NameError in decay model
- ratio = 0.0 if peak_citations == 0 else recent_citations / peak_citations
- citation_decay = 0.5 if peak_citations == 0 else max(0.0, 1.0 - ratio)
- Exit criterion: No NameError possible in the alert string builder regardless of input

### 0.4 — Make decay weights configurable
- Replace 0.45/0.30/0.25 hardcodes with WEIGHT_CITATION/WEIGHT_DOMAIN/WEIGHT_SYNTHESIS env vars
- Default domain_gap unknown to 0.5 (not 1.0); consistent fallback philosophy
- Log weights used in every DecayReport for debuggability
- Exit criterion: Weights appear in DecayReport output; changing env vars changes scores

### 0.5 — Fix JSON parse reliability in concept extraction
- Strip markdown fences before json.loads
- Increase max_tokens to 800; set temperature=0.0 for concept labeling
- Validate required keys after parse; log.warning on fallback; expose fallback rate as metric
- Use structured output (response_format=json_schema) where available
- Add tenacity retry on LLM 429/503 per concept (not global failure)
- Exit criterion: Fallback rate <5% on test corpus; every fallback logs a warning

### 0.6 — Fix README: distinguish implemented from planned
- Sources table: "Implemented" column (arXiv, PubMed) vs "Planned" column (ACM, patents, SO, HN, GitHub)
- Add explicit scope statement: English-language academic literature, post-1990, arXiv/PubMed domains
- Add "Out of scope in v1" section: tacit knowledge, non-English literature, pre-digital records
- Exit criterion: No false capability claims in README or ARCHITECTURE.md

---

## Phase 1 — Honest Foundations (Weeks 3-6)

**Goal:** A stable knowledge graph, a real importance signal, and a collision detector that
fires only on actual re-derivation events.

### 1.1 — Stable concept identity + deduplication (Priority 3)
- Replace SHA1(label) concept IDs with UUID5 of embedding bytes
- Add dedup pass: cosine_sim > 0.92 against existing nodes → merge, not insert
- Accumulate citation_count_total and importance_weight across runs (not per-batch reset)
- Fix first_seen to use earliest published_at across ALL batches (not current batch)
- Use cluster centroid mean as concept embedding (not LLM-generated description embedding)
- Exit criterion: Re-running ingestion on identical input produces identical graph (idempotency test)

### 1.2 — LLM intent classifier for collision detection (Priority 4)
- Add collision/intent.py: classify query intent before embedding
- Only exploring and implementing pass to detection; others return no-op CollisionReport
- Replace multiplicative composite score with additive:
  score = (0.4 * intent_confidence) + (0.35 * similarity) + (0.25 * absorption_score)
- Rename decay_score to absorption_score everywhere (naming clarity)
- Exit criterion: Zero false-positive alerts on test set of 20 "citing" queries

### 1.3 — FAISS ANN index for collision detection
- Build FAISS IVFFlat index at startup from all concept embeddings
- Update index incrementally on new concept insertion
- Replace O(N) numpy scan with FAISS.search(top_k=20)
- Exit criterion: detect() call < 50ms on a 10K-node graph

### 1.4 — Multi-concept extraction per cluster
- Switch from formula-based n_clusters to HDBSCAN (min_cluster_size=3) or
  agglomerative with distance_threshold (natural cluster count from data)
- Change extraction prompt: "up to N distinct concepts" instead of "the single core concept"
- Return list[ConceptNode] per cluster, not single ConceptNode
- Sample docs by centroid proximity, not first-6 insertion order
- Exit criterion: A cluster of papers on 3 distinct sub-topics produces 2-3 nodes, not 1

### 1.5 — Collision feedback loop
- Log every CollisionReport to feedback SQLite table with UUID and timestamp
- Expose thumbs-up/down endpoint per report_id
- Aggregate feedback weekly; surface precision/recall trend as system health metric
- Exit criterion: Feedback table exists; every CollisionReport has a retrievable UUID

### 1.6 — Ground truth validation harness (Priority 5)
- Pull 2000 concepts from OpenAlex published 1990-2005
- Compute 3 decay signals at 2015 snapshot; compare to 2025 citation rates
- Label decayed (>70% drop) / stable (<20% drop); exclude ambiguous middle
- Run current model; measure AUROC; train logistic regression for empirical weights
- Exit criterion: AUROC measured and documented. Weights updated if AUROC >= 0.70.
  If AUROC < 0.70: decay alerts disabled in UI pending model fix.

### 1.7 — citation_decay_v2: 3-window trajectory
- Replace snapshot ratio with 3-window (citations_recent 0-3yr, citations_mid 3-6yr, peak)
- Add revival signal: recovering = (recent > mid * 1.1) → suppress alert (discount score by 0.4)
- Add SYNTHESIS_HORIZONS dict: cs=7yr, biology=15yr, physics=20yr, default=12yr
- Exit criterion: Plateau concept (stable 40% of peak) and declining concept (40% still falling)
  score differently; revival signal suppresses alert correctly on test cases

### 1.8 — Define and implement delivery contract for alerts
- Decide delivery mechanism before Phase 2 (webhook / inline editor / email / Slack)
- CollisionReport requires a configured delivery target before alerts fire to users
- Alert without delivery target: logs only, no user-facing output
- Exit criterion: At least one delivery channel implemented and tested end-to-end

---

## Phase 2 — Production-Ready Pipeline (Weeks 7-12)

**Goal:** Corpus honest about its coverage, translation that is grounded, infrastructure
that survives real load.

### 2.1 — Swap embedding model for scientific literature
- Default EMBED_MODEL to allenai/specter2_base for arXiv/PubMed sources
- Keep all-MiniLM-L6-v2 as option for non-scientific sources
- Document model choice in config as first-class decision, not buried env var
- Exit criterion: Homonym disambiguation test passes (biology "prion" vs PL-theory "prion")

### 2.2 — CrossRef adapter + OpenAlex adapter
- CrossRef: 130M+ DOIs across all disciplines; free API; no institutional access required
- OpenAlex: 250M+ works; multilingual metadata; highest single-source coverage expansion
- Both follow IngestedDocument schema; Semantic Scholar enrichment applies
- Exit criterion: Domains not in arXiv/PubMed (economics, law, education) have retrievable papers

### 2.3 — Full-text ingestion where available
- arXiv: ar5iv HTML endpoint (https://ar5iv.org/abs/{arxiv_id}) for full paper text
- PubMed Central: efetch rettype=full for open-access papers
- IngestedDocument.body populated where available; abstract fallback otherwise
- Exit criterion: body field non-empty for >40% of arXiv papers

### 2.4 — Translation: retrieval augmentation + graph context injection
- Before LLM call: query graph for concepts connected to target concept in to_field
- Retrieve 5 actual cross-domain papers from corpus related to the concept
- Inject retrieved context into prompt as grounding
- Add practitioner_context: str to TranslationRequest for caller-injected domain vocabulary
- Add feedback: str for expert corrections from prior runs
- Exit criterion: Translation prompt contains at least 2 retrieved real papers before LLM call

### 2.5 — Translation: multi-pass + confidence scoring
- Add self-critique pass: "identify 3 ways this analogy might fail"
- Add revision pass incorporating self-critique
- Add second LLM pass producing confidence_score: float (0-1 structural validity)
- Exit criterion: confidence_score populated and correlates with human ratings on 20-item golden set

### 2.6 — Temporal ingestion (nightly scheduler)
- arXiv RSS feed per category for new papers
- PubMed reldate filter for papers published since last run
- APScheduler job: nightly at 02:00 UTC
- Exit criterion: Papers published today appear in corpus within 24 hours without manual run

### 2.7 — Retraction tracking
- PubMed: check PublicationType for "Retracted Publication" at ingest time
- arXiv: check comment field for withdrawal notice
- Add is_retracted: bool = False to IngestedDocument
- Concept nodes flagged when source papers retracted
- Exit criterion: Wakefield MMR paper (pmid 9500320) ingested with is_retracted=True

### 2.8 — Replace NetworkX with Kuzu
- Kuzu: embedded, no server, Cypher query language, fast traversal at scale
- Migrate ConceptNode and edge schema; keep NetworkX for <10K node dev mode
- Exit criterion: Graph traversal queries that take >1s in NetworkX complete in <100ms in Kuzu at 50K nodes

---

## Phase 3 — Data Flywheel + Commercial (Weeks 13-20)

**Goal:** The system gets better as more people use it.
The only durable moat is user working context. Semantic Scholar can replicate the static
analysis. They cannot replicate intent data — it violates their academic freedom principles.

### 3.1 — Practitioner profile builder
- Users describe what they are building in natural language
- REMNANT maps description to watched concepts in the graph
- Automatic alerts when new papers match a watched concept
- Working context stored per user; never shared; used only for alert personalization
- Exit criterion: User who declares "I am building distributed consensus" auto-receives
  alerts on new papers in the consensus/Paxos/Raft cluster

### 3.2 — Internal enterprise collision detection (Pivot A wedge)
Per business-gtm GTM Pivot A: highest-probability revenue path.
- Target: Series B-D tech companies, 100-2000 engineers
- Problem: "Three teams built auth from scratch last year"
- Ingest internal docs (GitHub Issues, Confluence, Jira, Slack with consent)
- Detect: Team A approaching a solution Team B already shipped
- Buying committee: CTO / VP Engineering; 30-90 day sales cycle; $500-$2000/seat/year
- Exit criterion: Internal ingestion adapter exists; one pilot customer onboarded

### 3.3 — Falsifiable academic demo
Per business-gtm F3: MVP must be falsifiable. Pharma ROI attribution is not.
- Run REMNANT on distributed systems papers 1970-2000
- Demonstrate it surfaces known cross-domain rediscoveries (vector clock / Lamport timestamp)
- Show a naive Semantic Scholar search would not have surfaced it
- This is the seed-stage proof point, not "one avoided pharma trial"
- Exit criterion: Demo runs reproducibly; surfaces at least 3 documented historical rediscoveries

### 3.4 — Feedback-driven threshold calibration
- Aggregate collision feedback from Phase 1 feedback loop
- Weekly recalibration of collision threshold based on accumulated ratings
- Publish precision/recall metrics as system health dashboard
- Exit criterion: Threshold is derived from measured feedback data, not a magic number

### 3.5 — Bidirectional translation
- Add TranslationRequest.bidirectional: bool = False
- When True: run both A-to-B and B-to-A; return BidirectionalTranslationResult
- "What B knows that A could use" section in bidirectional result
- Exit criterion: Bidirectional result returns non-trivial reverse insights for physics to org-behavior

### 3.6 — SSRN + language support
- SSRN adapter: economics, law, finance, social science (free metadata API)
- Language detection on ingested documents (langdetect or fastText)
- NLLB-200 for non-English concept extraction at abstract level
- Exit criterion: French and German SSRN papers produce valid ConceptNodes; findable via English query

---

## Milestone: Bacteriophage Example as Phase 3 Validation Target

The README uses Soviet phage therapy as the canonical civilizational memory failure.
That example requires:
- Non-English source coverage (Russian medical journals): Phase 3.6
- Pre-1990 literature (not in current adapters): additional historical sources beyond Phase 3
- Cross-domain detection across medicine, microbiology, applied therapy: Phase 3 concept graph

This milestone is the north star. It is not the MVP. The Phase 0 MVP makes no claim to this
capability. Phase 3 should be validated against it. The bacteriophage example belongs on the
roadmap as a milestone, not in the README as a current capability.

---

## What Success Looks Like at Each Phase

| Phase | What the system honestly does |
|---|---|
| Phase 0 complete | Ingests arXiv + PubMed with real citation counts. Translation does not hallucinate citations. Decay scores computed but not user-facing (unvalidated). README makes no false claims. |
| Phase 1 complete | Stable idempotent knowledge graph. Collision detection fires only on exploring/implementing intent. Decay model AUROC measured; weights empirically calibrated. Alerts delivered via one configured channel. |
| Phase 2 complete | Corpus covers 130M+ DOIs via CrossRef/OpenAlex. Full text for open-access papers. Translation grounded and confidence-scored. Retracted papers flagged. System updated nightly. |
| Phase 3 complete | Data flywheel operational. Internal enterprise pilot live. Falsifiable academic demo reproducible on historical corpus. Non-English concepts reachable. Threshold calibrated from real feedback. |
