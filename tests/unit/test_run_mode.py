"""執行模式（spec 020 FR-001、FR-007）：GARYU_RUN_MODE 的讀法與執行紀錄裡的固定行。
固定行的文字照 contracts/dry-run.md「執行紀錄裡的固定行」，這裡寫字面值，不引用模組的常數。
"""
import logging
import os
import subprocess
import sys

import pytest

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _REPO)

from src import run_mode  # noqa: E402

START_INPUT = "[不發布] 第一級：只到入選，不呼叫生成式 LLM"
START_FULL = "[不發布] 第二級：呼叫 LLM，不寫入、不發布"


@pytest.fixture
def unset(monkeypatch):
    monkeypatch.delenv("GARYU_RUN_MODE", raising=False)


def test_unset_is_formal(unset):
    assert run_mode.current() == run_mode.FORMAL
    assert run_mode.is_dry_run() is False


def test_empty_string_is_formal(monkeypatch):
    monkeypatch.setenv("GARYU_RUN_MODE", "")
    assert run_mode.current() == run_mode.FORMAL
    assert run_mode.is_dry_run() is False


def test_whitespace_only_strips_to_empty_and_is_formal(monkeypatch):
    monkeypatch.setenv("GARYU_RUN_MODE", " \t\n")
    assert run_mode.current() == run_mode.FORMAL
    assert run_mode.is_dry_run() is False


@pytest.mark.parametrize("raw, expected", [
    ("dry-input", "dry-input"),
    ("dry-full", "dry-full"),
    ("  dry-input\n", "dry-input"),
    ("\tdry-full ", "dry-full"),
])
def test_dry_levels_after_stripping(monkeypatch, raw, expected):
    monkeypatch.setenv("GARYU_RUN_MODE", raw)
    assert run_mode.current() == expected
    assert run_mode.is_dry_run() is True


def test_level_constants_are_the_workflow_values():
    assert (run_mode.DRY_INPUT, run_mode.DRY_FULL) == ("dry-input", "dry-full")
    assert run_mode.FORMAL not in ("dry-input", "dry-full", "")


@pytest.mark.parametrize("raw", ["full", "input", "DRY-FULL", "dry", "formal", "dry-input-x", "dry input"])
@pytest.mark.parametrize("call", ["current", "is_dry_run", "start_line"])
def test_unknown_value_raises_with_value_and_both_known_values(monkeypatch, raw, call):
    monkeypatch.setenv("GARYU_RUN_MODE", raw)
    with pytest.raises(ValueError) as exc:
        getattr(run_mode, call)()
    msg = str(exc.value)
    assert repr(raw) in msg, "訊息要帶不認得的那個值（加引號，才分得出 'dry' 與 dry-input）"
    assert "dry-input" in msg and "dry-full" in msg


def test_unknown_value_raises_from_skip_write_line(monkeypatch):
    monkeypatch.setenv("GARYU_RUN_MODE", "full")
    with pytest.raises(ValueError):
        run_mode.skip_write_line("upsert_articles", 3)


@pytest.mark.parametrize("raw, line", [("dry-input", START_INPUT), ("dry-full", START_FULL)])
def test_start_line_per_level(monkeypatch, raw, line):
    monkeypatch.setenv("GARYU_RUN_MODE", raw)
    assert run_mode.start_line() == line


@pytest.mark.parametrize("raw", ["dry-input", "dry-full"])
def test_skip_write_line_with_count(monkeypatch, raw):
    monkeypatch.setenv("GARYU_RUN_MODE", raw)
    assert run_mode.skip_write_line("upsert_articles", 3) == "[不發布] 略過 upsert_articles：3 筆"
    assert run_mode.skip_write_line("mark_articles_analyzed", 0) == "[不發布] 略過 mark_articles_analyzed：0 筆"


@pytest.mark.parametrize("raw", ["dry-input", "dry-full"])
def test_skip_write_line_without_count_says_unknown(monkeypatch, raw):
    monkeypatch.setenv("GARYU_RUN_MODE", raw)
    assert run_mode.skip_write_line("expire_buffer_articles") == (
        "[不發布] 略過 expire_buffer_articles：沒有查資料庫，筆數未知"
    )


@pytest.mark.parametrize("raw", [None, ""])
def test_formal_mode_lines_are_empty_and_nothing_is_logged(monkeypatch, caplog, raw):
    if raw is None:
        monkeypatch.delenv("GARYU_RUN_MODE", raising=False)
    else:
        monkeypatch.setenv("GARYU_RUN_MODE", raw)
    with caplog.at_level(logging.DEBUG):
        assert run_mode.start_line() == ""
        assert run_mode.skip_write_line("upsert_articles", 3) == ""
        assert run_mode.skip_write_line("expire_buffer_articles") == ""
    assert caplog.records == []


def test_only_run_mode_reads_the_variable():
    """預設值只定義在 src/run_mode.py：其他進版控的程式（測試除外）不得自己讀 GARYU_RUN_MODE。"""
    out = subprocess.run(
        ["git", "-C", _REPO, "ls-files", "-z", "*.py"],
        capture_output=True, text=True, check=True,
    ).stdout
    files = [p for p in out.split("\0") if p and not p.startswith("tests/")]
    assert "src/storage.py" in files, "清單取錯了：連 src/storage.py 都沒列到"
    readers = []
    for rel in files:
        with open(os.path.join(_REPO, rel), encoding="utf-8") as fh:
            if "GARYU_RUN_MODE" in fh.read():
                readers.append(rel)
    assert readers in ([], ["src/run_mode.py"]), f"這些檔自己讀 GARYU_RUN_MODE：{readers}"
