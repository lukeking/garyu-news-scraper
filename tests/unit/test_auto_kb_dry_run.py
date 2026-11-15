"""術語收錄的不寫入模式（spec 020 FR-003、FR-004、FR-007、FR-009、FR-010）：跑真的 main()，只換資料庫的 client 與 Gemini 的 HTTP。
第二級的輸入由真的 _dump_analysis_output 照 FFXIV 的站台目錄寫出來；固定行與產物欄位用字面值寫。"""
import copy
import json
import logging
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import auto_kb  # noqa: E402
from src import publisher  # noqa: E402
from src.pipeline.ffxiv import FFXIVCategory  # noqa: E402

START = {"dry-input": "[不發布] 第一級：只到入選，不呼叫生成式 LLM",
         "dry-full": "[不發布] 第二級：呼叫 LLM，不寫入、不發布"}
STOP = "[不發布] 第一級在 術語收錄 之前停下"
INPUT_HEAD = "[不發布] 術語收錄的輸入："
WOULD_WRITE = "[不發布] 術語收錄：會寫入 {} 條，沒有寫入"
PATCH_SKIP = "[不發布] 略過 articles 的內聯修補：{} 筆"
DRY_DONE = "Auto-KB 完成：沒有寫入術語庫與文章，{} 個術語仍待審查"
NO_UNKNOWN_DRY = "沒有未知術語需要解析，跳過 Gemini"
NO_UNKNOWN_FORMAL = "沒有未知術語需要解析，跳過 Gemini；Step 5 的修補仍會執行"
POOL_FORMAL = "術語已顯示於 FFXIV 頁面術語池，等待知識庫收錄。"
POOL_DRY = "正式執行時這些術語會顯示於 FFXIV 頁面術語池，等待知識庫收錄。"

KB = [{"jp_term": "ララ", "tw_term": "拉拉菲爾族"}, {"jp_term": "エオルゼア", "tw_term": "艾歐澤亞"}]
THIS_RUN = [
    {"title": "甲", "link": "https://f/1", "source": "s", "analysis": {"summary": "新任務 [[絶バハムート討滅戦]] 與 [[ララ]] 角色"}},
    {"title": "乙", "link": "https://f/2", "source": "s", "analysis": {"summary": "[[オメガ]] 與 [[spiky boy]]"}},
    {"title": "丙", "link": "https://f/3", "source": "s", "analysis": {"summary": "沒有標記"}},
    {"title": "丁", "link": "https://f/4", "source": "s", "analysis": {"summary": "[[某個沒人知道的詞]] 的後續"}},
]
DB_PENDING = [{"id": 99, "analysis": {"summary": "上週的 [[資料庫裡的詞]]"}}]
REPLY = [
    {"jp_term": "絶バハムート討滅戦", "tw_term": "絕巴哈姆特討滅戰", "en_term": "UCoB", "category": "副本", "notes": "4.11（2018）"},
    {"jp_term": "エオルゼア", "tw_term": "伊歐澤亞"},  # 術語庫已有：跳過
    {"jp_term": "", "tw_term": "沒有日文"},  # 缺欄：跳過
    {"jp_term": "オメガ", "tw_term": "歐米茄"},
]
ENTRIES = [
    {"jp_term": "絶バハムート討滅戦", "tw_term": "絕巴哈姆特討滅戰", "en_term": "UCoB", "category": "副本",
     "notes": "4.11（2018）", "auto_generated": True},
    {"jp_term": "オメガ", "tw_term": "歐米茄", "en_term": "", "category": "", "notes": "", "auto_generated": True},
]
ENTRY_LINES = ["  • 絶バハムート討滅戦 → 絕巴哈姆特討滅戰｜en_term：UCoB｜category：副本｜notes：4.11（2018）",
               "  • オメガ → 歐米茄｜en_term：｜category：｜notes："]
UNKNOWN = ["オメガ", "某個沒人知道的詞", "絶バハムート討滅戦"]


class _Resp:
    def __init__(self, text=None, status_code=200):
        self.status_code, self._text = status_code, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": self._text}]}}]}


def _ok(entries=REPLY):
    return _Resp(json.dumps(entries, ensure_ascii=False))


class _Query:
    def __init__(self, db, table, op, payload=None):
        self.db, self.table, self.op, self.payload = db, table, op, payload

    def eq(self, _col, _val):
        return self

    def execute(self):
        self.db.calls.append((self.table, self.op, self.payload))
        if (self.table, self.op) == ("knowledge_base", "select"):
            if self.db.kb is None:
                raise RuntimeError("讀不到術語庫")
            return SimpleNamespace(data=copy.deepcopy(self.db.kb))
        if (self.table, self.op) == ("articles", "select"):
            return SimpleNamespace(data=copy.deepcopy(self.db.articles))
        return SimpleNamespace(data=[])


