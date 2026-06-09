# Corpus & Ingestion Critic — What REMNANT Is Structurally Blind To

**Role:** Corpus & Ingestion Critic
**Target:** `remnant/ingestion/` + corpus design assumptions
**Date:** 2026-06-08
**Verdict:** The civilizational memory claim cannot be supported by this ingestion design. 7 of 12 findings are severity 7+.

---

## FINDING 1 — Citation Count Is Always Zero. The Entire Decay Mechanism Is Broken.

**Severity: 10/10 — SHOWSTOPPER**

This is not a design critique. This is a bug that silently invalidates the core value proposition.

`IngestedDocument.citation_count` defaults to 0. Neither `arxiv.py` nor `pubmed.py` populates it. Search the codebase: there is no assignment to `citation_count` anywhere. The arXiv Python library exposes `result.primary_category`, `result.categories`, but not citation counts (arXiv has no citation data in its API). PubMed's E-utilities similarly does not return citation counts via esearch/efetch.

The consequence: `ConceptNode.importance_weight` in `concept.py` is calculated as `min(1.0, len(docs) / 50.0)` — it's cluster size divided by 50, not citations. A concept that appears in a query returning 50 results gets weight 1.0. A concept queried with max_results=10 gets weight 0.2. This is an artifact of query parameters, not real-world importance.

Decay modeling (`decay/scorer.py`) is downstream of importance_weight and citation_velocity. Both are either zero or miscalculated. The system cannot generate meaningful decay scores. The flagship promise — "flags when important ideas go dark" — has no data foundation.

**What this does to the civilizational memory claim:** REMNANT cannot tell you a concept is fading. It cannot tell you a concept was ever important. All decay scores are noise.

**Fix required:** Citation data requires external sources. Semantic Scholar Open API returns citation counts and velocity. OpenCitations provides free citation graph data. iCite from NIH covers PubMed. None of these are free of lag, but they are real. The current approach pretends the data exists when it doesn't.

---

## FINDING 2 — Abstract-Only Ingestion, Then Truncated to 400 Characters

**Severity: 8/10**

`arxiv.py` line 37: `abstract=result.summary` — abstract only, no full text.
`pubmed.py` line 45: `rettype="abstract"` — explicit abstract-only fetch.
`concept.py` line 49: `abstract[:400]` — 400 character hard truncation.

The `body` field exists in `IngestedDocument` and is never populated by either adapter. It is a dead field.

A typical arXiv abstract is 150-250 words. 400 characters is approximately 60-80 words — not even the full abstract. The LLM concept extractor receives a snippet of a summary, not the methodology, not the experimental results, not the failure modes, not the nuance.

**What gets lost:**
- Boundary conditions and where the technique breaks
- Experimental parameters that determine whether results transfer
- Caveats and limitations authors bury in section 4
- The actual reproducible methodology
- Negative results (often only in the body)

A concept node labeled "Gossip Protocols" built from six 400-character abstract snippets is a label and a vibe, not a knowledge representation. The Translation Engine, which claims to express concepts for practitioners in another field, is translating summaries of summaries.

**Fix required:** arXiv provides full-text PDF links and HTML via arxiv-latex-cleaner or ar5iv. PubMed Central (PMC) provides full XML for open-access papers. The architecture should ingest full text where available, with abstract as fallback.

---

## FINDING 3 — Language Monoculture Breaks the Flagship Example

**Severity: 9/10**

The README and PITCH both cite bacteriophage therapy as the canonical example of civilizational memory failure: "standard Soviet medicine in the 1940s → invisible by 1960s → rediscovered in 2020."

Soviet medical literature from the 1940s was published in Russian: Zhurnal Mikrobiologii (Journal of Microbiology), Voprosy Virusologii, Georgian medical institute publications. This literature is not in PubMed (which covers English-language publications and selected international journals from roughly the 1960s onward). It is not in arXiv. It is not indexed anywhere REMNANT can reach.

