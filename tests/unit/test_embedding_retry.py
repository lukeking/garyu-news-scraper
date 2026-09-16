"""embedding 呼叫的退避重試與整次 run 的等待預算（BACKLOG #13 第二步）。
邊界值一律寫字面值（3 次、60 秒），不寫常數名——常數漂掉時測試才會紅。
"""
import logging
import os
import sys

import requests

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _REPO)

from src import analyzer  # noqa: E402

DUMMY_KEY = "dummy-key-for-test"
VECTOR = [0.1, 0.2]


class _Resp:
    def __init__(self, status, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self.text = ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)

    def json(self):
        return {"embedding": {"values": VECTOR}}


def _wire(monkeypatch, responses):
    """`responses` 依序被 post 取用；元素是狀態碼、`_Resp` 或要丟出的例外。"""
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_KEY)
    calls, sleeps = [], []
    queue = list(responses)

    def fake_post(url, json=None, timeout=None, headers=None, **kwargs):
        calls.append(headers)
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, _Resp) else _Resp(item)

    monkeypatch.setattr(analyzer.requests, "post", fake_post)
    monkeypatch.setattr(analyzer.time, "sleep", lambda s: sleeps.append(s))
    return calls, sleeps


def _articles(n):
    """每篇各自一個 dict——`[{...}] * n` 是同一個物件，第一篇寫入向量後其餘會被跳過。"""
    return [{"title": f"t{i}", "summary": ""} for i in range(n)]


def test_429_is_retried_with_backoff_then_succeeds(monkeypatch):
    calls, sleeps = _wire(monkeypatch, [429, 200])

    assert analyzer.generate_embedding("text") == VECTOR
    assert len(calls) == 2
    assert sleeps == [10]
    assert all(h["x-goog-api-key"] == DUMMY_KEY for h in calls), "重試那次也要帶 header"


def test_non_transient_error_is_not_retried(monkeypatch):
    calls, sleeps = _wire(monkeypatch, [400])

    assert analyzer.generate_embedding("text") is None
    assert len(calls) == 1
    assert sleeps == []


def test_malformed_200_body_is_not_retried(monkeypatch):
    class _NoVector(_Resp):
        def json(self):
            return {}

    calls, sleeps = _wire(monkeypatch, [_NoVector(200)])

    assert analyzer.generate_embedding("text") is None
    assert len(calls) == 1
    assert sleeps == []


def test_5xx_and_connection_errors_are_retried(monkeypatch):
    calls, _ = _wire(monkeypatch, [503, requests.ConnectionError("boom"), 200])

    assert analyzer.generate_embedding("text") == VECTOR
    assert len(calls) == 3


def test_at_most_3_retries_per_article(monkeypatch):
    """Retry-After=1 讓預算綁不住，才量得到每篇的次數上限本身。"""
    calls, sleeps = _wire(monkeypatch, [_Resp(429, {"Retry-After": "1"})])

    assert analyzer.generate_embedding("text") is None
    assert len(calls) == 4, "1 次原始呼叫 + 3 次重試"
    assert sleeps == [1, 1, 1]


def test_final_failure_logs_exactly_one_generation_failure_line(monkeypatch, caplog):
    """09-11 的 BACKLOG 用「生成失敗」行數當失敗篇數，重試行不可混進這個計數。"""
    _wire(monkeypatch, [_Resp(429, {"Retry-After": "1"})])

    with caplog.at_level(logging.WARNING):
        analyzer.generate_embedding("text")

    failures = [r for r in caplog.records if "生成失敗" in r.getMessage()]
    assert len(failures) == 1


def _failure_lines(caplog):
    return [r.getMessage() for r in caplog.records if "生成失敗" in r.getMessage()]


def test_failure_line_keeps_the_prefix_the_weekly_routine_counts(monkeypatch, caplog):
    """`routines/weekly-verify/FOCUS.md` 數「`[embedding] 生成失敗：`（含冒號）開頭」的行；改掉開頭會靜靜數成 0。"""
    _wire(monkeypatch, [400])

    with caplog.at_level(logging.WARNING):
        analyzer.attach_embeddings(_articles(2))

    lines = _failure_lines(caplog)
    assert len(lines) == 2
    assert all(m.startswith("[embedding] 生成失敗：") for m in lines), lines