class _DB:
    """supabase client 的替身：每次 execute 記成 (表, 動作, 內容)；kb 是 None 時讀術語庫丟錯。"""

    def __init__(self, kb, articles):
        self.kb, self.articles, self.calls = kb, articles, []

    def table(self, name):
        return SimpleNamespace(
            select=lambda _cols: _Query(self, name, "select"),
            insert=lambda row: _Query(self, name, "insert", row),
            update=lambda patch: _Query(self, name, "update", patch),
        )


def _ops(db, op):
    return [(table, payload) for table, o, payload in db.calls if o == op]


def _end(gen):
    return f"[不發布] 生成式 LLM 呼叫 {gen} 次，embedding 呼叫 0 次"


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_input(articles):
    publisher._dump_analysis_output(copy.deepcopy(articles), "2026-W46", FFXIVCategory.output_dir)


@pytest.fixture
def h(monkeypatch, tmp_path, caplog):
    h = SimpleNamespace(kb=KB, articles=DB_PENDING, replies=[_ok()], db=None, clients=0, queue=[], posts=[],
                        gemini_calls=[], out=tmp_path / "analysis-output")
    h.input = h.out / "ffxiv_articles.json"
    h.entries_file = h.out / "auto_kb_entries.json"

    def create_client(url, key):
        h.clients += 1
        return h.db

    def post(url, json=None, headers=None, timeout=None):
        h.posts.append(url)
        return h.queue.pop(0)

    monkeypatch.setitem(sys.modules, "supabase", SimpleNamespace(create_client=create_client))
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(post=post))
    monkeypatch.setattr(auto_kb.time, "sleep", lambda _s: None)
    real = auto_kb.call_gemini

    def spy(terms, *args, **kwargs):
        h.gemini_calls.append(sorted(terms))
        return real(terms, *args, **kwargs)

    monkeypatch.setattr(auto_kb, "call_gemini", spy)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-not-a-real-key")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-not-a-real-key")
    monkeypatch.setenv("ANALYSIS_OUTPUT_DIR", str(h.out))
    monkeypatch.setenv("GARYU_RUN_MODE", "dry-full")
    _write_input(THIS_RUN)

    def run(mode):
        if mode is None:
            monkeypatch.delenv("GARYU_RUN_MODE", raising=False)
        else:
            monkeypatch.setenv("GARYU_RUN_MODE", mode)
        h.db = _DB(copy.deepcopy(h.kb), copy.deepcopy(h.articles))
        h.clients, h.queue, h.exit = 0, list(h.replies), "returned"
        h.posts.clear()
        h.gemini_calls.clear()
        caplog.clear()
        with caplog.at_level(logging.INFO):
            try:
                auto_kb.main()
            except SystemExit as exc:
                h.exit = exc.code
            finally:
                h.msgs = [r.getMessage() for r in caplog.records]
        return h.msgs

    h.run = run
    return h


# ── 第二級 ─────────────────────────────────────────────────────

def test_dry_full_sends_this_runs_markers_and_writes_nothing(h):
    msgs = h.run("dry-full")
    assert _ops(h.db, "insert") == [], "不發布時不寫 knowledge_base"
    assert _ops(h.db, "update") == [], "不發布時不改 articles"
    assert h.gemini_calls == [UNKNOWN], "未知術語取自這次的分析輸出，不取資料庫裡待處理的 articles"
    assert h.db.calls == [("knowledge_base", "select", None)], "術語庫照常讀，其他什麼都不碰"
    assert (len(h.posts), h.exit) == (1, "returned")
    assert msgs[0] == START["dry-full"]
    assert f"{INPUT_HEAD}{h.input} 的 4 篇，其中 3 篇帶標記" in msgs
    i = msgs.index(WOULD_WRITE.format(2))
    assert msgs[i + 1:i + 3] == ENTRY_LINES
    assert msgs.count(PATCH_SKIP.format(2)) == 1
    assert msgs[-2:] == [DRY_DONE.format(1), _end(1)]


def test_dry_full_leaves_the_entries_it_would_write_in_the_analysis_output_dir(h):
    msgs = h.run("dry-full")
    assert f"術語收錄會寫入的條目：寫入 {h.entries_file}（2 條）" in msgs
    data = _read(h.entries_file)
    assert list(data) == ["run_mode", "unknown_terms", "entry_count", "entries"]
    assert data == {"run_mode": "dry-full", "unknown_terms": UNKNOWN, "entry_count": 2, "entries": ENTRIES}


