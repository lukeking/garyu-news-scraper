"""
`scripts/auto_kb.py` 的 Step 5（內聯修補）測試。

**為什麼是這幾條**：2026-08-31 有一個 bug 連著兩個 PR 都沒被攔下來——
Step 2 的「沒有未知術語 → `sys.exit(0)`」讓 Step 5 永遠到不了，而 Step 5 後來長出
兩個獨立於 Gemini 的職責（修補全 KB 的 jp→tw、拆 `IGNORED_MARKERS` 的括號），
那兩者恰好會把未知集清空，於是自己觸發早退、把自己關在門外。

那是一個**控制流** bug，不是邏輯 bug。當時的驗證方式是分別乾跑 Step 2 與 Step 5
的邏輯，兩邊都「正確」——但沒有任何東西模擬它們之間的 `sys.exit`。
所以這裡刻意跑**真正的 `main()`**，用假 client 攔住寫入，而不是重寫一份邏輯：
重寫的那份不會有早退，於是永遠測不到這個 bug。
"""
import json
import os
import sys
import types

import pytest

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import auto_kb  # noqa: E402


# ── 假 supabase client：只支援 auto_kb 實際用到的那幾條鏈 ──────────────────

class _Query:
    def __init__(self, table, op, payload=None):
        self.table, self.op, self.payload = table, op, payload
        self.filters = {}

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def execute(self):
        return types.SimpleNamespace(data=self.table._run(self))


class _Table:
    def __init__(self, db, name):
        self.db, self.name = db, name

    def select(self, _cols):
        return _Query(self, "select")

    def insert(self, rows):
        return _Query(self, "insert", rows)

    def update(self, patch):
        return _Query(self, "update", patch)

    def _run(self, q):
        if self.name == "knowledge_base":
            if q.op == "select":
                return [dict(r) for r in self.db.kb]
            if q.op == "insert":
                rows = q.payload if isinstance(q.payload, list) else [q.payload]
                self.db.kb.extend(rows)
                self.db.inserted.extend(rows)
                return rows
        if self.name == "articles":
            if q.op == "select":
                return [dict(a) for a in self.db.articles]
            if q.op == "update":
                aid = q.filters.get("id")
                for a in self.db.articles:
                    if a["id"] == aid:
                        a.update(q.payload)
                self.db.updates.append((aid, q.payload))
                return []
        raise AssertionError(f"未預期的呼叫：{self.name}.{q.op}")


class _FakeDB:
    def __init__(self, kb, articles):
        self.kb, self.articles = kb, articles
        self.updates, self.inserted = [], []

    def table(self, name):
        return _Table(self, name)


@pytest.fixture
def run_main(monkeypatch):
    """跑真正的 main()，回傳假 DB 供斷言。gemini_calls 記錄它有沒有呼叫 Gemini。"""
    def _run(kb, articles):
        db = _FakeDB(kb, articles)
        monkeypatch.setitem(
            sys.modules, "supabase",
            types.SimpleNamespace(create_client=lambda url, key: db),
        )
        monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-not-a-real-key")
        monkeypatch.setenv("GEMINI_API_KEY", "fake-not-a-real-key")

        calls = []
        monkeypatch.setattr(
            auto_kb, "call_gemini",
            lambda terms, *a, **k: (calls.append(sorted(terms)) or []),
        )
        # main() 正常路徑是直接回傳；早退只發生在錯誤或無事可做的分支，
        # 且依 docstring「Always exits 0」一律是 0。兩種都接受，非零則失敗。
        try:
            auto_kb.main()
        except SystemExit as exc:
            assert exc.code in (0, None), f"main() 以非零碼結束：{exc.code}"
        db.gemini_calls = calls
        return db
    return _run


def _article(aid, text):
    return {"id": aid, "analysis": {"summary": text}}


def _summary(db, aid):
    return next(a for a in db.articles if a["id"] == aid)["analysis"]["summary"]


# ── 迴歸：這條就是 2026-08-31 漏掉的那個案例 ──────────────────────────────

def test_known_term_patched_with_no_unknowns(run_main):
    kb = [{"jp_term": "ララ", "tw_term": "拉拉菲爾族"}]
    arts = [_article(1, "自己的 [[ララ]] 角色")]
    db = run_main(kb, arts)

    assert db.gemini_calls == [], "沒有未知術語就不該呼叫 Gemini"
    assert _summary(db, 1) == "自己的 拉拉菲爾族 角色", "已知詞必須被修補"
    assert db.updates, "文章沒有被寫回"


def test_ignored_marker_loses_brackets_with_no_unknowns(run_main):
    """`IGNORED_MARKERS` 的詞拆括號留原文，且同樣不該被早退擋掉。"""
    arts = [_article(2, "阿莉澤與 [[spiky boy]] 將作為夥伴")]
    db = run_main([], arts)

    assert db.gemini_calls == []
    assert _summary(db, 2) == "阿莉澤與 spiky boy 將作為夥伴"


def test_unknown_term_still_reaches_gemini(run_main):
    """未知詞照舊送 Gemini；修法不能把原本的主線關掉。"""
    arts = [_article(3, "任務 [[某個沒人知道的詞]] 結束後")]
    db = run_main([], arts)

    assert db.gemini_calls == [["某個沒人知道的詞"]]
    assert "[[某個沒人知道的詞]]" in _summary(db, 3), "Gemini 沒解出來就該保持原樣"


def test_ignored_marker_not_sent_to_gemini(run_main):
    """忽略名單的詞不該浪費 Gemini 呼叫——它每輪都會被婉拒。"""
    arts = [_article(4, "[[spiky boy]] 與 [[另一個未知詞]]")]
    db = run_main([], arts)

    assert db.gemini_calls == [["另一個未知詞"]]


def test_no_markers_at_all_is_a_noop(run_main):
    """完全沒有標記時不寫入任何東西（別為了修早退而變成每輪全表重寫）。"""
    db = run_main([{"jp_term": "ララ", "tw_term": "拉拉菲爾族"}],
                  [_article(5, "一篇沒有任何標記的摘要")])

    assert db.updates == []
    assert db.gemini_calls == []
