"""
Unit tests for mark_articles_analyzed — US2 (010):
count return, empty-input short-circuit, fail-soft ERROR semantics.
(Runner-level consumption ordering is covered in tests/integration/test_digest_weekly.py.)
"""
import logging
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.storage import mark_articles_analyzed


def test_mark_returns_count_and_updates_by_link():
    client = MagicMock()
    with patch("src.storage._get_client", return_value=client):
        assert mark_articles_analyzed(["l1", "l2", "l3"]) == 3
    client.table.assert_called_once_with("articles")
    client.table.return_value.update.assert_called_once_with({"hot_topic_analyzed": True})
    client.table.return_value.update.return_value.in_.assert_called_once_with(
        "link", ["l1", "l2", "l3"]
    )


def test_mark_empty_links_returns_zero_without_touching_client():
    with patch("src.storage._get_client") as get_client:
        assert mark_articles_analyzed([]) == 0
    get_client.assert_not_called()


def test_mark_failure_logs_error_and_returns_zero(caplog):
    client = MagicMock()
    client.table.return_value.update.return_value.in_.return_value.execute.side_effect = \
        RuntimeError("boom")
    with patch("src.storage._get_client", return_value=client), \
         caplog.at_level(logging.ERROR):
        assert mark_articles_analyzed(["l1"]) == 0
    assert "mark_articles_analyzed 失敗" in caplog.text


# ── 013: 匯流文章的消耗（INV-4／INV-5／INV-7）─────────────────────────────

from src.analyzer import select_digest_pool  # noqa: E402

_CFG = {"trigger_count": 10, "quality_floor": 0.18, "max_articles": 3}


def _art(idx, q=0.3, cat="道安政策"):
    return {
        "link": f"https://example.com/{idx}",
        "major_category": cat,
        "initial_quality_score": q,
        "title": f"文章{idx}",
        "published": "2026-08-05T00:00:00",
    }


def test_merged_articles_are_in_the_consumption_source():
    """INV-7：匯流進池的兄弟類別文章必須出現在**消耗來源**中。

    ⚠️ 範圍誠實標註：runner 消耗的是 `pool_all`
    （`scripts/traffic_weekly_analysis.py`「消耗：…池歸零」那段）。本測試守的是
    **`pool_all` 這個來源的內容**，不是 runner 的呼叫順序——後者由
    `tests/integration/test_digest_weekly.py` 覆蓋。分開講是因為兩者會各自壞掉。
    """
    arts = [
        _art(1, cat="道安政策"),
        _art(2, cat="路權政策"),
        _art(3, cat="科技執法"),
    ]
    cfg = {**_CFG, "include_categories": ["路權政策", "科技執法"]}
    _selected, pool_all, _eff = select_digest_pool(arts, "道安政策", cfg, set())

    consumed_links = {a["link"] for a in pool_all}
    assert consumed_links == {
        "https://example.com/1", "https://example.com/2", "https://example.com/3",
    }, "兄弟類別文章若不在 pool_all，就不會被消耗，下週會重複進池"


def test_layer_containment_holds_under_merge():
    """INV-4／INV-5：selected ⊆ effective ⊆ pool_all，且 len(selected) ≤ max_articles。

    低分文章（低於 quality_floor）必須留在 pool_all（會被消耗）但不進 selected——
    這是 010「池歸零」的核心語意，匯流不得破壞它。
    """
    arts = [
        _art(1, q=0.50, cat="道安政策"),
        _art(2, q=0.40, cat="路權政策"),
        _art(3, q=0.35, cat="科技執法"),
        _art(4, q=0.30, cat="交通工程"),
        _art(5, q=0.10, cat="路權政策"),   # 低於 floor
    ]
    cfg = {**_CFG, "include_categories": ["路權政策", "科技執法", "交通工程"]}
    selected, pool_all, effective = select_digest_pool(arts, "道安政策", cfg, set())

    pool_links = {a["link"] for a in pool_all}
    sel_links = {a["link"] for a in selected}
    assert sel_links <= pool_links
    assert effective == 4                      # 5 篇進池，1 篇低於 floor
    assert len(pool_all) == 5
    assert len(selected) == 3 == _CFG["max_articles"]
    assert "https://example.com/5" in pool_links   # 低分仍被消耗
    assert "https://example.com/5" not in sel_links
