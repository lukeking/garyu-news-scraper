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


def _row(week, analysed=False, buffered=None):
    row = {"week_id": week, "hot_topic_analyzed": analysed}
    if buffered:
        row["buffered_at"] = buffered
    return row


MON = "2026-09-14T02:07:23.725181+00:00"  # W38 週一，週報 run 收的（id 3842）
TUE = "2026-09-15T02:50:01.63516+00:00"   # W38 週二，daily 收的（id 3950）
WED = "2026-09-16T02:40:00+00:00"


def test_different_weeks_is_cross_week():
    assert gap.classify_pair(_row("2026-W33"), _row("2026-W34")) == gap.CROSS_WEEK


def test_cross_week_outranks_analysed():
    """順序守門員：跨週 **且** 已分析時，歸因必須是跨週。

    反過來寫（先看已分析）會把這一類記進「已分析」桶，96% 那個數字就會被稀釋。
    """
    assert gap.classify_pair(
        _row("2026-W33", analysed=True), _row("2026-W34")
    ) == gap.CROSS_WEEK


def test_monday_batch_consumed_before_later_arrival_is_analysed():
    """3842↔3950：先進那篇是週一週報那批、當天被消耗，週二那篇進來時它已不在比對窗。"""
    assert gap.classify_pair(_row("2026-W38", True, MON), _row("2026-W38", True, TUE)) == gap.ANALYSED
    assert gap.classify_pair(_row("2026-W38", True, TUE), _row("2026-W38", True, MON)) == gap.ANALYSED


def test_both_daily_then_consumed_is_a_real_miss():
    """後進那篇進來時先進那篇還沒被分析＝在比對窗內。「現在」兩篇都已分析不改變這件事，
    舊版用現在的旗標，把這類錯記成比對範圍外。"""
    assert gap.classify_pair(_row("2026-W38", True, TUE), _row("2026-W38", True, WED)) == gap.REAL_MISS


def test_same_batch_is_a_real_miss():
    """同一批進庫的候選之間互相比對，週一那批也一樣。"""
    assert gap.classify_pair(_row("2026-W38", True, MON), _row("2026-W38", True, MON)) == gap.REAL_MISS


def test_monday_batch_never_consumed_stays_in_window():
    """週一進庫但從沒被選上（現在仍未分析）＝一直在比對窗內。"""
    assert gap.classify_pair(_row("2026-W38", False, MON), _row("2026-W38", False, TUE)) == gap.REAL_MISS


def test_monday_is_the_taiwan_date():
    """week_id 用台灣時區：週日 UTC 20:00 是台灣週一 04:00。"""
    sunday_utc = "2026-09-13T20:00:00+00:00"
    assert gap.classify_pair(_row("2026-W38", True, sunday_utc), _row("2026-W38", True, TUE)) == gap.ANALYSED


def test_same_week_both_unanalysed_is_a_real_miss():
    assert gap.classify_pair(_row("2026-W34"), _row("2026-W34")) == gap.REAL_MISS


def test_missing_analysed_field_counts_as_unanalysed():
    """DB 的 `hot_topic_analyzed` 可能是 NULL；缺欄位不該被當成「已分析」而
    把一對真的漏抓誤記成比對範圍外。"""
    assert gap.classify_pair({"week_id": "2026-W34"}, {"week_id": "2026-W34"}) == gap.REAL_MISS


def test_three_buckets_are_distinct():
    """三個桶的字串不可以重複——重複的話統計表會把兩類加在一起而看不出來。"""
    assert len({gap.CROSS_WEEK, gap.ANALYSED, gap.REAL_MISS}) == 3
