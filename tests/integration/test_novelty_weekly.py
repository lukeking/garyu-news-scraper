"""
Integration test for the novelty gate across a two-week sequence — US1 (009).

Simulates: week 1 reports a topic → persists its basis → week 2 with no surge is
suppressed, while a surged week-2 variant re-triggers. No live Supabase/Gemini —
the week-1 basis is built exactly as scripts/traffic_weekly_analysis.py would.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.analyzer import (
    score_topic_buckets,
    select_hot_topics_with_novelty,
    topic_token_signature,
    _bucket_latest_date,
)

_CONFIG = {
    "jaccard": {"merge_threshold": 0.45, "cluster_lower": 0.20},
    "topic_scoring": {"min_threshold": 1.5, "max_hot_topics": 3, "novelty_growth_pct": 0.5},
    "topic_identity": {"similarity_threshold": 0.3},
}

# Deterministic token map (no jieba dependency in the test).
_TOKENS = {"moto": frozenset(["機車", "事故"])}


def _art(token_key, source, pub, quality=0.6, category="機車事故"):
    return {
        "title": token_key, "major_category": category,
        "initial_quality_score": quality, "source": source,
        "published": f"{pub}T00:00:00", "summary": "x",
    }


def _basis_from_selection(buckets, scores, bid):
    """Build the hot_topic_reports basis row the weekly script would persist."""
    arts = buckets[bid]
    sig = topic_token_signature(arts)
    return {
        "topic_label": f"{arts[0]['major_category']} · {sig[0]}" if sig else arts[0]["major_category"],
        "topic_token_signature": sig,
        "cumulative_score": scores[bid],
        "latest_source_date": _bucket_latest_date(arts),
    }


def test_two_week_suppress_then_retrigger():
    with patch("src.filter.normalise_title", side_effect=lambda t: _TOKENS.get(t, frozenset())):
        # ── Week 1: a healthy 機車事故 bucket gets selected and reported ──
        wk1 = {"b": [_art("moto", s, "2026-06-02") for s in ("A", "B", "C")]}
        wk1_scores = score_topic_buckets(wk1, _CONFIG)
        wk1_sel = select_hot_topics_with_novelty(wk1, wk1_scores, [], _CONFIG)
        assert "b" in wk1_sel
        prior = [_basis_from_selection(wk1, wk1_scores, "b")]

        # ── Week 2a: similar volume, no later publication day → SUPPRESSED ──
        wk2 = {"b": [_art("moto", s, "2026-06-02") for s in ("A", "B", "C")]}
        wk2_scores = score_topic_buckets(wk2, _CONFIG)
        assert select_hot_topics_with_novelty(wk2, wk2_scores, prior, _CONFIG) == []

        # ── Week 2b: surge (more sources + quality) AND a later day → RE-TRIGGER ──
        wk2b = {"b": [_art("moto", s, "2026-06-09", quality=0.9)
                      for s in ("A", "B", "C", "D", "E", "F")]}
        wk2b_scores = score_topic_buckets(wk2b, _CONFIG)
        assert "b" in select_hot_topics_with_novelty(wk2b, wk2b_scores, prior, _CONFIG)


def test_fail_open_equivalent_empty_prior_analyzes():
    """When prior reports can't be read, the script passes [] → topics treated as novel."""
    with patch("src.filter.normalise_title", side_effect=lambda t: _TOKENS.get(t, frozenset())):
        wk = {"b": [_art("moto", s, "2026-06-02") for s in ("A", "B", "C")]}
        scores = score_topic_buckets(wk, _CONFIG)
        assert "b" in select_hot_topics_with_novelty(wk, scores, [], _CONFIG)
