"""
Unit tests for game_deduplicate() — FR-008, FR-009, FR-010.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.filter import game_deduplicate

CONFIG = {"jaccard": {"game_threshold": 0.50}}


def _article(title: str, pub: str = "2025-01-01T00:00:00") -> dict:
    return {"title": title, "published": pub}


def test_inclusion_check_shorter_discarded():
    """FR-008: A whose tokens ⊆ B's tokens is dropped."""
    long_title = "FFXIV 7.2 更新 職業 調整 詳細 說明"
    short_title = "FFXIV 更新"
    articles = [_article(long_title), _article(short_title)]
    result = game_deduplicate(articles, CONFIG)
    titles = [a["title"] for a in result]
    assert long_title in titles
    assert short_title not in titles


def test_jaccard_above_threshold_discarded():
    """FR-009: second article with Jaccard > 0.50 vs. retained article is dropped."""
    a1 = _article("FFXIV 7.2 更新 職業 調整 平衡 補丁")
    a2 = _article("FFXIV 7.2 更新 職業 調整 平衡 說明")
    result = game_deduplicate([a1, a2], CONFIG)
    assert len(result) == 1


def test_cap_at_twenty():
    """FR-010: output is capped at 20 articles even with 25 unique inputs."""
    articles = [_article(f"完全不同的遊戲新聞第{i}篇獨立標題內容") for i in range(25)]
    result = game_deduplicate(articles, CONFIG)
    assert len(result) <= 20


def test_all_unique_retained():
    """All unique articles (≤ 20) are retained without truncation."""
    articles = [
        _article("戰士職業平衡調整說明"),
        _article("白魔法師治療技能更新"),
        _article("忍者轉職任務攻略完整"),
        _article("占星術士位置技巧介紹"),
        _article("龍騎士連擊循環教學"),
        _article("賢者治療手法分析"),
        _article("舞者職業特色詳解"),
        _article("黑魔法師傷害輸出優化"),
        _article("武士刀技連段攻略"),
        _article("園藝師採集路線規劃"),
    ]
    result = game_deduplicate(articles, CONFIG)
    assert len(result) == 10


def test_disjoint_articles_all_retained():
    """Completely disjoint titles → all retained (up to cap)."""
    a1 = _article("坦克職業技能說明")
    a2 = _article("治療職業平衡調整")
    a3 = _article("遠端物理傷害輸出")
    result = game_deduplicate([a1, a2, a3], CONFIG)
    assert len(result) == 3


def test_empty_input_returns_empty():
    result = game_deduplicate([], CONFIG)
    assert result == []


def test_newest_first_ordering():
    """Retained articles are sorted newest-first."""
    old = _article("舊版本職業技能說明詳細", "2024-12-01T00:00:00")
    new = _article("新地圖區域探索指南完整", "2025-03-01T00:00:00")
    result = game_deduplicate([old, new], CONFIG)
    assert len(result) == 2
    assert result[0]["title"] == new["title"]
