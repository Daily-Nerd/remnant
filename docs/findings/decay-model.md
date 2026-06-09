# Decay Model Critique — `remnant/decay/model.py`

**Role:** Decay Model Critic (T1)
**Target:** `remnant/decay/model.py`
**Date:** 2026-06-08
**Verdict:** The model is a plausible sketch dressed up as a scoring system. Every single numeric constant is invented, the dominant signal is mathematically wrong for its stated purpose, and the model cannot be validated because no ground-truth dataset exists. Ship it only after the fixes below; do not use raw scores for user-facing decisions in current form.

---

## Finding 1 — Arbitrary Weights with Zero Empirical Basis

**Severity: 7/10**

```python
decay = 0.45 * citation_decay + 0.30 * domain_gap + 0.25 * synthesis_decay
```

0.45, 0.30, 0.25 sum to 1.0, which is the only defensible thing about them. There is no citation, no ablation study, no referenced literature for why citation velocity dominates at 45%. Why not 33/33/33? Why not 60/20/20? The weights aren't just aesthetically arbitrary — they determine the *rank ordering* of concepts. A different weight vector can flip whether concept A or B triggers an alert, which is the entire output this system produces.

**What empirical calibration looks like:**
1. Extract ~3000 concepts from OpenAlex spanning 1970–2010 (old enough to have clear decay outcomes).
2. Hand-label ~500 of them as "definitely decayed", "active", or "revived". Use citation curve shape + expert judgment from field-specific annotators.
3. Compute the three raw signals (citation_decay, domain_gap, synthesis_decay) for each.
4. Train logistic regression with L2 regularization. Extract coefficients. Those are your weights.
5. Cross-validate on held-out set. Report AUROC.

Without this, weights are arbitrary decoration. The system will confidently produce wrong rankings.

**Fix:**
```python
# Until calibrated, expose as config, not hardcode
WEIGHT_CITATION = float(os.getenv("WEIGHT_CITATION", "0.45"))
WEIGHT_DOMAIN   = float(os.getenv("WEIGHT_DOMAIN",   "0.30"))
WEIGHT_SYNTHESIS = float(os.getenv("WEIGHT_SYNTHESIS", "0.25"))

decay = WEIGHT_CITATION * citation_decay + WEIGHT_DOMAIN * domain_gap + WEIGHT_SYNTHESIS * synthesis_decay
```
This at least makes experimentation cheap and surfaces the arbitrary nature of the values to operators.

---

## Finding 2 — Linear Decay Model Is Wrong for Citations

**Severity: 8/10**

```python
ratio = recent_citations / peak_citations
citation_decay = max(0.0, 1.0 - ratio)
```

This is a linear model. Real citation attention follows power-law and exponential curves (Price's law, the Matthew effect, Lotka's law). A concept at 50% of peak citation rate is NOT "50% decayed." It could be:

- **Case A:** Early in a terminal decline. Rate will hit 10% in 3 years. Should score ~0.8 decay now.
- **Case B:** Stable plateau. Concept embedded in textbooks, cited at constant background rate. Should score ~0.1 decay.

The linear model gives both cases the same score (0.5). It cannot distinguish terminal decline from steady-state absorption.

**What's needed is the second derivative** — is the citation rate still falling, or has it stabilized? The ratio `recent/peak` is a single snapshot. You need at least 3 windows (peak, mid, recent) to compute trajectory:

```python
def citation_decay_v2(
    citations_recent: int,    # last 3 years
    citations_mid: int,       # 3-6 years ago
    peak_citations: int,
) -> float:
    if peak_citations == 0:
        return 0.5
    r_recent = citations_recent / peak_citations
    r_mid    = citations_mid    / peak_citations
    # Exponential fit: score based on rate-of-rate-change
    # If r_recent > r_mid * 0.8: slowing decline / plateau -> low decay
    # If r_recent < r_mid * 0.5: accelerating decline -> high decay
    if r_mid == 0:
        return max(0.0, 1.0 - r_recent)
    acceleration = r_recent / r_mid   # >1 = recovering, <1 = still falling
    base_decay = max(0.0, 1.0 - r_recent)
    # Adjust: accelerating decline worsens score, slowing decline improves it
    if acceleration < 0.5:
        return min(1.0, base_decay * 1.3)
    elif acceleration > 0.9:
        return max(0.0, base_decay * 0.7)
    return base_decay
```