def test_dry_full_does_not_say_added_patched_or_shown(h):
    msgs = h.run("dry-full")
    assert not [m for m in msgs if m.startswith("[KB AUTO] 新增術語")]
    assert not [m for m in msgs if "已內聯修補術語" in m]
    assert not [m for m in msgs if m.startswith("Auto-KB 完成：新增")]
    assert POOL_FORMAL not in msgs
    assert msgs.index("  • 某個沒人知道的詞") < msgs.index(POOL_DRY)


def test_dry_full_would_write_what_formal_writes_from_the_same_articles(h):
    h.articles = [{"id": i, "analysis": a["analysis"]} for i, a in enumerate(THIS_RUN, 1)]
    h.run(None)
    formal_inserts = [row for _, row in _ops(h.db, "insert")]
    formal_patches = len(_ops(h.db, "update"))
    assert (formal_inserts, formal_patches) == (ENTRIES, 2)
    msgs = h.run("dry-full")
    assert _read(h.entries_file)["entries"] == formal_inserts
    assert PATCH_SKIP.format(formal_patches) in msgs


def test_closing_line_counts_every_request_including_retries(h):
    h.replies = [_Resp(status_code=503), _ok()]
    msgs = h.run("dry-full")
    assert (len(h.gemini_calls), len(h.posts)) == (1, 2)
    assert WOULD_WRITE.format(2) in msgs
    assert msgs[-1] == _end(2)


def test_a_failed_gemini_call_says_so_and_would_write_nothing(h):
    h.replies = [_Resp("這不是 JSON")] * 3
    msgs = h.run("dry-full")
    assert "Gemini 所有重試均失敗，跳過本次 KB 擴充" in msgs
    i = msgs.index(WOULD_WRITE.format(0))
    assert not msgs[i + 1].startswith("  • ")
    assert _read(h.entries_file)["entry_count"] == 0
    assert msgs[-1] == _end(3)


def test_known_markers_only_skip_gemini_and_still_count_the_patch(h):
    _write_input([THIS_RUN[2], {"title": "戊", "link": "https://f/5", "source": "s",
                                "analysis": {"summary": "[[ララ]] 與 [[spiky boy]]"}}])
    msgs = h.run("dry-full")
    assert f"{INPUT_HEAD}{h.input} 的 2 篇，其中 1 篇帶標記" in msgs
    assert h.gemini_calls == [] and h.posts == []
    assert NO_UNKNOWN_DRY in msgs and NO_UNKNOWN_FORMAL not in msgs
    assert WOULD_WRITE.format(0) in msgs and PATCH_SKIP.format(1) in msgs
    assert POOL_DRY not in msgs
    assert msgs[-2:] == [DRY_DONE.format(0), _end(0)]


# ── 第二級的輸入讀不到 ─────────────────────────────────────────

def test_unset_output_dir_says_so_and_does_not_fall_back_to_the_database(h, monkeypatch):
    monkeypatch.delenv("ANALYSIS_OUTPUT_DIR")
    msgs = h.run("dry-full")
    assert f"{INPUT_HEAD}沒有這次的 FFXIV 分析輸出（未設 ANALYSIS_OUTPUT_DIR）" in msgs
    assert h.db.calls == [("knowledge_base", "select", None)]
    assert h.gemini_calls == []
    assert NO_UNKNOWN_DRY in msgs and WOULD_WRITE.format(0) in msgs
    assert "術語收錄會寫入的條目：未設 ANALYSIS_OUTPUT_DIR，不寫檔" in msgs
    assert PATCH_SKIP.format(0) in msgs
    assert msgs[-2:] == [DRY_DONE.format(0), _end(0)]


def test_missing_input_file_says_so_and_still_leaves_an_empty_artifact(h):
    h.input.unlink()
    msgs = h.run("dry-full")
    assert f"{INPUT_HEAD}沒有這次的 FFXIV 分析輸出（找不到 {h.input}）" in msgs
    assert h.db.calls == [("knowledge_base", "select", None)]
    assert h.gemini_calls == []
    assert _read(h.entries_file)["entry_count"] == 0
    assert msgs[-1] == _end(0)


def test_unreadable_input_file_warns_and_sends_nothing(h):
    h.input.write_text("{", encoding="utf-8")
    msgs = h.run("dry-full")
    assert [m for m in msgs if m.startswith(f"{INPUT_HEAD}沒有這次的 FFXIV 分析輸出（讀不了 {h.input}：")]
    assert h.db.calls == [("knowledge_base", "select", None)]
    assert h.gemini_calls == []
    assert msgs[-1] == _end(0)


