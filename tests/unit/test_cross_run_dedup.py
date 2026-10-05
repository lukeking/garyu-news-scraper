"""GNS-20261005-nwn：embed_dedup 比對窗（本週＋上週未消耗）與跨期重複的影子判定。
向量用二維（同 test_embed_dedup.py）：二維餘弦可以手算。"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.analyzer import find_cross_run_repeats  # noqa: E402
from src.pipeline.traffic import TrafficCategory, dedup_window  # noqa: E402

TW = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=TW)  # 2026-W41 週三
BASE, NEAR = [1.0, 0.0], [0.9, 0.4]          # cos ≈ 0.914
OTHER, NEAR_OTHER = [0.0, 1.0], [0.4, 0.9]   # cos ≈ 0.914；與 BASE 只有 ≈ 0.406
FAR = [0.8, 0.6]                              # 與 BASE 0.800
PUB = "2026-09-11T02:13:00+00:00"


def _row(aid, week):
    return {"id": aid, "week_id": week}


def _art(aid, emb, pub=PUB):
    return {"id": aid, "title": f"標題{aid}", "summary": "摘要", "embedding": emb, "published": pub}


# ── dedup_window ──────────────────────────────────────────────

def test_window_is_this_week_and_last_week():
    rows = [_row(1, "2026-W41"), _row(2, "2026-W40"), _row(3, "2026-W39")]
    assert [r["id"] for r in dedup_window(rows, NOW)] == [1, 2]


def test_window_uses_taiwan_dates():
    """台灣週一 00:30 是 UTC 週日：用 UTC 會把本週算成 W40、把 W39 也放進來。"""
    monday_early = datetime(2026, 10, 5, 0, 30, tzinfo=TW)
    rows = [_row(1, "2026-W41"), _row(2, "2026-W40"), _row(3, "2026-W39")]
    assert [r["id"] for r in dedup_window(rows, monday_early)] == [1, 2]


def test_window_crosses_the_iso_year():
    """2027-01-06 是 2027-W01；上一週是 2026-W53（2026 有 53 週）。"""
    rows = [_row(1, "2027-W01"), _row(2, "2026-W53"), _row(3, "2026-W52")]
    assert [r["id"] for r in dedup_window(rows, datetime(2027, 1, 6, 9, 0, tzinfo=TW))] == [1, 2]


# ── find_cross_run_repeats ─────────────────────────────────────

def test_same_article_republished_within_a_day_is_flagged():
    hits = find_cross_run_repeats([_art(1, BASE)], [_art(77, NEAR, "2026-09-11T07:00:00+00:00")], threshold=0.88)
    assert [(c["id"], old["id"]) for c, old, _, _ in hits] == [(1, 77)]
    _, _, cos, gap_h = hits[0]
    assert cos == pytest.approx(0.914, abs=0.001) and gap_h == pytest.approx(4.783, abs=0.001)


def test_a_full_day_apart_is_not_flagged():
    """發布差要 < 24 小時；剛好 24 小時就是另一天的新聞了。"""
    old = _art(77, NEAR, "2026-09-12T02:13:00+00:00")
    assert find_cross_run_repeats([_art(1, BASE)], [old], threshold=0.88) == []


def test_below_threshold_is_not_flagged():
    assert find_cross_run_repeats([_art(1, BASE)], [_art(77, FAR)], threshold=0.88) == []


@pytest.mark.parametrize("cand_pub, old_pub", [("", PUB), (PUB, None), ("Thu, 11 Sep 2026", PUB)])
def test_missing_or_unparseable_published_is_not_flagged(cand_pub, old_pub):
    """缺發布時間就判不了「同一則」：寧可漏記，不要誤記。"""
    assert find_cross_run_repeats([_art(1, BASE, cand_pub)], [_art(77, NEAR, old_pub)], threshold=0.88) == []


def test_most_similar_consumed_row_is_reported():
    olds = [_art(77, [0.9, 0.43]), _art(78, [0.99, 0.1])]
    hits = find_cross_run_repeats([_art(1, BASE)], olds, threshold=0.88)
    assert [old["id"] for _, old, _, _ in hits] == [78]


def test_pgvector_string_on_consumed_rows_is_parsed():
    hits = find_cross_run_repeats([_art(1, BASE)], [_art(77, "[0.9,0.4]")], threshold=0.88)
    assert [old["id"] for _, old, _, _ in hits] == [77]


# ── TrafficCategory._embedding_dedup（真的方法，只換邊界） ──────────

@pytest.fixture
def boundary(monkeypatch):
    calls = {"consumed": []}
    monkeypatch.setattr("src.analyzer.attach_embeddings", lambda articles: None)
    monkeypatch.setattr("src.storage.get_traffic_buffer", lambda *a, **k: [
        {**_art(91, NEAR), "week_id": "2026-W40"},
        {**_art(92, NEAR_OTHER), "week_id": "2026-W39"},
    ])
    monkeypatch.setattr("src.storage.get_recent_consumed_traffic", lambda *a, **k: calls["consumed"])
    return calls


def test_last_weeks_leftover_blocks_but_older_does_not(boundary):
    """W40 的未消耗列擋得到；W39 那篇在窗外，候選 2 留下。"""
    kept = TrafficCategory()._embedding_dedup([_art(1, BASE), _art(2, OTHER)], {}, now=NOW)
    assert [a["id"] for a in kept] == [2]


def test_shadow_logs_but_never_drops(boundary, caplog):
    boundary["consumed"] = [{"id": 77, "title": "舊的那篇", "published": PUB, "embedding": NEAR_OTHER}]
    with caplog.at_level(logging.INFO, logger="src.pipeline.traffic"):
        kept = TrafficCategory()._embedding_dedup([_art(1, BASE), _art(2, OTHER)], {}, now=NOW)
    assert [a["id"] for a in kept] == [2]
    assert "[embed_dedup 影子] 會擋 cos=0.9138 發布差 0.0h：「標題2」↔ 已消耗 id=77「舊的那篇」" in caplog.text
    assert "[embed_dedup 影子] 跨期重複：1/1 篇候選會被擋（發布差 < 24h、餘弦 ≥ 0.88；只記錄、不擋）" in caplog.text


def test_shadow_prints_zero_too(boundary, caplog):
    with caplog.at_level(logging.INFO, logger="src.pipeline.traffic"):
        TrafficCategory()._embedding_dedup([_art(2, OTHER)], {}, now=NOW)
    assert "[embed_dedup 影子] 跨期重複：0/1 篇候選會被擋" in caplog.text


def test_shadow_failure_does_not_touch_dedup(boundary, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("consumed boom")
    monkeypatch.setattr("src.storage.get_recent_consumed_traffic", boom)
    with caplog.at_level(logging.WARNING, logger="src.pipeline.traffic"):
        kept = TrafficCategory()._embedding_dedup([_art(1, BASE), _art(2, OTHER)], {}, now=NOW)
    assert [a["id"] for a in kept] == [2]
    assert "[embed_dedup 影子] 跨期比對失敗，略過（只記錄，不影響去重）：consumed boom" in caplog.text
