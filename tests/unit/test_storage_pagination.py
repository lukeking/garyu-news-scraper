"""PostgREST 每次回應最多 1000 列（BACKLOG #14）。兩個讀取點要分頁拿到全部，
且任一頁失敗都不得回傳部分結果。邊界只換 Supabase client。
"""
import logging
import os
import random
import sys
import types
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.storage import get_existing_title_fingerprints, get_traffic_buffer  # noqa: E402

CAP = 1000  # 伺服器端上限，刻意寫字面值而不引用 storage 的常數


class _Query:
    """假 builder：不論 range 要多少，一次最多回 CAP 列；依收到的 order 排序並記下來。"""

    def __init__(self, rows, pages, fail_on_page):
        self._rows, self._pages, self._fail_on_page = rows, pages, fail_on_page
        self.orders, self.filters, self.range_ = [], [], None
        self._negate = False

    def select(self, *a):
        return self

    @property
    def not_(self):
        self._negate = True
        return self

    def is_(self, col, val):
        self.filters.append(("not.is" if self._negate else "is", col, val))
        self._negate = False
        return self

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def gt(self, col, val):
        self.filters.append(("gt", col))
        return self

    def order(self, col, desc=False):
        self.orders.append((col, desc))
        return self

    def range(self, start, end):
        assert self.range_ is None, "同一個 builder 呼叫兩次 .range()——真的 postgrest 會疊加參數"
        self.range_ = (start, end)
        return self

    def execute(self):
        self._pages.append(self)
        assert len(self._pages) <= 10, "分頁停不下來"
        if len(self._pages) == self._fail_on_page:
            raise RuntimeError("page boom")
        rows = list(self._rows)
        for col, desc in reversed(self.orders):
            rows.sort(key=lambda r: r[col], reverse=desc)
        start, end = self.range_ or (0, len(rows))
        return types.SimpleNamespace(data=rows[start:end + 1][:CAP])


def _client(rows, fail_on_page=None):
    """每次 table() 都給新的 builder；pages 依序收集每個執行過的 builder。"""
    pages = []

    def table(name):
        assert name == "articles"
        return _Query(rows, pages, fail_on_page)

    return types.SimpleNamespace(table=table), pages


def _rows(n):
    """id 唯一；published 只有 7 種，大量平手，id 排序才有作用。順序打亂。"""
    rows = [{"id": i, "content_fingerprint": f"fp{i:05d}",
             "published": f"2026-09-{i % 7 + 1:02d}T00:00:00"} for i in range(1, n + 1)]
    random.Random(14).shuffle(rows)
    return rows


def _run(reader, client):
    with patch("src.storage._get_client", return_value=client), \
         patch("src.storage.is_configured", return_value=True):
        return reader()


_BOTH = pytest.mark.parametrize(
    "reader", [get_existing_title_fingerprints, get_traffic_buffer],
    ids=["fingerprints", "buffer"],
)


def test_fingerprints_returns_every_row_past_the_cap(caplog):
    rows = _rows(2345)
    client, _ = _client(rows)
    with caplog.at_level(logging.INFO, logger="src.storage"):
        got = _run(get_existing_title_fingerprints, client)
    assert len(got) == 2345
    assert got == {r["content_fingerprint"] for r in rows}
    assert "get_existing_title_fingerprints：取得 2345 筆" in caplog.text


@_BOTH
def test_exact_multiple_of_page_size_returns_all_and_stops(reader):
    """2000 列：第三頁回 0 列才停，所以正好 3 次請求。"""
    client, pages = _client(_rows(2000))
    got = _run(reader, client)
    assert len(got) == 2000
    assert len(pages) == 3


def test_buffer_returns_every_row_in_query_order(caplog):
    rows = _rows(2345)
    client, _ = _client(rows)
    with caplog.at_level(logging.INFO, logger="src.storage"):
        got = _run(get_traffic_buffer, client)
    assert len(got) == 2345
    expected = sorted(rows, key=lambda r: r["id"])
    expected.sort(key=lambda r: r["published"], reverse=True)
    assert got == expected, "published desc、同日依 id 升冪；跨頁不得重複或跳過"
    assert "get_traffic_buffer：取得 2345 筆" in caplog.text


def test_fingerprints_failure_on_page_two_returns_empty_set(caplog):
    client, _ = _client(_rows(2345), fail_on_page=2)
    with caplog.at_level(logging.WARNING, logger="src.storage"):
        assert _run(get_existing_title_fingerprints, client) == set()
    assert "跨週指紋查詢失敗" in caplog.text


def test_buffer_failure_on_page_two_raises(caplog):
    client, _ = _client(_rows(2345), fail_on_page=2)
    with caplog.at_level(logging.ERROR, logger="src.storage"), \
         pytest.raises(RuntimeError, match="page boom"):
        _run(get_traffic_buffer, client)
    assert "get_traffic_buffer 失敗" in caplog.text


@pytest.mark.parametrize("reader, filters, orders", [
    (get_existing_title_fingerprints,
     [("not.is", "content_fingerprint", "null")],
     [("id", False)]),
    (get_traffic_buffer,
     [("eq", "content_type", "traffic"), ("eq", "hot_topic_analyzed", False),
      ("gt", "buffer_expires_at")],
     [("published", True), ("id", False)]),
], ids=["fingerprints", "buffer"])
def test_every_page_keeps_its_filters_and_orders_by_id(reader, filters, orders):
    client, pages = _client(_rows(2345))
    _run(reader, client)
    assert len(pages) == 3
    assert [p.filters for p in pages] == [filters] * 3
    assert [p.orders for p in pages] == [orders] * 3