REMNANT cannot index the bacteriophage therapy knowledge it uses as its primary motivating example. The example that justifies the system's existence is outside the system's corpus by design.

This is not just about Soviet medicine. ~60% of scientific literature is published in languages other than English. Chinese industrial standards (GB/T series), German engineering specifications (DIN norms), French agricultural research (INRAE), Japanese manufacturing standards (JIS) — all structurally invisible. The "~95% of human knowledge" figure in the task brief is directionally correct. Even if we restrict to formal scientific literature, the English-only bias excludes 40-60%.

**What this does to the civilizational memory claim:** The claim is specifically that REMNANT preserves civilization's memory. The corpus covers English-language academic science published after ~1990. That is a narrow slice of civilization. The rest of it — oral traditions, indigenous knowledge, pre-digital technical manuals, non-English scientific traditions, craft knowledge — does not exist to REMNANT.

**Fix required:** Crossref DOI metadata covers multilingual publications. OpenAlex includes non-English papers. Machine translation (DeepL, NLLB-200) can bridge language gaps for concept extraction. None of this is trivial, but the alternative is that the "civilizational" claim is false advertising.

---

## FINDING 4 — Domain Gap: REMNANT Cannot Cover Its Own Target Domains

**Severity: 9/10**

arXiv categories are: cs.*, math.*, physics.*, cond-mat.*, quant-ph, econ.* (added 2017), q-bio.*, stat.*
PubMed categories: biomedical, clinical, life sciences.

The seed corpus in `scripts/seed_corpus.py` includes "urban planning community displacement." There is no arXiv category for urban planning. There is no PubMed coverage of urban planning. Querying arXiv for "urban planning" returns papers from cs.CY (Computers and Society) and maybe econ.GN — academic papers about urban planning, not the planning literature itself.

Domains with zero or near-zero coverage in the current adapter set:
- Economics (beyond narrow quantitative econ)
- History
- Law and jurisprudence
- Urban and regional planning
- Engineering practice (vs. engineering science)
- Music theory
- Agriculture and agronomy
- Education research
- Psychology and social science
- Geology and earth science

The ROADMAP acknowledges this partially: "Multi-domain ingestion (CS + Biology + Physics + Economics)" in Phase 2. But the Phase 2 plan still only names sources that already exist (arXiv + PubMed). No new adapters for JSTOR, SSRN, Google Scholar, CrossRef, or domain-specific repositories are specified. The expansion plan is aspirational without a concrete source list.

**Fix required:** SSRN for economics/law/social science. JSTOR metadata API (with institutional access). CrossRef API covers 130M+ DOIs across all disciplines. ERIC for education. AGRICOLA for agriculture. Each requires a distinct adapter.

---

## FINDING 5 — The README Lists 7 Sources; 2 Exist As Code

**Severity: 8/10**

README claims: "Continuous indexing of arXiv, PubMed, ACM, patents, SO, HN, GitHub"

Code that exists: `ingestion/arxiv.py`, `ingestion/pubmed.py`

Code that does not exist: ACM adapter, patent adapter, Stack Overflow adapter, Hacker News adapter, GitHub adapter.

`SourceType` enum in `models.py` includes `HACKERNEWS` and `GITHUB` as declared types, but there is no code that ingests from either. The ARCHITECTURE.md lists "Hacker News (via Algolia API)" and "GitHub Issues/Discussions" as v0.1 sources. They are not implemented.

This is not a roadmap issue. The README presents these as current capabilities: "Continuous indexing of arXiv, PubMed, ACM, patents, SO, HN, GitHub." A reader of the README believes these sources are operational. They are not. Three of the five planned v0.2+ sources (ACM, IEEE, USPTO) are paywalled and require institutional access or licensing agreements that are not mentioned anywhere.

**Fix required:** README must distinguish implemented sources from roadmap sources. USPTO patent data is actually free via PatentsView and Google Patents Public Data on BigQuery. ACM and IEEE require licensing. This needs to be spelled out.

---