# ── 第一級 ─────────────────────────────────────────────────────

def test_dry_input_stops_before_term_collection_without_reading_anything(h):
    msgs = h.run("dry-input")
    assert h.gemini_calls == [], "第一級不呼叫生成式 LLM"
    assert (h.clients, h.posts, h.exit) == (0, [], "returned")
    assert msgs == [START["dry-input"], STOP, _end(0)]
    assert not h.entries_file.exists()


# ── 每一條出口都印結尾那一行；模式先驗 ──────────────────────────

@pytest.mark.parametrize("unset, line", [
    ("SUPABASE_URL", "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 未設定，中止"),
    ("GEMINI_API_KEY", "GEMINI_API_KEY 未設定，中止"),
])
def test_missing_environment_exit_still_prints_the_closing_line(h, monkeypatch, unset, line):
    monkeypatch.delenv(unset)
    msgs = h.run("dry-full")
    assert (h.exit, h.clients) == (0, 0)
    assert msgs == [START["dry-full"], line, _end(0)]


def test_unreadable_knowledge_base_stops_and_prints_the_closing_line(h):
    h.kb = None
    msgs = h.run("dry-full")
    assert h.db.calls == [("knowledge_base", "select", None)]
    assert h.gemini_calls == []
    assert h.exit == 0
    assert msgs == [START["dry-full"], "無法讀取 knowledge_base 表格：讀不到術語庫", _end(0)]


def test_a_run_that_raises_after_a_request_still_counts_it(h):
    h.replies = [_Resp('["不是物件"]')]
    with pytest.raises(AttributeError):
        h.run("dry-full")
    assert _ops(h.db, "insert") == []
    assert (h.msgs[0], h.msgs[-1]) == (START["dry-full"], _end(1))


def test_unknown_mode_fails_before_reading_anything(h):
    with pytest.raises(ValueError, match="dry-input"):
        h.run("full")
    assert (h.clients, h.gemini_calls, h.msgs) == (0, [], [])


# ── 正式模式 ───────────────────────────────────────────────────

def test_formal_mode_reads_the_database_not_the_output_and_says_so_as_before(h):
    _write_input([{"title": "己", "link": "https://f/6", "source": "s", "analysis": {"summary": "[[只在檔案裡的詞]]"}}])
    h.articles = DB_PENDING + [{"id": i, "analysis": a["analysis"]} for i, a in enumerate(THIS_RUN, 1)]
    msgs = h.run(None)
    assert h.gemini_calls == [sorted(UNKNOWN + ["資料庫裡的詞"])]
    assert [row for _, row in _ops(h.db, "insert")] == ENTRIES
    assert [table for table, _ in _ops(h.db, "update")] == ["articles", "articles"]
    assert not [m for m in msgs if m.startswith("[不發布]")]
    assert "" not in msgs, "正式模式不該印空行"
    assert "[KB AUTO] 新增術語：絶バハムート討滅戦 → 絕巴哈姆特討滅戰" in msgs
    assert "[KB AUTO] 新增術語：オメガ → 歐米茄" in msgs
    assert ["文章 1 已內聯修補術語", "文章 2 已內聯修補術語"] == [m for m in msgs if "已內聯修補術語" in m]
    assert POOL_FORMAL in msgs and POOL_DRY not in msgs
    assert not h.entries_file.exists()
    assert h.exit == "returned"
    assert msgs[-1] == "Auto-KB 完成：新增 2 個術語，2 個術語仍待審查"


def test_the_script_finds_src_when_only_its_own_directory_is_on_the_path(tmp_path):
    """auto-kb.yml 跑 python scripts/auto_kb.py：只有 scripts/ 在 sys.path 上。只 import、不呼叫 main()，dotenv 換掉不讀 .env。"""
    code = ("import sys, types; sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **k: False); "
            f"sys.path.insert(0, {os.path.join(_REPO, 'scripts')!r}); import auto_kb; "
            "print(auto_kb.run_mode.__name__, auto_kb.artifacts.__name__)")
    out = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert (out.returncode, out.stdout.split()) == (0, ["src.run_mode", "src.artifacts"]), out.stderr


def test_formal_mode_without_unknown_terms_keeps_its_message(h):
    h.articles = [{"id": 7, "analysis": {"summary": "[[ララ]] 的故事"}}]
    msgs = h.run(None)
    assert h.gemini_calls == []
    assert NO_UNKNOWN_FORMAL in msgs
    assert _ops(h.db, "update") == [("articles", {"analysis": {"summary": "拉拉菲爾族 的故事"}})]
    assert msgs[-1] == "Auto-KB 完成：新增 0 個術語，0 個術語仍待審查"
