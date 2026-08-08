"""
FR-008 regression (012 T006a): wiring the relevance gate in front of the weekly
selection path (partition_by_relevance → cluster_traffic_articles → score_topic_buckets
→ select_hot_topics_with_novelty) must NOT break existing behaviour —
  * ≤ max_hot_topics cap still holds;
  * the novelty gate still suppresses / passes buckets the gate never touched;
  * the gate changes no article's major_category.

Clustering is made deterministic by mocking src.filter.normalise_title (same idiom as
test_novelty_gate.py). The gate itself matches on the real title substring, independent of
the mock — so title drives on/off-topic, the mock drives clustering/scoring/signature.
"""
import copy
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.filter import partition_by_relevance
from src.analyzer import (
    cluster_traffic_articles,
    score_topic_buckets,
    select_hot_topics_with_novelty,
)

_CONFIG = {
    "jaccard": {"merge_threshold": 0.45, "cluster_lower": 0.20},
    "topic_scoring": {"min_threshold": 1.5, "max_hot_topics": 3, "novelty_growth_pct": 0.5},
    "topic_identity": {"similarity_threshold": 0.3},
}

# Only 機車事故 carries a rule; every other category is fail-open (untouched).
_RULES = {"機車事故": {"require_any": ["撞", "事故", "死", "傷", "送醫"]}}


def _art(title, cat, source, pub, q):
    return {
        "title": title, "major_category": cat, "source": source,
        "published": f"{pub}T00:00:00", "initial_quality_score": q, "link": title,
    }


# Fixture: 機車事故 = 3 real accidents (kept) + 2 crime (removed by gate);
#          道安政策 = 3 articles the gate never touches (no rule).
_FIXTURE = [
    _art("機車追撞轎車釀2傷", "機車事故", "A報", "2026-08-01", 0.9),
    _art("機車自撞分隔島1死", "機車事故", "B報", "2026-08-02", 0.9),
    _art("機車事故騎士送醫不治", "機車事故", "C報", "2026-08-03", 0.9),
    _art("男子涉竊機車遭通緝", "機車事故", "D報", "2026-08-01", 0.9),   # off-topic (no accident token)
    _art("毒駕騎士遭羈押交保", "機車事故", "E報", "2026-08-02", 0.9),   # off-topic
    _art("道安會報提改革方案", "道安政策", "F報", "2026-08-01", 0.9),
    _art("道安政策願景新規劃", "道安政策", "G報", "2026-08-02", 0.9),
    _art("道安會報檢討肇因", "道安政策", "H報", "2026-08-03", 0.9),
]

# Deterministic tokens: a 2-token shared core per category + 3 unique per article →
# pairwise Jaccard within a core = 2/8 = 0.25 ∈ [cluster_lower, merge_threshold]
# → one bucket per category, no dedup; cross-category Jaccard = 0 → separate buckets.
# Crime pieces share the 機車事故 core so that WITHOUT the gate they land in the accident
# bucket (the gate's job is to pull them out before that).
_CORE = {"機車事故": ("機共1", "機共2"), "道安政策": ("道共1", "道共2")}


def _mock_tokens(title):
    for art in _FIXTURE:
        if art["title"] == title:
            c = _CORE[art["major_category"]]
            uniq = (f"u_{title}_1", f"u_{title}_2", f"u_{title}_3")
            return frozenset(c + uniq)
    return frozenset()


def _run_full_path(articles, prior):
    """partition → cluster → score → select, returning (result_ids, buckets)."""
    on, _off = partition_by_relevance(copy.deepcopy(articles), _RULES)
    buckets = cluster_traffic_articles(on, _CONFIG)
    scores = score_topic_buckets(buckets, _CONFIG)
    result = select_hot_topics_with_novelty(buckets, scores, prior, _CONFIG)
    return result, buckets


def _run_baseline(articles, prior):
    """Same path WITHOUT the gate — the FR-008 reference."""
    buckets = cluster_traffic_articles(copy.deepcopy(articles), _CONFIG)
    scores = score_topic_buckets(buckets, _CONFIG)
    result = select_hot_topics_with_novelty(buckets, scores, prior, _CONFIG)
    return result, buckets


def _selected_categories(buckets, result):
    return sorted(buckets[bid][0]["major_category"] for bid in result if buckets.get(bid))


# ── T006a-1: gate removes only off-topic, never mutates major_category ─────────

def test_gate_removes_only_offtopic_and_preserves_category():
    cat_of = {a["title"]: a["major_category"] for a in _FIXTURE}
    on, off = partition_by_relevance(copy.deepcopy(_FIXTURE), _RULES)
    assert {a["title"] for a in off} == {"男子涉竊機車遭通緝", "毒駕騎士遭羈押交保"}
    # gate changed no article's category (only added _relevance_reason)
    for a in on + off:
        assert a["major_category"] == cat_of[a["title"]]
    # untouched category fully survived (fail-open, no rule)
    assert sum(1 for a in on if a["major_category"] == "道安政策") == 3


# ── T006a-2: ≤ cap holds; novelty PASS on untouched category is unchanged ──────

def test_cap_and_untouched_category_pass_unchanged_by_gate():
    with patch("src.filter.normalise_title", side_effect=_mock_tokens):
        r_base, b_base = _run_baseline(_FIXTURE, [])   # no prior → first-time novel
        r_gate, b_gate = _run_full_path(_FIXTURE, [])
    # ≤ max_hot_topics
    assert len(r_gate) <= _CONFIG["topic_scoring"]["max_hot_topics"]
    # gate does not change which categories get selected (accident bucket survives the
    # crime removal; untouched 道安政策 unchanged)
    assert _selected_categories(b_gate, r_gate) == _selected_categories(b_base, r_base)
    assert set(_selected_categories(b_gate, r_gate)) == {"機車事故", "道安政策"}


# ── T006a-3: novelty SUPPRESS on an untouched bucket is unchanged by the gate ──

def test_untouched_bucket_novelty_suppression_unchanged_by_gate():
    from src.analyzer import topic_token_signature
    with patch("src.filter.normalise_title", side_effect=_mock_tokens):
        # Derive a prior that MATCHES the 道安政策 bucket (same category + its real
        # signature), with a huge cumulative_score (current ≪ prior×1.5) and a
        # not-older date → the novelty gate must suppress it.
        b0 = cluster_traffic_articles(copy.deepcopy(_FIXTURE), _CONFIG)
        dao = next(a for a in b0.values() if a[0]["major_category"] == "道安政策")
        prior = [{
            "topic_label": "道安政策 · 前期",
            "topic_token_signature": topic_token_signature(dao),
            "cumulative_score": 100.0,
            "latest_source_date": "2026-08-03",
        }]
        r_base, b_base = _run_baseline(_FIXTURE, prior)
        r_gate, b_gate = _run_full_path(_FIXTURE, prior)
    # 道安政策 suppressed in BOTH runs (gate didn't perturb its novelty verdict)
    assert "道安政策" not in _selected_categories(b_base, r_base)
    assert "道安政策" not in _selected_categories(b_gate, r_gate)
    # 機車事故 (novel, first-time) still selected in both
    assert "機車事故" in _selected_categories(b_base, r_base)
    assert "機車事故" in _selected_categories(b_gate, r_gate)
    assert len(r_gate) <= _CONFIG["topic_scoring"]["max_hot_topics"]