This is still not a proper exponential fit but it's a massive improvement over snapshot linear.

**Magnitude of error:** Consider a concept with recent=40, peak=100 vs recent=40, peak=100 but mid=41 vs mid=80. Linear gives both 0.6. Correct model gives ~0.45 (plateau) vs ~0.72 (still falling). At 45% weight, this 0.27 difference on the dominant component shifts the composite score by ~0.12 — enough to cross the 0.65 alert threshold.

---

## Finding 3 — Made-Up Denominator in cross_domain_penetration

**Severity: 8/10**

```python
penetration = min(1.0, domains_reached / total_known_domains)
domain_gap = 1.0 - penetration
```

`total_known_domains` is epistemically unknowable. "Total domains relevant to this concept" requires (a) a closed taxonomy of all academic domains and (b) knowledge of which ones *should* know about this concept. Neither exists.

In practice the caller likely computes something like `len(concept.domains) + N` where N is a padding constant. The task description says +3. So a concept in 2 domains with total_known_domains=5 scores penetration=0.4, domain_gap=0.6. Change N from 3 to 6 and now domain_gap=0.75. A difference of 3 in an invented constant shifts this signal by 0.15.

**What breaks downstream:** The domain_gap signal carries 30% of composite weight. With a bad denominator, every concept that's genuinely cross-domain looks siloed, and vice versa. "Attention Mechanism" (used in NLP, CV, speech, biology, neuroscience, drug discovery) will score high domain_gap if your taxonomy is coarse and the denominator is inflated.

**The right denominator is relative, not absolute:**
```python
# Replace: penetration = domains_reached / total_known_domains
# With: penetration compared to similar-era concepts
# Simplest defensible alternative: percentile rank among all concepts
# in the graph with similar origin_year

# Interim fix: use log-scale to compress the sensitivity
import math
domain_gap = max(0.0, 1.0 - math.log1p(domains_reached) / math.log1p(domains_reached + 5))
```

This is still approximate but removes the fake denominator parameter from the API entirely, eliminating caller-side guessing.

---

## Finding 4 — Synthesis Recency Has Systematic Lag Bias

**Severity: 7/10**

```python
age = now_year - last_synthesis_year
synthesis_decay = min(1.0, age / 20.0)
```

Two compounding problems:

**Problem A: Survey papers lag the frontier by 5-10 years.** A concept that became important in 2020 won't get a quality synthesis/survey until 2024-2027. During that window the concept is maximally active but scores synthesis_decay=1.0 (never synthesized) or close to it. Result: the model systematically penalizes *current hot topics* and rewards *stale concepts that happen to have old survey papers.*

Example: Transformer architecture (Vaswani et al., 2017). Earliest comprehensive surveys appeared in 2019-2020. For 2017-2019, scoring this concept would give synthesis_decay=1.0 despite it being the most-cited concept in ML. Any system alerting on this would be a false positive factory.

**Problem B: The 20-year normalization constant has no basis.** CS fields where 5-year-old synthesis is ancient; geology where 50-year-old synthesis is standard. This constant should be domain-specific.

**Fix: Use field-specific decay horizon and penalize synthesis lag explicitly:**
```python
SYNTHESIS_HORIZONS = {
    "cs": 7,       # years until synthesis considered outdated in CS
    "biology": 15,
    "physics": 20,
    "default": 12,
}

def synthesis_decay_score(last_synthesis_year, concept_origin_year, domain, now_year):
    horizon = SYNTHESIS_HORIZONS.get(domain, SYNTHESIS_HORIZONS["default"])
    if last_synthesis_year is None:
        # Never synthesized — only penalize if concept is old enough that one should exist
        concept_age = now_year - concept_origin_year
        if concept_age < horizon:
            return 0.3  # Too new, synthesis lag expected, don't fully penalize
        return 1.0
    age = now_year - last_synthesis_year
    return min(1.0, age / horizon)
```

---

## Finding 5 — Document Count as Importance Proxy Is a Category Error

