"""`scripts/measure_pool_near_dups.py` 的配對判定測試（GNS-20261005-nwn 的完成標準：池內沒有餘弦 ≥ 0.88 且發布差 < 1 天的對）。"""
import os
import sys

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import measure_pool_near_dups as m  # noqa: E402

T0 = "2026-10-06T08:00:00+08:00"


def _row(rid, emb, published=T0):
    return {"id": rid, "embedding": emb, "published": published}


def test_same_story_within_a_day_is_a_pair():
    pairs = m.near_dup_pairs([_row(1, [1, 0]), _row(2, [1, 0.1], "2026-10-06T20:00:00+08:00")], threshold=0.88)

    assert [(a["id"], b["id"]) for _, _, a, b in pairs] == [(1, 2)]
    assert round(pairs[0][1], 1) == 12.0


def test_gap_of_24h_or_more_is_not_a_pair():
    assert m.near_dup_pairs([_row(1, [1, 0]), _row(2, [1, 0], "2026-10-07T08:00:00+08:00")], threshold=0.88) == []


def test_dissimilar_rows_are_not_a_pair():
    assert m.near_dup_pairs([_row(1, [1, 0]), _row(2, [0, 1])], threshold=0.88) == []


def test_rows_without_embedding_or_timezone_are_skipped_not_paired():
    rows = [_row(1, [1, 0]), _row(2, None), _row(3, [1, 0], "2026-10-06T08:00:00")]

    assert m.near_dup_pairs(rows, threshold=0.88) == []
    assert m.unjudgeable(rows) == {"缺向量": 1, "缺時區或發布時間": 1}
