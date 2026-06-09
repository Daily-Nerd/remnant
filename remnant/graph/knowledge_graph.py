"""
In-memory knowledge graph (NetworkX) with SQLite persistence.

Nodes: ConceptNode, DocumentNode
Edges: EXPRESSES (doc→concept), RELATED_TO (concept↔concept), TRANSLATED_FROM (concept→concept)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterator

import networkx as nx

from remnant.models import ConceptNode, DocumentNode


class KnowledgeGraph:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.G: nx.DiGraph = nx.DiGraph()
        self._init_db()
        self._load_from_db()

    # ── DB init ───────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS concepts (
                    id TEXT PRIMARY KEY,
                    data JSON NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    data JSON NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS edges (
                    src TEXT NOT NULL,
                    dst TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    meta JSON,
                    PRIMARY KEY (src, dst, kind)
                );
                CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
                CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
            """)

    def _load_from_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            for row in conn.execute("SELECT data FROM concepts"):
                node = ConceptNode(**json.loads(row[0]))
                self.G.add_node(node.id, kind="concept", data=node)
            for row in conn.execute("SELECT data FROM documents"):
                node = DocumentNode(**json.loads(row[0]))
                self.G.add_node(node.id, kind="document", data=node)
            for row in conn.execute("SELECT src, dst, kind, weight, meta FROM edges"):
                self.G.add_edge(row[0], row[1], kind=row[2], weight=row[3],
                                meta=json.loads(row[4] or "{}"))

    # ── Write ─────────────────────────────────────────────────────────────

    def upsert_concept(self, concept: ConceptNode) -> None:
        self.G.add_node(concept.id, kind="concept", data=concept)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO concepts (id, data, updated_at) VALUES (?, ?, ?)",
                (concept.id, concept.model_dump_json(), datetime.utcnow().isoformat())
            )

    def upsert_document(self, doc: DocumentNode) -> None:
        self.G.add_node(doc.id, kind="document", data=doc)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO documents (id, data, updated_at) VALUES (?, ?, ?)",
                (doc.id, doc.model_dump_json(), datetime.utcnow().isoformat())
            )

    def add_edge(self, src: str, dst: str, kind: str,
                 weight: float = 1.0, meta: dict | None = None) -> None:
        self.G.add_edge(src, dst, kind=kind, weight=weight, meta=meta or {})
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO edges (src, dst, kind, weight, meta) VALUES (?,?,?,?,?)",
                (src, dst, kind, weight, json.dumps(meta or {}))
            )

    # ── Read ──────────────────────────────────────────────────────────────

    def get_concept(self, concept_id: str) -> ConceptNode | None:
        node = self.G.nodes.get(concept_id)
        if node and node.get("kind") == "concept":
            return node["data"]
        return None

    def all_concepts(self) -> Iterator[ConceptNode]:
        for node_id, attrs in self.G.nodes(data=True):
            if attrs.get("kind") == "concept":
                yield attrs["data"]

    def concepts_by_domain(self, domain: str) -> list[ConceptNode]:
        return [c for c in self.all_concepts() if domain in c.domains]

    def related_concepts(self, concept_id: str, min_weight: float = 0.0) -> list[ConceptNode]:
        results = []
        for _, dst, attrs in self.G.out_edges(concept_id, data=True):
            if attrs.get("kind") == "RELATED_TO" and attrs.get("weight", 0) >= min_weight:
                c = self.get_concept(dst)
                if c:
                    results.append(c)
        return results

    def concept_count(self) -> int:
        return sum(1 for _, d in self.G.nodes(data=True) if d.get("kind") == "concept")

    def document_count(self) -> int:
        return sum(1 for _, d in self.G.nodes(data=True) if d.get("kind") == "document")