def test_failure_line_says_non_transient_and_exception_type(monkeypatch, caplog):
    _wire(monkeypatch, [400])

    with caplog.at_level(logging.WARNING):
        analyzer.generate_embedding("標題\n摘要")

    (line,) = _failure_lines(caplog)
    assert "非暫時性錯誤，不重試" in line
    assert "「標題」" in line
    assert "HTTPError: 400" in line


def test_failure_line_names_the_malformed_body(monkeypatch, caplog):
    class _NoVector(_Resp):
        def json(self):
            return {}

    _wire(monkeypatch, [_NoVector(200)])

    with caplog.at_level(logging.WARNING):
        analyzer.generate_embedding("標題")

    (line,) = _failure_lines(caplog)
    assert "KeyError: 'embedding'" in line


def test_failure_line_says_retries_ran_out(monkeypatch, caplog):
    _wire(monkeypatch, [_Resp(429, {"Retry-After": "1"})])

    with caplog.at_level(logging.WARNING):
        analyzer.generate_embedding("標題")

    (line,) = _failure_lines(caplog)
    assert "已重試 3 次" in line


def test_failure_line_says_budget_ran_out_with_numbers(monkeypatch, caplog):
    _wire(monkeypatch, [429])

    with caplog.at_level(logging.WARNING):
        analyzer.attach_embeddings(_articles(3))

    lines = _failure_lines(caplog)
    assert "預算不足（需 40 秒、剩 30 秒）" in lines[0] and "「t0」" in lines[0]
    assert "預算不足（需 40 秒、剩 0 秒）" in lines[1] and "「t1」" in lines[1]
    assert "預算不足（需 10 秒、剩 0 秒）" in lines[2] and "「t2」" in lines[2]


def test_retries_ran_out_wins_over_budget_when_both_hold(monkeypatch, caplog):
    """連線錯誤等 5/10/15 秒，預算 40 用剩 10；第 4 次要等 20——兩個條件同時成立。"""
    _wire(monkeypatch, [requests.ConnectionError("boom")])
    budget = analyzer._new_embed_retry_budget()
    budget["seconds"] = 40

    with caplog.at_level(logging.WARNING):
        analyzer.generate_embedding("標題", budget)

    (line,) = _failure_lines(caplog)
    assert "已重試 3 次" in line and "預算不足" not in line
    assert budget["skipped"] == 0, "重試用完的那篇不可算進「因預算不足不再重試」"


def test_failure_line_title_is_cut_at_30_chars(monkeypatch, caplog):
    _wire(monkeypatch, [400])

    with caplog.at_level(logging.WARNING):
        analyzer.generate_embedding("標" * 40 + "\n摘要")

    (line,) = _failure_lines(caplog)
    assert "「" + "標" * 30 + "」" in line


def test_retry_waits_share_a_60_second_budget_across_the_run(monkeypatch):
    _, sleeps = _wire(monkeypatch, [429])
    candidates = _articles(3)

    analyzer.attach_embeddings(candidates)

    assert sleeps == [10, 20, 10, 20], "第 1 篇 10+20，第 2 篇用完剩下的 30，第 3 篇不再等"
    assert sum(sleeps) == 60
    assert all(c["embedding"] is None for c in candidates)


def test_budget_is_per_run_not_global(monkeypatch):
    _, sleeps = _wire(monkeypatch, [429])

    analyzer.attach_embeddings(_articles(3))
    sleeps.clear()
    analyzer.attach_embeddings(_articles(3))

    assert sum(sleeps) == 60, "第二次 run 必須拿到完整預算"


def test_run_summary_reports_waited_seconds(monkeypatch, caplog):
    _wire(monkeypatch, [429, 200])

    with caplog.at_level(logging.WARNING):
        analyzer.attach_embeddings(_articles(2))

    summary = [r.getMessage() for r in caplog.records if "重試共等待" in r.getMessage()]
    assert summary == ["[embedding] 重試共等待 10/60 秒"]


def test_run_summary_says_when_budget_ran_out(monkeypatch, caplog):
    _wire(monkeypatch, [429])

    with caplog.at_level(logging.WARNING):
        analyzer.attach_embeddings(_articles(3))

    summary = [r.getMessage() for r in caplog.records if "重試共等待" in r.getMessage()]
    assert len(summary) == 1
    assert "60/60" in summary[0] and "不再重試" in summary[0]


def test_quiet_run_logs_no_retry_summary(monkeypatch, caplog):
    _wire(monkeypatch, [200])

    with caplog.at_level(logging.WARNING):
        analyzer.attach_embeddings(_articles(1))

    assert not [r for r in caplog.records if "[embedding]" in r.getMessage()]
