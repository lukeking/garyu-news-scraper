"""產物寫檔的共用函式（spec 020 FR-008）：src/artifacts.py 的 write_json，以及三個經過它的呼叫點。
訊息與檔案內容用字面值寫。"""
import logging
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src import artifacts, publisher  # noqa: E402
from src import filter as filter_mod  # noqa: E402
from src.pipeline.traffic import TrafficCategory  # noqa: E402

VAR = "ARTIFACT_TEST_PATH"
CALLER = logging.getLogger("test_artifacts.caller")
DATA = {"標題": "機車路權", "when": datetime(2026, 11, 15, 4, 0, tzinfo=timezone.utc), "n": [1, 2]}
TEXT = '{\n "標題": "機車路權",\n "when": "2026-11-15 04:00:00+00:00",\n "n": [\n  1,\n  2\n ]\n}'


def _records(caplog):
    return [(r.name, r.levelno, r.getMessage()) for r in caplog.records]


def _write(caplog, filename=None, summary="3 篇"):
    with caplog.at_level(logging.INFO, logger=CALLER.name):
        artifacts.write_json(CALLER, "標籤", VAR, lambda: (DATA, summary), filename)
    return _records(caplog)


# ── 路徑變數沒設 ───────────────────────────────────────────────

@pytest.mark.parametrize("value", [None, "", "   "])
@pytest.mark.parametrize("filename", [None, "out.json"])
def test_unset_or_blank_variable_says_so_and_builds_nothing(monkeypatch, tmp_path, caplog, value, filename):
    if value is None:
        monkeypatch.delenv(VAR, raising=False)
    else:
        monkeypatch.setenv(VAR, value)
    monkeypatch.chdir(tmp_path)
    built = []
    with caplog.at_level(logging.INFO, logger=CALLER.name):
        artifacts.write_json(CALLER, "標籤", VAR, lambda: built.append(1) or (DATA, "x"), filename)
    assert _records(caplog) == [(CALLER.name, logging.INFO, f"標籤：未設 {VAR}，不寫檔")]
    assert built == [], "沒設路徑時不該組內容"
    assert list(tmp_path.iterdir()) == []


# ── 目錄與檔案路徑 ─────────────────────────────────────────────

def test_directory_variable_creates_the_directory_and_writes_the_name_inside(monkeypatch, tmp_path, caplog):
    target = tmp_path / "a" / "b"
    monkeypatch.setenv(VAR, f"  {target}  ")
    records = _write(caplog, "out.json")
    path = target / "out.json"
    assert path.read_bytes() == TEXT.encode("utf-8")
    assert sorted(p.name for p in target.iterdir()) == ["out.json"]
    assert records == [(CALLER.name, logging.INFO, f"標籤：寫入 {path}（3 篇）")]


def test_directory_variable_reuses_an_existing_directory(monkeypatch, tmp_path, caplog):
    (tmp_path / "keep.txt").write_text("留著", encoding="utf-8")
    monkeypatch.setenv(VAR, str(tmp_path))
    records = _write(caplog, "out.json", summary="1 篇，入選 0 篇")
    assert (tmp_path / "out.json").read_text(encoding="utf-8") == TEXT
    assert (tmp_path / "keep.txt").read_text(encoding="utf-8") == "留著"
    assert records == [(CALLER.name, logging.INFO, f"標籤：寫入 {tmp_path / 'out.json'}（1 篇，入選 0 篇）")]


def test_file_variable_writes_that_path(monkeypatch, tmp_path, caplog):
    path = tmp_path / "pool.json"
    monkeypatch.setenv(VAR, f" {path} ")
    records = _write(caplog)
    assert path.read_bytes() == TEXT.encode("utf-8")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pool.json"]
    assert records == [(CALLER.name, logging.INFO, f"標籤：寫入 {path}（3 篇）")]


# ── 寫不進去 ───────────────────────────────────────────────────

def test_file_variable_does_not_create_the_parent_and_warns(monkeypatch, tmp_path, caplog):
    path = tmp_path / "missing" / "pool.json"
    monkeypatch.setenv(VAR, str(path))
    records = _write(caplog)
    assert not (tmp_path / "missing").exists()
    assert records == [(CALLER.name, logging.WARNING,
                        f"標籤：寫入 {path} 失敗（[Errno 2] No such file or directory: '{path}'）")]


def test_directory_that_cannot_be_created_warns_and_does_not_raise(monkeypatch, tmp_path, caplog):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv(VAR, str(blocker))
    records = _write(caplog, "out.json")
    assert blocker.read_text(encoding="utf-8") == "x"
    assert records == [(CALLER.name, logging.WARNING,
                        f"標籤：寫入 {blocker / 'out.json'} 失敗（[Errno 17] File exists: '{blocker}'）")]


# ── 三個呼叫點都經過它 ─────────────────────────────────────────

ARTICLE = {"title": "甲", "link": "https://x/1", "source": "s", "summary": "摘要", "analysis": {"summary": "分析"}}


class _Untouchable(dict):
    def get(self, *args, **kwargs):
        raise AssertionError("內容只該在 build 裡組，不該在呼叫 write_json 之前就讀文章")


def _call_the_three(monkeypatch, tmp_path, article):
    calls = []

    def record(logger, label, env_var, build, filename=None):
        calls.append((logger.name, label, env_var, filename))

    monkeypatch.setattr(artifacts, "write_json", record)
    monkeypatch.setenv("GARYU_RUN_MODE", "dry-full")
    monkeypatch.setenv("FFXIV_POOL_DUMP", str(tmp_path / "pool.json"))
    monkeypatch.setenv("TRAFFIC_POOL_DIR", str(tmp_path / "traffic-pool"))
    monkeypatch.setenv("ANALYSIS_OUTPUT_DIR", str(tmp_path / "analysis-output"))
    cat = TrafficCategory()
    monkeypatch.setattr(cat, "_buffer_max_age_weeks", lambda: 8)
    filter_mod._dump_ffxiv_pool([article], 1)
    cat._dump_collected([article])
    publisher._dump_analysis_output([article], "2026-W46", "pages/ffxiv")
    return calls


def test_the_three_call_sites_each_call_write_json_once_and_write_nothing_themselves(monkeypatch, tmp_path):
    calls = _call_the_three(monkeypatch, tmp_path, ARTICLE)
    assert (calls, sorted(p.name for p in tmp_path.rglob("*"))) == ([
        ("src.filter", "FFXIV 候選池內容", "FFXIV_POOL_DUMP", None),
        ("src.pipeline.traffic", "交通候選清單", "TRAFFIC_POOL_DIR", "collected.json"),
        ("src.publisher", "逐篇分析全文", "ANALYSIS_OUTPUT_DIR", "ffxiv_articles.json"),
    ], [])


def test_the_three_call_sites_build_their_content_only_inside_build(monkeypatch, tmp_path):
    assert len(_call_the_three(monkeypatch, tmp_path, _Untouchable(ARTICLE))) == 3
