"""Semantic embedding fingerprints for documents and queries."""
from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

from remnant.config import EMBED_MODEL

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def embed(texts: list[str]) -> np.ndarray:
    """Return (N, D) float32 embedding matrix."""
    return _get_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)


def embed_one(text: str) -> list[float]:
    return embed([text])[0].tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def batch_similarity(query_vec: list[float], matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity between query_vec and each row of matrix."""
    q = np.array(query_vec)
    norms = np.linalg.norm(matrix, axis=1)
    norms[norms == 0] = 1e-9
    return (matrix @ q) / (norms * np.linalg.norm(q))