## FINDING 6 — No Retraction Tracking. REMNANT Will Surface Invalidated Knowledge.

**Severity: 8/10**

Neither adapter checks for retraction status. arXiv does not retract papers (it withdraws/replaces them, but the original entry remains accessible and is returned by search). PubMed tags retracted papers with "Retraction of Publication" publication type but this field is not checked or stored.

REMNANT will extract concept nodes from retracted papers. Those concept nodes will persist in the knowledge graph. The decay scoring will not distinguish "concept faded because it was wrong" from "concept faded because it was superseded." The collision detector will alert practitioners that they are "re-deriving" something whose foundational papers were retracted.

Real-world scope: approximately 10,000 papers are retracted per year across biomedical literature (Retraction Watch data). Many retracted papers have high citation counts before retraction — which makes them more likely to appear in REMNANT's corpus and more likely to generate high importance_weight scores. The most-cited retracted papers are the highest-risk entries in the corpus.

Example failure mode: Andrew Wakefield's MMR-autism paper (12,000+ citations, retracted 2010) would appear in REMNANT's corpus as a highly-cited concept node about "vaccine-autism link." A researcher working on vaccine communication would get a collision alert suggesting this "solved" concept is being re-derived. The system would recommend invalidated science as established knowledge.

**Fix required:** PubMed has a `RetractionOf` XML field and a `PublicationType` of "Retracted Publication." arXiv withdrawal/replacement is detectable via the `updated` field and comments. Retraction Watch maintains a public CSV database. These must be checked at ingest time and on periodic refresh.

---

## FINDING 7 — Pull-Only, Query-Driven Ingestion. No Continuous Monitoring.

**Severity: 6/10**

The ingestion model is: run a query, get up to max_results papers sorted by Relevance, done. There is no scheduler. There is no continuous monitoring. There is no push subscription.

Consequences:
1. The corpus is a static snapshot of the moment `seed_corpus.py` was run.
2. New papers are invisible until someone manually re-runs ingestion.
3. A breakthrough paper published today does not enter REMNANT until a human decides to update that query's results.
4. The decay model has no temporal update mechanism — it cannot detect that a concept is currently accelerating or decelerating because it only knows what was ingested at seed time.

arXiv supports RSS feeds per category (e.g. `https://arxiv.org/rss/cs.DC` for distributed computing). PubMed supports E-utilities with `reldate` filtering for new publications. These are free, lightweight, and would enable continuous monitoring. Neither is used.

**Fix required:** APScheduler is already in the ROADMAP Phase 3. But this should be Phase 1 — the decay model is meaningless without temporal data collection. At minimum, a nightly cron that fetches papers published since last run is required before any decay analysis can be considered valid.

---

## FINDING 8 — Tacit Knowledge: The Gap Is Not Acknowledged

**Severity: 7/10**

The PITCH explicitly frames REMNANT as preserving knowledge that "might as well not have been recorded." But the deeper problem — knowledge that was never recorded — is not addressed and not acknowledged.

The bacteriophage therapy example is a special case of a general failure: knowledge that lived in practice, not in papers. Georgian phage therapy worked because Georgian doctors knew how to do it — which strains, which concentrations, which delivery mechanisms. That knowledge was partially in papers but mostly in practitioner experience. The papers gave you the what; the tacit knowledge gave you the how.