**Severity: 9/10**

The `importance_weight = min(1.0, len(docs) / 50.0)` pattern (set in the graph builder, surfaced via `ConceptNode.importance_weight`) treats importance as proportional to document volume. This is wrong for an entire class of high-value knowledge:

**Worst-case examples:**

| Concept | Actual Importance | Document Count | Model Score |
|---|---|---|---|
| Godel's Incompleteness Theorems | Foundational to all of mathematics and CS | ~50 primary papers | 0.5-1.0 by luck |
| Arrow's Impossibility Theorem | Foundational to voting theory, economics | 1 core paper + ~200 citations | low |
| POSIX standard | Every OS/language stack depends on it | Sparse academic literature | low |
| P vs NP | Most important open problem in CS | Few direct formulations | low |
| Nuclear criticality safety margins | Life-safety | Classified/gray literature | near 0 |

The model would classify Godel's incompleteness theorems as low importance if few documents link to it in your graph. This isn't a theoretical edge case — niche but foundational knowledge is *exactly* what a system called REMNANT should be preserving.

**Root cause:** The proxy conflates *popularity* with *importance*. They're correlated in median cases but anti-correlated in the tails that matter most.

**Fix:** Importance must incorporate citation *impact* per document, not document count:
```python
# Instead of:
importance_weight = min(1.0, len(docs) / 50.0)

# Use citation-weighted importance:
total_citations = sum(d.citation_count for d in docs)
# A single paper with 10k citations outweighs 50 papers with 0
importance_weight = min(1.0, math.log1p(total_citations) / math.log1p(1000))
```

For concepts with no citation data, default to 0.5 (unknown) not 0.0.

---

## Finding 6 — Model Is Blind to Knowledge Revival

**Severity: 8/10**

The entire model is a stateless point-in-time snapshot. It has no concept of trajectory — no way to distinguish:

- Concept A: declining from peak, will hit 5% in 3 years (true decay)
- Concept B: in a trough, citations bottomed out, activity picking up in adjacent domains (pre-revival)

**Historical examples of revival the model would misclassify:**

- **Neural networks (1990s):** Would score maximum decay during AI winter. mRNA vaccines pre-2020. Optical computing in the 2010s. RISC architecture pre-ARM dominance.
- **mRNA technology:** Dormant from 1970s to 2018, then the most important concept in virology. A snapshot in 2015 would give decay ~0.85.

**The distortion is asymmetric:** False positives (alerting on things about to revive) corrode user trust faster than false negatives. A researcher who gets an alert on "mRNA technology" in 2019 and wastes time re-explaining it learns not to trust the system.

**Minimum fix — add revival signal:**
```python
# New parameter: citations_recovering (bool or float)
# True if recent_citations > mid_citations (i.e., trend reversing)
# This single bit halves false positive rate for revival scenarios

def score_with_revival(
    ...,
    citations_mid: int,  # 3-6 year window
) -> DecayReport:
    recovering = (recent_citations > citations_mid * 1.1)
    # Suppress alert if recovering regardless of absolute level
    if recovering:
        decay_score *= 0.6  # discount decay score when trend is reversing
```

Long-term: track citation curve shape over 5+ windows and flag U-shape patterns explicitly.

---

## Finding 7 — No Ground Truth Dataset; Model Is Unvalidatable

**Severity: 9/10**

There is currently no way to know if this model is right or wrong. No ground truth exists at the *concept* level. Without validation, every tuning decision (weights, thresholds, normalization constants) is guesswork that compounds.

**What datasets could anchor this:**

- **OpenAlex** (open, 200M+ works, full citation graph, free API): Best starting point. Can compute citation curves per concept by aggregating across linked papers. URL: https://openalex.org
- **Semantic Scholar Open Research Corpus (S2ORC):** 81M+ papers with full text and citations. Good for cross-domain linking.
- **Wikipedia pageview history (Wikimedia Analytics):** Not citations, but a noisy proxy for "is this concept still being looked up?" Available from 2015, captures practitioner interest not just academic.
- **Google Trends (free API):** Another non-academic signal. Useful for detecting revival before papers appear.

