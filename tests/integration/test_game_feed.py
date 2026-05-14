"""
Integration test for game_deduplicate() using pipeline_config.example.yml — T020.
Seeds 40 articles with 15 known near-duplicate pairs and verifies pipeline output.
"""
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.filter import game_deduplicate, compute_jaccard, normalise_title

EXAMPLE_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "pipeline_config.example.yml"
)


@pytest.fixture
def config():
    with open(EXAMPLE_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _article(title: str, pub: str = "2025-01-01T00:00:00") -> dict:
    return {"title": title, "published": pub}


def _build_articles():
    """
    Build 40 articles: 10 unique + 15 near-duplicate pairs (30 articles) = 40 total.
    Each pair shares enough tokens to exceed the 0.50 game_threshold.
    """
    unique = [
        _article(f"完全獨立的遊戲資訊第{i}條從未重複", f"2025-01-{i+1:02d}T00:00:00")
        for i in range(10)
    ]
    # 15 near-duplicate pairs — each pair should collapse to 1 article
    pairs = []
    for i in range(15):
        base = f"FFXIV 7.2 補丁 職業 調整 週報 第{i+1}期 平衡"
        variant = f"FFXIV 7.2 補丁 職業 調整 週報 第{i+1}期 說明"
        pairs.append(_article(base, "2025-02-01T00:00:00"))
        pairs.append(_article(variant, "2025-02-01T00:00:00"))
    return unique + pairs


def test_result_capped_at_twenty(config):
    articles = _build_articles()
    assert len(articles) == 40
    result = game_deduplicate(articles, config)
    assert len(result) <= 20


def test_no_duplicate_pairs_remain(config):
    """No two retained articles should have Jaccard > game_threshold or inclusion relationship."""
    articles = _build_articles()
    result = game_deduplicate(articles, config)
    game_threshold = config["jaccard"]["game_threshold"]
    token_sets = [normalise_title(a["title"]) for a in result]
    for i in range(len(token_sets)):
        for j in range(i + 1, len(token_sets)):
            ts_i, ts_j = token_sets[i], token_sets[j]
            assert not (ts_i and ts_j and (ts_i <= ts_j or ts_j <= ts_i)), (
                f"Inclusion pair found: [{i}] and [{j}]"
            )
            score = compute_jaccard(ts_i, ts_j)
            assert score <= game_threshold, (
                f"Near-duplicate pair found: [{i}] and [{j}] score={score:.3f}"
            )
