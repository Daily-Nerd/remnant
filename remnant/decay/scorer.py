"""Batch scorer — runs decay model over all concepts in the graph."""
from __future__ import annotations

from remnant.graph.knowledge_graph import KnowledgeGraph
from remnant.models import DecayReport
from .model import score


def run_all(graph: KnowledgeGraph) -> list[DecayReport]:
    """
    Score every concept in the graph.
    Returns reports sorted by decay_score descending (most decayed first).
    """
    reports: list[DecayReport] = []
    for concept in graph.all_concepts():
        # Count documents expressing this concept (proxy for citations)
        doc_edges = [
            (u, v, d) for u, v, d in graph.G.in_edges(concept.id, data=True)
            if d.get("kind") == "EXPRESSES"
        ]
        all_docs = len(doc_edges)
        recent_docs = sum(
            1 for _, _, d in doc_edges
            if d.get("meta", {}).get("year", 0) >= 2021
        )
        domains = concept.domains
        report = score(
            concept=concept,
            recent_citations=recent_docs,
            peak_citations=max(1, all_docs),
            domains_reached=len(domains),
            total_known_domains=max(1, len(domains) + 3),  # assume 3 undiscovered
            last_synthesis_year=concept.peak_citation_year,
        )
        reports.append(report)

    return sorted(reports, key=lambda r: r.decay_score, reverse=True)