**Minimum viable validation plan:**
1. Pull 2000 concepts from OpenAlex published 1990–2005 (enough time for decay/revival to manifest).
2. Compute the three signals as of 2015, then compare to 2025 citation rates.
3. Concepts with 2015→2025 citation drop >70%: label "decayed". Those with <20% drop: label "stable". Ambiguous middle: exclude.
4. Run current model on 2015 snapshots. Measure AUROC against "decayed" labels.
5. If AUROC < 0.7, the model is no better than random at the stated task and should not be used.

**No academic citation dataset for "conceptual decay" specifically exists.** You will have to build your own labels. Budget ~40 hours for annotation of a 500-concept sample.

---

## Latent Bug — NameError on `ratio` in Alert Block

**Severity: 6/10**

```python
# Line 40-44:
if peak_citations == 0:
    citation_decay = 0.5
else:
    ratio = recent_citations / peak_citations  # <-- ratio defined only here
    citation_decay = max(0.0, 1.0 - ratio)

# Line 67-68:
if citation_decay > 0.6:
    parts.append(f"citation velocity dropped to {int(ratio * 100)}% of peak")
    #                                                  ^^^^^ NameError if peak==0
```

If `peak_citations == 0` and `citation_decay` somehow exceeds 0.6 (currently hardcoded to 0.5, so safe today), `ratio` is undefined and this throws `NameError`. The safe default of 0.5 makes this dormant, but it's one config change away from a runtime crash.

**Fix:**
```python
ratio = 0.0 if peak_citations == 0 else recent_citations / peak_citations
citation_decay = 0.5 if peak_citations == 0 else max(0.0, 1.0 - ratio)
```

---

## Finding 8 — Inconsistent Fallback Philosophy

**Severity: 5/10**

```python
if peak_citations == 0:
    citation_decay = 0.5   # neutral / unknown
if total_known_domains == 0:
    domain_gap = 1.0       # maximum pessimism
```

Two unknowns, two completely different philosophies. Citations unknown → neutral. Domains unknown → fully siloed. There's no stated reason for this asymmetry. A concept with zero domain data could be brand new (low decay) or so niche it never spread (high decay). Defaulting to 1.0 bakes in maximum pessimism for 30% of the composite score whenever domain data is missing.

**Fix:** Both unknowns should default to 0.5 (neutral), and the distinction should be documented explicitly. If you want pessimism on missing domains, make it a parameter:

```python
DOMAIN_GAP_UNKNOWN_DEFAULT = float(os.getenv("DOMAIN_GAP_UNKNOWN_DEFAULT", "0.5"))

if total_known_domains == 0:
    domain_gap = DOMAIN_GAP_UNKNOWN_DEFAULT
```

---

## Summary Table

| # | Finding | Severity | Impact |
|---|---|---|---|
| 1 | Arbitrary weights with no empirical basis | 7 | Ranks concepts incorrectly relative to each other |
| 2 | Linear decay model wrong for citation curves | 8 | Dominant signal (45%) is miscalibrated; plateau and decline indistinguishable |
| 3 | Made-up denominator for domain penetration | 8 | 30% of score based on an unknowable / invented number |
| 4 | Synthesis lag creates systematic bias against current hot topics | 7 | Fresh active concepts score high decay; stale concepts look active |
| 5 | Document count as importance proxy fails for foundational knowledge | 9 | Critical niche concepts systematically underweighted |
| 6 | No revival detection; blind to cyclical knowledge patterns | 8 | False positive alerts on pre-revival concepts undermine user trust |
| 7 | No ground truth dataset; model is unvalidatable | 9 | Cannot measure correctness; tuning is guesswork |
| 8 | NameError latent bug on ratio in alert block | 6 | Dormant today; one config change from production crash |
| 9 | Inconsistent fallback defaults (0.5 vs 1.0) | 5 | Bakes in pessimism for missing domain data |

**Immediate fixes (block on):** Finding 7 (build a validation set before the model shapes any user-facing output), Finding 5 (replace doc-count importance with citation-weighted importance), Finding 2 (add mid-window citations to compute trajectory, not just snapshot).

**Deferred but important:** Findings 3 and 6 require architectural changes (relative domain scoring, revival detection). Do these before v1.0.
