"""不發布模式下 src/storage.py 的寫入出口（spec 020 FR-004、FR-007、FR-010；research D1）。
寫入函式從原始碼列舉，不手寫清單：多一個寫入函式而沒有不發布的案例，這裡會紅。邊界只換 Supabase client。
"""
import ast
import logging
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import src.storage as storage  # noqa: E402

_SOURCE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "src", "storage.py")
with open(_SOURCE_PATH, encoding="utf-8") as _fh:
    _SOURCE = _fh.read()

_WRITE_METHODS = ("upsert", "insert", "update", "delete")

# research.md「現況」列的 5 個
_RESEARCH_FIVE = {
    "upsert_articles", "upsert_traffic_buffer", "expire_buffer_articles",
    "mark_articles_analyzed", "upsert_hot_topic_report",
}


def _write_functions(source: str) -> set:
    """原始碼裡呼叫了寫入方法（不論接收者）的每個函式名。"""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr in _WRITE_METHODS):
                found.add(node.name)
    return found


_DERIVED = sorted(_write_functions(_SOURCE))

_ARTICLES = [
    {"title": "a1", "link": "https://x/1", "source": "s"},
    {"title": "a2", "link": "https://x/2", "source": "s"},
    {"title": "a3", "link": "https://x/3", "source": "s"},
]
_LINKS = ["https://x/1", "https://x/2"]
_REPORT = {
    "week_start_date": "2026-11-09", "topic_label": "t", "report_text": "r",
    "source_article_links": _LINKS,
}

# 名字 → (呼叫參數, 不發布時的那一行, 不發布時的回傳值)
_CASES = {
    "upsert_articles": ((_ARTICLES, "2026-W46"), "[不發布] 略過 upsert_articles：3 筆", 0),
    "upsert_traffic_buffer": ((_ARTICLES, "2026-W46"), "[不發布] 略過 upsert_traffic_buffer：3 筆", 0),
    "expire_buffer_articles": ((), "[不發布] 略過 expire_buffer_articles：沒有查資料庫，筆數未知", 0),
    "mark_articles_analyzed": ((_LINKS,), "[不發布] 略過 mark_articles_analyzed：2 筆", 0),
    "upsert_hot_topic_report": ((_REPORT,), "[不發布] 略過 upsert_hot_topic_report：1 筆", None),
}


def _fake_client(monkeypatch):
    client = MagicMock()
    get = MagicMock(return_value=client)
    monkeypatch.setattr(storage, "_get_client", get)
    monkeypatch.setattr(storage, "_client", client)
    return get, client


def _messages(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "src.storage"]


def _case(name):
    assert name in _CASES, f"{name} 會寫入資料庫，卻沒有不發布的測試案例"
    return _CASES[name]


def test_write_functions_are_exactly_the_five_in_research():
    assert set(_DERIVED) == _RESEARCH_FIVE


def test_enumeration_catches_an_unguarded_writer():
    fake = (
        "\n\ndef sneaky_write(rows):\n"
        "    client = _get_client()\n"
        "    client.table('articles').insert(rows).execute()\n"
    )
    assert _write_functions(_SOURCE + fake) == _RESEARCH_FIVE | {"sneaky_write"}


def test_enumeration_ignores_readers():
    reader = "def reader():\n    return _get_client().table('articles').select('*').execute()\n"
    assert _write_functions(reader) == set()


@pytest.mark.parametrize("mode", ["dry-input", "dry-full"])
@pytest.mark.parametrize("name", _DERIVED)
def test_dry_mode_never_touches_the_client(name, mode, monkeypatch, caplog):
    args, line, expected = _case(name)
    monkeypatch.setenv("GARYU_RUN_MODE", mode)
    get, client = _fake_client(monkeypatch)
    with caplog.at_level(logging.DEBUG, logger="src.storage"):
        result = getattr(storage, name)(*args)
    assert get.call_count == 0
    assert client.mock_calls == []
    assert (type(result), result) == (type(expected), expected)
    assert _messages(caplog) == [line]


@pytest.mark.parametrize("name", ["upsert_articles", "upsert_traffic_buffer", "mark_articles_analyzed"])
def test_dry_mode_checks_before_the_empty_input_early_return(name, monkeypatch, caplog):
    monkeypatch.setenv("GARYU_RUN_MODE", "dry-full")
    get, client = _fake_client(monkeypatch)
    args = ([], "2026-W46") if name != "mark_articles_analyzed" else ([],)
    with caplog.at_level(logging.DEBUG, logger="src.storage"):
        assert getattr(storage, name)(*args) == 0
    assert get.call_count == 0
    assert _messages(caplog) == [f"[不發布] 略過 {name}：0 筆"]


@pytest.mark.parametrize("name", _DERIVED)
def test_unknown_mode_raises_before_the_client(name, monkeypatch):
    args, _, _ = _case(name)
    monkeypatch.setenv("GARYU_RUN_MODE", "dry")
    get, client = _fake_client(monkeypatch)
    with pytest.raises(ValueError, match="dry-input"):
        getattr(storage, name)(*args)
    assert get.call_count == 0
    assert client.mock_calls == []


@pytest.mark.parametrize("name", _DERIVED)
def test_formal_mode_still_writes(name, monkeypatch, caplog):
    args, _, _ = _case(name)
    monkeypatch.delenv("GARYU_RUN_MODE", raising=False)
    get, client = _fake_client(monkeypatch)
    with caplog.at_level(logging.DEBUG, logger="src.storage"):
        getattr(storage, name)(*args)
    assert get.call_count == 1
    table = client.table.return_value
    assert any(getattr(table, m).called for m in _WRITE_METHODS), "正式模式沒有呼叫寫入方法"
    assert not [m for m in _messages(caplog) if m.startswith("[不發布]")]
