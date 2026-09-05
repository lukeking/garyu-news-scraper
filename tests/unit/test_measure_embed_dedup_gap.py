"""`scripts/measure_embed_dedup_gap.py` 的歸因邏輯測試。

腳本的結論（「96% 是跨週」）完全建立在 `classify_pair` 的分類上，所以承重的是它，
不是相似度計算（後者是 `src/analyzer._cosine_similarity`，已在別處被使用與驗證）。

⚠️ **兩個判準的順序是承重的**：跨週的那些**即使兩篇都未分析**也不會被比對到，
所以週別是更外層的原因。反過來寫會把一部分跨週對錯記成「已分析」，把 96% 那個
數字稀釋掉——而數字錯了，結論（該修的是窗不是門檻）就沒有依據。
"""
import os
import sys

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import measure_embed_dedup_gap as gap  # noqa: E402


def _row(week, analysed=False):
    return {"week_id": week, "hot_topic_analyzed": analysed}


def test_different_weeks_is_cross_week():
    assert gap.classify_pair(_row("2026-W33"), _row("2026-W34")) == gap.CROSS_WEEK


def test_cross_week_outranks_analysed():
    """順序守門員：跨週 **且** 已分析時，歸因必須是跨週。

    反過來寫（先看已分析）會把這一類記進「已分析」桶，96% 那個數字就會被稀釋。
    """
    assert gap.classify_pair(
        _row("2026-W33", analysed=True), _row("2026-W34")
    ) == gap.CROSS_WEEK


def test_same_week_with_one_analysed():
    assert gap.classify_pair(
        _row("2026-W34"), _row("2026-W34", analysed=True)
    ) == gap.ANALYSED
    # 對稱：哪一邊已分析都算
    assert gap.classify_pair(
        _row("2026-W34", analysed=True), _row("2026-W34")
    ) == gap.ANALYSED


def test_same_week_both_unanalysed_is_a_real_miss():
    assert gap.classify_pair(_row("2026-W34"), _row("2026-W34")) == gap.REAL_MISS


def test_missing_analysed_field_counts_as_unanalysed():
    """DB 的 `hot_topic_analyzed` 可能是 NULL；缺欄位不該被當成「已分析」而
    把一對真的漏抓誤記成比對範圍外。"""
    assert gap.classify_pair({"week_id": "2026-W34"}, {"week_id": "2026-W34"}) == gap.REAL_MISS


def test_three_buckets_are_distinct():
    """三個桶的字串不可以重複——重複的話統計表會把兩類加在一起而看不出來。"""
    assert len({gap.CROSS_WEEK, gap.ANALYSED, gap.REAL_MISS}) == 3