This same gap exists in:
- Surgical technique (resident-to-attending transfer, not publications)
- Software architecture at scale (conference talks, tribal knowledge in companies)
- Materials science in manufacturing (process parameters not publishable for IP reasons)
- Agricultural practice (soil management, pest control in specific microclimates)
- Legal strategy (case outcomes don't capture the argumentation approach that worked)

REMNANT's architecture cannot help with any of this by design. That is a legitimate constraint. The problem is that none of the project documentation acknowledges this constraint. The civilizational memory claim implicitly includes tacit knowledge. A responsible version of this project would say: "We cover recorded, formalized, English-language academic knowledge. Tacit, practitioner, and non-Western knowledge is out of scope."

**Fix required:** Add an explicit "Out of Scope" section to ARCHITECTURE.md and README. The scope limitation does not kill the value proposition — it focuses it honestly.

---

## FINDING 9 — Citation Timing Gap: New Papers Are Invisible at Peak Value

**Severity: 7/10**

Finding 1 establishes that citation_count is always 0. This finding addresses the architectural problem even if citations were collected.

arXiv papers have 0 citations for months after posting. Citation data in Semantic Scholar lags 2-6 months. A paper that defines a new paradigm gets 0 citations for its first year — it looks like noise to any citation-based importance scoring. REMNANT would assign it low importance_weight. It would not appear in collision detection. It would not generate alerts.

This is the exact opposite of what a civilizational memory system needs to do. The highest value intervention is catching emerging knowledge before it decays, not after it has already been cited enough to look important. A system that requires citation momentum before surfacing knowledge cannot serve the early-detection function.

The PITCH's example of bacteriophage therapy illustrates this: the knowledge was in Soviet papers that never got Western citations. Citation count as an importance proxy would have ranked that knowledge as unimportant — confirming its invisibility rather than surfacing it.

**Fix required:** Importance signals need to include: semantic centrality in the concept graph (how many other concepts reference this one), structural novelty (embedding distance from existing nodes), and cross-domain appearance (same concept appearing in two fields independently). Citation count, if used at all, should be a secondary signal with a known lag correction.

---

## FINDING 10 — concept.py Samples Only 6 Documents From Any Cluster

**Severity: 5/10**

Line 49 in `concept.py`:
```python
snippets = "\n---\n".join(
    f"Title: {d.title}\nAbstract: {d.abstract[:400]}" for d in docs[:6]
)
```

A cluster of 100 semantically similar papers feeds only 6 to the LLM for concept extraction. The other 94 papers are not represented in the concept label or description. If the 6 sampled papers happen to be fringe applications of the concept rather than the core formulation, the concept node is mislabeled. The sampling is positional (first 6), not representative.

**Fix required:** Either use all docs with a summarization step first, or sample by semantic centrality (pick the 6 closest to the cluster centroid). The current approach is a lazy default that will produce systematic errors in concept labeling.

---

## FINDING 11 — HackerNews and GitHub Listed in SourceType But No Adapters

**Severity: 4/10**

Minor but symptomatic. `models.py` defines `SourceType.HACKERNEWS` and `SourceType.GITHUB`. Neither has an adapter. If something creates an `IngestedDocument` with `source=SourceType.HACKERNEWS`, the rest of the pipeline accepts it — but nothing creates such documents. Dead enum values in a model that will expand over time is a maintenance trap.

---

## FINDING 12 — NetworkX Is Not Civilizational-Scale Infrastructure

**Severity: 6/10**

"NetworkX in-memory graph + SQLite for persistence" (ARCHITECTURE.md).

NetworkX is a pure Python in-memory graph library. At 10,000 concept nodes with 100,000 edges, memory usage is ~1-2GB and traversal is slow. At 1,000,000 nodes (plausible for serious multi-domain coverage), it is unusable. SQLite adds persistence but not query performance — complex graph traversals across a SQLite-backed NetworkX graph at scale will be unusable.

This is a Phase 0 decision that will require full replacement in Phase 2-3. The system is being architected with placeholder infrastructure that cannot survive its own success. Neo4j, Kuzu, or even a purpose-built embedding store (Qdrant, Weaviate) would serve the semantic similarity queries that drive collision detection far better.

---

## Summary Table

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| 1 | citation_count always 0 — decay mechanism broken | 10 | Bug (confirmed) |
| 2 | Abstract-only, truncated to 400 chars | 8 | By design |
| 3 | English-only corpus breaks flagship bacteriophage example | 9 | By design |
| 4 | Target domains (urban planning, law, etc.) have no adapter | 9 | Gap |
| 5 | README claims 7 sources; 2 exist as code | 8 | False advertising |
| 6 | No retraction tracking — will surface invalidated knowledge | 8 | Missing |
| 7 | Pull-only ingestion, no continuous monitoring | 6 | Missing |
| 8 | Tacit knowledge gap not acknowledged | 7 | Documentation |
| 9 | New papers invisible at peak value (citation lag) | 7 | Architectural |
| 10 | Concept extraction samples only 6 of N docs | 5 | Implementation |
| 11 | Dead enum values (HN, GitHub) with no adapters | 4 | Minor |
| 12 | NetworkX won't scale to civilizational corpus | 6 | Technical debt |

---

## Realistic Corpus Roadmap

This is not the roadmap you want. It is the roadmap required to support the claims.

### Phase 0 (now): Fix the broken things

1. **citation_count**: Integrate Semantic Scholar API (`https://api.semanticscholar.org/graph/v1/paper/`) for citation counts. Free tier: 100 req/5 min. Add `semantic_scholar_id` to `raw_metadata`.
2. **Retraction tracking**: On ingest, check PubMed `PublicationType` for "Retracted Publication." For arXiv, check comment field for withdrawal notice. Add `is_retracted: bool = False` to `IngestedDocument`.
3. **Full text**: Add `fetch_full_text: bool = False` flag to adapters. arXiv full text via ar5iv HTML. PMC full text via efetch with `rettype=full`. Fall back to abstract when unavailable.
4. **Fix README**: Distinguish "implemented" from "planned" in the sources table.

### Phase 1 (weeks 1-4): Honest MVP

1. **Fix importance_weight**: Replace cluster-size heuristic with semantic centrality (average cosine similarity to cluster centroid).
2. **Add temporal ingestion**: Nightly fetch of papers published since last run using arXiv RSS and PubMed reldate. This is required before decay analysis means anything.
3. **Add CrossRef adapter**: CrossRef covers 130M+ DOIs across all disciplines, with citation data. Free API. This alone expands coverage to economics, social sciences, humanities.
4. **Scope statement**: Add an explicit scope/out-of-scope section to README and ARCHITECTURE.md. State that tacit knowledge, non-English knowledge, and pre-1990 grey literature are out of scope in v1.

### Phase 2 (weeks 5-8): Domain expansion

1. **SSRN adapter**: Economics, law, finance, social sciences. Free metadata API.
2. **Semantic Scholar as primary citation source**: Covers 200M+ papers across all fields with citation graphs. Replace arXiv/PubMed as primary sources; add them as providers within Semantic Scholar.
3. **OpenAlex adapter**: Fully open, 250M+ works, multilingual metadata, institutional affiliation data. The single highest-leverage source expansion available.
4. **Language detection + translation pipeline**: Identify non-English abstracts, apply NLLB-200 or DeepL for concept extraction. Store original language in metadata.

### Phase 3 (weeks 9-12): Production-honest

1. **Replace NetworkX**: Move to Kuzu (embedded, Cypher, fast) or Qdrant for embedding-based graph with semantic search.
2. **Citation velocity calculation**: With real citation data from Semantic Scholar/OpenCitations, implement the decay model as designed.
3. **Retraction Watch integration**: Periodic sync with Retraction Watch CSV (`retractionwatch.com/retraction-watch-database-user-guide`). Flag existing concept nodes whose source papers have been retracted.
4. **Multi-language concept nodes**: Concepts should carry source-language metadata and should be findable via queries in multiple languages.

---

## Bottom Line

REMNANT has a strong conceptual foundation and a broken implementation of its core mechanism. The decay scoring — the heart of the system — operates on data that is never collected (citation counts). The corpus coverage is too narrow to support the civilizational claim by roughly two orders of magnitude. The flagship example in the README is literally outside the system's reach.

None of this is unfixable. The fixes in Phase 0 above take days, not months. The gap between what REMNANT claims and what it currently does needs to close before any demo, any pitch, or any user sees this system.

Build what you claim, or claim what you build.
