"""
Unit tests for the novelty gate — US1 (009):
passes_novelty, topic_token_signature, _match_prior_basis, select_hot_topics_with_novelty.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.analyzer import (
    passes_novelty,
    topic_token_signature,
    select_hot_topics_with_novelty,
    _match_prior_basis,
)

_CONFIG = {
    "topic_scoring": {"min_threshold": 1.5, "max_hot_topics": 3, "novelty_growth_pct": 0.5},
    "topic_identity": {"similarity_threshold": 0.3},
}


# ── passes_novelty ────────────────────────────────────────────────────────────

def test_passes_no_prior_basis_is_novel():
    assert passes_novelty(2.0, "2026-06-10", None, _CONFIG) is True


def test_passes_growth_below_threshold_suppressed():
    prior = {"cumulative_score": 4.0, "latest_source_date": "2026-06-01"}
    # 5.0 < 4.0 * 1.5 = 6.0 → suppressed
    assert passes_novelty(5.0, "2026-06-10", prior, _CONFIG) is False


def test_passes_growth_and_newer_date_is_novel():
    prior = {"cumulative_score": 4.0, "latest_source_date": "2026-06-01"}
    # 6.5 ≥ 6.0 and 2026-06-10 > 2026-06-01 → novel
    assert passes_novelty(6.5, "2026-06-10", prior, _CONFIG) is True


def test_passes_growth_but_no_newer_date_suppressed():
    prior = {"cumulative_score": 4.0, "latest_source_date": "2026-06-10"}
    # 7.0 ≥ 6.0 but latest date not strictly newer → suppressed
    assert passes_novelty(7.0, "2026-06-10", prior, _CONFIG) is False


# ── topic_token_signature ─────────────────────────────────────────────────────

def test_signature_most_common_tokens():
    arts = [{"title": "a"}, {"title": "b"}, {"title": "c"}]
    ts = {"a": frozenset(["區間", "測速"]), "b": frozenset(["區間", "國道"]), "c": frozenset(["區間"])}
    with patch("src.filter.normalise_title", side_effect=lambda t: ts.get(t, frozenset())):
        sig = topic_token_signature(arts, top_k=2)
    assert sig[0] == "區間"  # appears 3×, most common
    assert len(sig) == 2


# ── _match_prior_basis ────────────────────────────────────────────────────────

def test_match_same_category_and_similar_signature():
    prior = [{"topic_label": "科技執法 · 區間", "topic_token_signature": ["區間", "測速", "國道"],
              "cumulative_score": 3.0, "latest_source_date": "2026-06-01"}]
    # Jaccard({區間,測速,高速},{區間,測速,國道}) = 2/4 = 0.5 ≥ 0.3
    assert _match_prior_basis("科技執法", ["區間", "測速", "高速"], prior, 0.3) is not None


def test_match_different_category_no_match():
    prior = [{"topic_label": "行人事故 · 區間", "topic_token_signature": ["區間", "測速"],
              "cumulative_score": 3.0, "latest_source_date": "2026-06-01"}]
    assert _match_prior_basis("科技執法", ["區間", "測速"], prior, 0.3) is None


def test_match_low_similarity_no_match():
    prior = [{"topic_label": "科技執法 · 區間", "topic_token_signature": ["區間", "測速"],
              "cumulative_score": 3.0, "latest_source_date": "2026-06-01"}]
    # Jaccard({行人,斑馬},{區間,測速}) = 0 < 0.3
    assert _match_prior_basis("科技執法", ["行人", "斑馬"], prior, 0.3) is None


def test_match_backward_compat_bare_category_label():
    """Pre-009 reports stored topic_label as the bare category (no ' · ' separator)."""
    prior = [{"topic_label": "科技執法", "topic_token_signature": ["區間", "測速"],
              "cumulative_score": 3.0, "latest_source_date": "2026-06-01"}]
    assert _match_prior_basis("科技執法", ["區間", "測速"], prior, 0.3) is not None


# ── select_hot_topics_with_novelty (gate-then-cap) ────────────────────────────

def _art(cat, pub):
    return {"title": f"{cat}-{pub}", "major_category": cat, "published": f"{pub}T00:00:00"}


def test_gate_then_cap_prefers_novel_over_stale_highscorers():
    """Top-3 by score are stale; #4/#5 are novel → survivors are the novel ones."""
    buckets = {f"b{i}": [_art(f"cat{i}", "2026-06-10")] for i in range(5)}
    scores = {"b0": 5.0, "b1": 4.8, "b2": 4.6, "b3": 2.0, "b4": 1.9}  # b0-b2 highest
    prior = [
        {"topic_label": f"cat{i} · cat{i}", "topic_token_signature": [f"cat{i}"],
         "cumulative_score": 100.0,  # current 5.0 ≪ 100*1.5 → suppressed
         "latest_source_date": "2026-06-10"}
        for i in range(3)
    ]
    with patch("src.filter.normalise_title", side_effect=lambda t: frozenset([t.split("-")[0]])):
        result = select_hot_topics_with_novelty(buckets, scores, prior, _CONFIG)
    assert set(result) == {"b3", "b4"}  # stale high-scorers gated out


def test_below_threshold_excluded_before_gate():
    buckets = {"b0": [_art("catx", "2026-06-10")]}
    scores = {"b0": 0.5}  # below min_threshold
    with patch("src.filter.normalise_title", side_effect=lambda t: frozenset([t.split("-")[0]])):
        result = select_hot_topics_with_novelty(buckets, scores, [], _CONFIG)
    assert result == []


def test_all_first_time_pass_capped_at_max():
    buckets = {f"b{i}": [_art(f"cat{i}", "2026-06-10")] for i in range(5)}
    scores = {f"b{i}": float(i + 2) for i in range(5)}  # all ≥ threshold, no prior
    with patch("src.filter.normalise_title", side_effect=lambda t: frozenset([t.split("-")[0]])):
        result = select_hot_topics_with_novelty(buckets, scores, [], _CONFIG)
    assert len(result) == 3      # capped at max_hot_topics
    assert result[0] == "b4"     # highest score first
