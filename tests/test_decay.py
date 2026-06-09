"""Tests for the decay scoring model."""
from datetime import datetime, timezone

import pytest

from remnant.models import ConceptNode
from remnant.decay.model import score


def _concept(**kwargs) -> ConceptNode:
    defaults = dict(
        id="concept:test",
        label="Test Concept",
        description="A test concept.",
        domains=["physics"],
        first_seen=datetime(2000, 1, 1, tzinfo=timezone.utc),
        last_cited=datetime(2010, 1, 1, tzinfo=timezone.utc),
        importance_weight=0.8,
        decay_score=0.0,
    )
    defaults.update(kwargs)
    return ConceptNode(**defaults)


def test_fully_decayed():
    c = _concept()
    report = score(c, recent_citations=0, peak_citations=100,
                   domains_reached=1, total_known_domains=10,
                   last_synthesis_year=1995)
    assert report.decay_score > 0.65
    assert report.alert is True


def test_healthy_concept():
    c = _concept()
    report = score(c, recent_citations=90, peak_citations=100,
                   domains_reached=8, total_known_domains=10,
                   last_synthesis_year=2024)
    assert report.decay_score < 0.30
    assert report.alert is False


def test_partial_decay():
    c = _concept()
    report = score(c, recent_citations=30, peak_citations=100,
                   domains_reached=3, total_known_domains=10,
                   last_synthesis_year=2015)
    assert 0.30 <= report.decay_score <= 0.80


def test_zero_peak_citations():
    """Should not divide by zero."""
    c = _concept()
    report = score(c, recent_citations=0, peak_citations=0,
                   domains_reached=1, total_known_domains=5,
                   last_synthesis_year=None)
    assert 0.0 <= report.decay_score <= 1.0


def test_never_synthesized_boosts_decay():
    c = _concept()
    r_synth = score(c, recent_citations=50, peak_citations=100,
                    domains_reached=5, total_known_domains=10,
                    last_synthesis_year=2023)
    r_no_synth = score(c, recent_citations=50, peak_citations=100,
                       domains_reached=5, total_known_domains=10,
                       last_synthesis_year=None)
    assert r_no_synth.decay_score > r_synth.decay_score
