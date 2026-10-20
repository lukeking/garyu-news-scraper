"""spec 015 T007：論壇回覆的固定週窗口——［該 ISO 週週一 00:00 UTC − 7 天, 該週一 00:00 UTC）。"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.collector import _forum_window  # noqa: E402

UTC = timezone.utc
THIS_WEEK = (datetime(2026, 10, 12, tzinfo=UTC), datetime(2026, 10, 19, tzinfo=UTC))
LAST_WEEK = (datetime(2026, 10, 5, tzinfo=UTC), datetime(2026, 10, 12, tzinfo=UTC))


@pytest.mark.parametrize("now", [
    datetime(2026, 10, 19, 0, 0, tzinfo=UTC),     # 排程時刻本身
    datetime(2026, 10, 19, 0, 30, tzinfo=UTC),    # 延遲 30 分開跑
    datetime(2026, 10, 19, 2, 30, tzinfo=UTC),    # 延遲 2.5 小時開跑
    datetime(2026, 10, 21, 10, 0, tzinfo=UTC),    # 同一週的週三重跑
])
def test_same_iso_week_gets_the_same_window(now):
    assert _forum_window(now) == THIS_WEEK


def test_sunday_night_gets_the_previous_window():
    assert _forum_window(datetime(2026, 10, 18, 23, 59, tzinfo=UTC)) == LAST_WEEK


def test_non_utc_now_is_judged_in_utc():
    # 日本時間週一 08:00 在 UTC 仍是週日 23:00
    jst_monday_morning = datetime(2026, 10, 19, 8, 0, tzinfo=timezone(timedelta(hours=9)))
    assert _forum_window(jst_monday_morning) == LAST_WEEK


def test_adjacent_weeks_meet_without_gap_or_overlap():
    first = _forum_window(datetime(2026, 10, 19, 1, 0, tzinfo=UTC))
    second = _forum_window(datetime(2026, 10, 26, 0, 45, tzinfo=UTC))
    assert first[1] == second[0]
    assert second[1] - second[0] == timedelta(days=7)
