"""呼叫計數（spec 020 FR-009、SC-002）：只換 requests.post，數的是送出的請求，重試也算。
結尾那一行的文字照 contracts/dry-run.md，用字面值寫。"""
import logging
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src import analyzer, run_mode  # noqa: E402

DUMMY_KEY = "dummy-key-for-test"
OK_TEXT = {"candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}]}
OK_VECTOR = {"embedding": {"values": [0.1, 0.2]}}


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self.headers = {}
        self.text = ""
        self._body = body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)

    def json(self):
        return self._body


def _wire(monkeypatch, items, body):
    """items 依序被 post 取用：狀態碼或要丟出的例外；回傳每次 post 收到的 url。"""
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_KEY)
    monkeypatch.setattr(analyzer.time, "sleep", lambda _s: None)
    urls, queue = [], list(items)

    def fake_post(url, json=None, timeout=None, headers=None, **kwargs):
        urls.append(url)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Resp(item, body)

    monkeypatch.setattr(analyzer.requests, "post", fake_post)
    return urls


def _delta(before):
    after = analyzer.get_call_counts()
    return {k: after[k] - before[k] for k in ("generative", "embedding")}


def test_call_gemini_counts_every_attempt_including_retries(monkeypatch):
    urls = _wire(monkeypatch, [500, 503, 200], OK_TEXT)
    before = analyzer.get_call_counts()
    assert analyzer._call_gemini("prompt", DUMMY_KEY, retries=5) == "ok"
    assert len(urls) == 3
    assert _delta(before) == {"generative": 3, "embedding": 0}


def test_call_gemini_counts_an_attempt_that_raises(monkeypatch):
    """計數加在 requests.post 之前：連線錯誤的那一次也算一次送出。"""
    _wire(monkeypatch, [requests.ConnectionError("boom"), 200], OK_TEXT)
    before = analyzer.get_call_counts()
    assert analyzer._call_gemini("prompt", DUMMY_KEY, retries=5) == "ok"
    assert _delta(before) == {"generative": 2, "embedding": 0}


def test_call_gemini_that_gives_up_counts_all_retries(monkeypatch):
    _wire(monkeypatch, [500, 500], OK_TEXT)
    before = analyzer.get_call_counts()
    assert analyzer._call_gemini("prompt", DUMMY_KEY, retries=2) is None
    assert _delta(before) == {"generative": 2, "embedding": 0}


def test_generate_embedding_counts_every_attempt_including_retries(monkeypatch):
    urls = _wire(monkeypatch, [429, 200], OK_VECTOR)
    before = analyzer.get_call_counts()
    assert analyzer.generate_embedding("text") == [0.1, 0.2]
    assert urls == [analyzer.GEMINI_EMBED_URL] * 2
    assert _delta(before) == {"generative": 0, "embedding": 2}


def test_generate_embedding_non_transient_failure_counts_once(monkeypatch):
    _wire(monkeypatch, [400], OK_VECTOR)
    before = analyzer.get_call_counts()
    assert analyzer.generate_embedding("text") is None
    assert _delta(before) == {"generative": 0, "embedding": 1}


def test_attach_embeddings_counts_only_articles_that_send_a_request(monkeypatch):
    _wire(monkeypatch, [200, 200], OK_VECTOR)
    articles = [{"title": "a"}, {"title": "b", "embedding": [1.0, 0.0]}, {"title": "c"}]
    before = analyzer.get_call_counts()
    analyzer.attach_embeddings(articles)
    assert _delta(before) == {"generative": 0, "embedding": 2}


def test_counts_are_a_copy_not_the_live_counter(monkeypatch):
    _wire(monkeypatch, [200], OK_TEXT)
    snapshot = analyzer.get_call_counts()
    analyzer._call_gemini("prompt", DUMMY_KEY, retries=1)
    assert analyzer.get_call_counts()["generative"] == snapshot["generative"] + 1


def test_counting_logs_nothing_in_formal_mode(monkeypatch, caplog):
    monkeypatch.delenv("GARYU_RUN_MODE", raising=False)
    _wire(monkeypatch, [200], OK_TEXT)
    with caplog.at_level(logging.DEBUG, logger="src.analyzer"):
        analyzer._call_gemini("prompt", DUMMY_KEY, retries=1)
    assert caplog.records == []


@pytest.mark.parametrize("mode", ["dry-input", "dry-full"])
def test_end_line_text_in_dry_modes(monkeypatch, mode):
    monkeypatch.setenv("GARYU_RUN_MODE", mode)
    assert run_mode.end_line(0, 12) == "[不發布] 生成式 LLM 呼叫 0 次，embedding 呼叫 12 次"
    assert run_mode.end_line(21, 0) == "[不發布] 生成式 LLM 呼叫 21 次，embedding 呼叫 0 次"


@pytest.mark.parametrize("mode", ["dry-input", "dry-full"])
def test_stop_line_text_in_dry_modes(monkeypatch, mode):
    monkeypatch.setenv("GARYU_RUN_MODE", mode)
    assert run_mode.stop_line("FFXIV 分析") == "[不發布] 第一級在 FFXIV 分析 之前停下"
    assert run_mode.stop_line("熱點分析") == "[不發布] 第一級在 熱點分析 之前停下"


@pytest.mark.parametrize("raw", [None, ""])
def test_end_and_stop_lines_are_empty_in_formal_mode_and_log_nothing(monkeypatch, caplog, raw):
    if raw is None:
        monkeypatch.delenv("GARYU_RUN_MODE", raising=False)
    else:
        monkeypatch.setenv("GARYU_RUN_MODE", raw)
    with caplog.at_level(logging.DEBUG):
        assert run_mode.end_line(3, 4) == ""
        assert run_mode.stop_line("FFXIV 分析") == ""
    assert caplog.records == []


@pytest.mark.parametrize("call", [lambda: run_mode.end_line(0, 0), lambda: run_mode.stop_line("FFXIV 分析")])
def test_end_and_stop_lines_raise_on_unknown_mode(monkeypatch, call):
    monkeypatch.setenv("GARYU_RUN_MODE", "full")
    with pytest.raises(ValueError, match="dry-input"):
        call()
