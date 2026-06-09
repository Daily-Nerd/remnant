"""
Decay scoring model.

decay_score = weighted combination of:
  - citation_velocity   (how fast is attention decelerating)
  - cross_domain_gap    (hasn't crossed domain boundaries)
  - synthesis_recency   (no recent review/synthesis paper)
"""
from __future__ import annotations

from datetime import datetime, timezone

from remnant.config import DECAY_ALERT_THRESHOLD
from remnant.models import ConceptNode, DecayReport


def score(concept: ConceptNode,
          recent_citations: int,
          peak_citations: int,
          domains_reached: int,
          total_known_domains: int,
          last_synthesis_year: int | None) -> DecayReport:
    """
    Compute decay score for a concept.

    Args:
        concept: The ConceptNode to score.
        recent_citations: Citations in the last 3 years.
        peak_citations: Citations at peak (best 3-year window).
        domains_reached: How many distinct fields have cited this concept.
        total_known_domains: Denominator for cross-domain penetration.
        last_synthesis_year: Year of last review/synthesis paper (None if never).

    Returns:
        DecayReport with composite decay_score in [0, 1].
    """
    now_year = datetime.now(timezone.utc).year

    # 1. Citation velocity decay: 1.0 = fully decayed, 0.0 = still at peak
    if peak_citations == 0:
        citation_decay = 0.5
    else:
        ratio = recent_citations / peak_citations
        citation_decay = max(0.0, 1.0 - ratio)

    # 2. Cross-domain penetration: 1.0 = only in one silo, 0.0 = everywhere
    if total_known_domains == 0:
        domain_gap = 1.0
    else:
        penetration = min(1.0, domains_reached / total_known_domains)
        domain_gap = 1.0 - penetration

    # 3. Synthesis recency: 1.0 = never synthesized, 0.0 = synthesized this year
    if last_synthesis_year is None:
        synthesis_decay = 1.0
    else:
        age = now_year - last_synthesis_year
        synthesis_decay = min(1.0, age / 20.0)   # 20 years → fully decayed

    # Composite (weighted)
    decay = 0.45 * citation_decay + 0.30 * domain_gap + 0.25 * synthesis_decay

    alert = decay >= DECAY_ALERT_THRESHOLD
    reason = ""
    if alert:
        parts = []
        if citation_decay > 0.6:
            parts.append(f"citation velocity dropped to {int(ratio * 100)}% of peak")
        if domain_gap > 0.7:
            parts.append(f"only {domains_reached}/{total_known_domains} domains aware")
        if synthesis_decay > 0.8:
            yr = last_synthesis_year or "never"
            parts.append(f"last synthesis: {yr}")
        reason = "; ".join(parts)

    updated = concept.model_copy(update={"decay_score": round(decay, 4)})

    return DecayReport(
        concept=updated,
        citation_velocity=round(1.0 - citation_decay, 4),
        cross_domain_penetration=round(1.0 - domain_gap, 4),
        recency_of_synthesis=round(1.0 - synthesis_decay, 4),
        decay_score=round(decay, 4),
        alert=alert,
        alert_reason=reason,
    )
