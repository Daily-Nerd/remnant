"""
Collision Detector — finds concepts a query is approaching.

Given any text input, embed it and find concept nodes in the graph
whose embeddings are semantically similar. High similarity + high decay
score = likely re-derivation in progress. Fire alert.
"""
from __future__ import annotations

import numpy as np

from remnant.config import COLLISION_SIMILARITY_THRESHOLD
from remnant.extraction.fingerprint import embed_one, batch_similarity
from remnant.graph.knowledge_graph import KnowledgeGraph
from remnant.models import CollisionCandidate, CollisionReport, ConceptNode


def detect(query: str, graph: KnowledgeGraph,
           top_k: int = 5) -> CollisionReport:
    """
    Detect concepts the query text is approaching.

    Args:
        query: Any text — a question, issue description, forum post, etc.
        graph: The populated KnowledgeGraph.
        top_k: Maximum candidates to return.

    Returns:
        CollisionReport with ranked candidates and optional top alert.
    """
    query_vec = embed_one(query)

    # Collect all concepts with embeddings
    concepts: list[ConceptNode] = []
    embeddings: list[list[float]] = []
    for c in graph.all_concepts():
        if c.embedding:
            concepts.append(c)
            embeddings.append(c.embedding)

    if not concepts:
        return CollisionReport(query=query, candidates=[], top_alert=None)

    matrix = np.array(embeddings, dtype=np.float32)
    similarities = batch_similarity(query_vec, matrix)

    # Score = similarity × decay_score × importance_weight
    candidates: list[CollisionCandidate] = []
    for i, concept in enumerate(concepts):
        sim = float(similarities[i])
        if sim < 0.40:
            continue
        relevance = sim * concept.decay_score * concept.importance_weight
        alert = sim >= COLLISION_SIMILARITY_THRESHOLD and concept.decay_score > 0.4

        summary = _build_summary(concept, sim, alert)
        candidates.append(CollisionCandidate(
            concept=concept,
            similarity=round(sim, 4),
            relevance_score=round(relevance, 4),
            alert=alert,
            summary=summary,
        ))

    candidates.sort(key=lambda c: c.relevance_score, reverse=True)
    top = candidates[:top_k]
    top_alert = next((c for c in top if c.alert), None)

    return CollisionReport(query=query, candidates=top, top_alert=top_alert)


def _build_summary(concept: ConceptNode, similarity: float, alert: bool) -> str:
    prefix = "⚠️  COLLISION DETECTED" if alert else "ℹ️  Related concept"
    domains = ", ".join(concept.domains[:3]) if concept.domains else "unknown domain"
    year = concept.first_seen.year if concept.first_seen else "unknown year"
    return (
        f"{prefix}: '{concept.label}' ({domains}, established ~{year}). "
        f"Similarity: {similarity:.0%}. Decay score: {concept.decay_score:.2f}. "
        f"{concept.description[:200]}..."
    )
