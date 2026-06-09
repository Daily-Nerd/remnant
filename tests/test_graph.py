"""Tests for the knowledge graph."""
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from remnant.graph.knowledge_graph import KnowledgeGraph
from remnant.models import ConceptNode, DocumentNode, SourceType


@pytest.fixture
def graph(tmp_path):
    return KnowledgeGraph(tmp_path / "test.db")


def _concept(i: int = 0) -> ConceptNode:
    return ConceptNode(
        id=f"concept:{i}",
        label=f"Concept {i}",
        description=f"Description {i}",
        domains=["cs", "biology"],
        first_seen=datetime(2000, 1, 1, tzinfo=timezone.utc),
        last_cited=datetime(2020, 1, 1, tzinfo=timezone.utc),
        importance_weight=0.5,
        decay_score=0.3,
    )


def _doc(i: int = 0) -> DocumentNode:
    return DocumentNode(
        id=f"doc:{i}",
        source=SourceType.ARXIV,
        title=f"Paper {i}",
        url=f"https://arxiv.org/{i}",
        published_at=datetime(2015, 6, 1, tzinfo=timezone.utc),
    )


def test_upsert_and_retrieve_concept(graph):
    c = _concept(1)
    graph.upsert_concept(c)
    assert graph.get_concept("concept:1") is not None
    assert graph.get_concept("concept:1").label == "Concept 1"


def test_concept_count(graph):
    for i in range(5):
        graph.upsert_concept(_concept(i))
    assert graph.concept_count() == 5


def test_add_edge_and_query(graph):
    c = _concept(0)
    c2 = _concept(1)
    graph.upsert_concept(c)
    graph.upsert_concept(c2)
    graph.add_edge(c.id, c2.id, "RELATED_TO", weight=0.85)
    related = graph.related_concepts(c.id, min_weight=0.5)
    assert len(related) == 1
    assert related[0].id == c2.id


def test_persistence(tmp_path):
    db = tmp_path / "persist.db"
    g1 = KnowledgeGraph(db)
    g1.upsert_concept(_concept(42))
    # Re-open
    g2 = KnowledgeGraph(db)
    assert g2.get_concept("concept:42") is not None
