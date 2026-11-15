"""週交通分析腳本的兩級（spec 020 FR-002～FR-004、FR-007～FR-010）：跑真的 main()，只換資料庫的 client 與兩個讀取、
Gemini 的 HTTP、設定與站台根目錄。這次收集的清單由真的 _dump_collected 寫出來。固定行與產物欄位用字面值寫。"""
import copy
import importlib.util
import json
import logging
import math
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import dotenv
import pytest

_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _ROOT)

from src import analyzer, publisher, report_review, storage  # noqa: E402
from src.pipeline.traffic import TrafficCategory  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "weekly_dry_run_under_test", os.path.join(_ROOT, "scripts", "traffic_weekly_analysis.py"))
weekly = importlib.util.module_from_spec(_SPEC)
# 模組層會 load_dotenv() 與 logging.basicConfig()：擋掉，免得真的憑證進到 pytest 行程、全域 log 等級被改
with patch.object(dotenv, "load_dotenv", lambda *a, **k: False), \
        patch.object(logging, "basicConfig", lambda *a, **k: None):
    _SPEC.loader.exec_module(weekly)

START = {"dry-input": "[不發布] 第一級：只到入選，不呼叫生成式 LLM",
         "dry-full": "[不發布] 第二級：呼叫 LLM，不寫入、不發布"}
BANNER = "=== 週交通熱點分析開始 ==="
STOP = "[不發布] 第一級在 熱點分析 之前停下"
EXPIRE_SKIP = "[不發布] 略過 expire_buffer_articles：沒有查資料庫，筆數未知"
OVERLAY = "[不發布] 分析的輸入：buffer 11 篇，加上這次收集的 4 篇（其中 1 篇 buffer 裡已經有）"
TRIGGER = "digest[道安政策] pool=12 effective=11 threshold=10 → TRIGGER"

CONFIG = {
    "jaccard": {"merge_threshold": 0.45, "cluster_lower": 0.20},
    "topic_scoring": {"min_threshold": 1.5, "max_hot_topics": 3, "novelty_growth_pct": 0.5,
                      "category_min_threshold": {"道安政策": 1.0}},
    "topic_identity": {"similarity_threshold": 0.3},
    "buffer": {"max_age_weeks": 8},
    "category_digest": {"道安政策": {"trigger_count": 10, "quality_floor": 0.18, "max_articles": 15}},
}


def tokens(title):
    if title.startswith("p"):
        return frozenset({f"{title}x", f"{title}y"})
    bucket, variant = title.split("_")
    return frozenset({bucket, f"{bucket}{variant}"})


def _art(link, title, cat, q, source, published, summary):
    return {"link": link, "title": title, "major_category": cat, "initial_quality_score": q,
            "source": source, "published": published, "summary": summary}


def _policy(i, published, summary, q=0.3, source=None):
    return _art(f"https://p/{i}", f"p{i}", "道安政策", q, source or ("政府" if i % 2 == 0 else "媒體"), published, summary)


def _news(i):
    return f"交通部說明第{i}項新制，明年一月起分階段上路，各縣市配合宣導。"


D9 = "2026-11-09T00:00:00+00:00"
M1A = _art("https://m/1a", "m1_a", "機車事故", 0.7, "車a", "2026-11-10T00:00:00+00:00", "機車行經路口與轎車碰撞，騎士送醫。")
M1B = _art("https://m/1b", "m1_b", "機車事故", 0.9, "車b", "2026-11-11T00:00:00+00:00", "")
P11 = _policy(11, "2026-11-06T00:00:00+00:00", _news(11), q=0.1, source="政府")  # 低於品質下限：在池裡、不入選
# get_traffic_buffer 的順序（published 新到舊）。p0 的摘要 401 字、p2 剛好 400 字：彙整的來源截到 400 字
BUFFER = [M1B, M1A, _policy(0, D9, "長" * 397 + "8月1日"), _policy(1, D9, ""), _policy(2, D9, "長" * 396 + "8月2日"),
          _policy(3, D9, ""), _policy(4, D9, _news(4)), _policy(5, D9, _news(5)), _policy(6, D9, _news(6)),
          _policy(7, D9, "buffer 版：" + _news(7)), P11]
COLLECTED_IN = [_policy(7, D9, "收集版：" + _news(7)), _policy(8, "2026-11-13T07:00:00+08:00", _news(8)),
                _policy(9, "2026-11-08T00:00:00+00:00", ""), _policy(10, "2026-11-07T00:00:00+00:00", _news(10))]
# 正式執行時 main.py 先寫進 buffer：同 link 的不覆寫；published 是 timestamptz，讀回來是 UTC
FORMAL_BUFFER = [_policy(8, "2026-11-12T23:00:00+00:00", _news(8)), *BUFFER[:10],
                 COLLECTED_IN[2], COLLECTED_IN[3], P11]

HOT_TEXT = "### 一、事件\n機車碰撞 [1][2]，另見 [9]。\n### 二、分析\n路口設計。\n### 三、建議\n加強宣導。"
DIGEST_RAW = "### 本期概覽\n本週各項新制互相獨立。\n### 分節彙整\n- 新制上路 [1][2]，另見 [9]\n### 待追蹤\n- 8月1日、8月2日的後續"
DIGEST_TEXT = ("### 本期概覽\n本期收錄 11 篇報導，其中 3 篇只有標題。\n本週各項新制互相獨立。\n### 分節彙整\n- 新制上路 [1][2]，另見 [9]\n"
               "### 待追蹤\n- 8月1日、8月2日的後續\n\n### 僅標題\n- p1 [9]\n- p3 [10]\n- p9 [11]")
HOT_HITS = {"missing_section": [], "id_out_of_range": ["[9]"], "interweave_sum": [],
            "replacement_new_number": [], "deletion_over_cap": []}
DIGEST_HITS = {"missing_section": [], "id_out_of_range": [], "title_only_in_sections": ["[9]"], "self_count": [],
               "independence_claim": ["互相獨立"], "date_unlabeled": ["8月1日"],
               "replacement_new_number": [], "deletion_over_cap": []}
DIGEST_ORDER = ["p8", "p0", "p2", "p4", "p5", "p6", "p7", "p10", "p1", "p3", "p9"]
HOT_LABEL = "機車事故 · m1"
DIGEST_LABEL = "道安政策 · 彙整"


class _Resp:
    status_code = 200
    headers: dict = {}
    text = ""

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class _Query:
    """PostgREST builder 的替身：鏈式呼叫照收，execute 時把整串記進 client.calls，回空。"""

    def __init__(self, client, table):
        self._client, self._table, self._ops = client, table, []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self._ops.append((name, args))
            return self
        return call

    def execute(self):
        self._client.calls.append((self._table, self._ops))
        return SimpleNamespace(data=[])


class _Client:
    def __init__(self):
        self.calls = []

    def table(self, name):
        return _Query(self, name)


def _writes(client):
    """每次 execute 縮成 (表, 第一個動作, in_ 的 link 清單或 None)。"""
    return [(table, ops[0][0], next((args[1] for name, args in ops if name == "in_"), None))
            for table, ops in client.calls]


def _upserted_reports(client):
    return [ops[0][1][0] for table, ops in client.calls if table == "hot_topic_reports"]


def _snapshot(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _end(gen, emb):
    return f"[不發布] 生成式 LLM 呼叫 {gen} 次，embedding 呼叫 {emb} 次"


def _brief(a):
    return {k: a[k] for k in ("title", "link", "source", "published", "major_category", "initial_quality_score", "summary")}


@pytest.fixture
def h(monkeypatch, tmp_path, caplog):
    h = SimpleNamespace(client=_Client(), posts=[], buffer=BUFFER, reads=0, analyze={"hot": 0, "digest": 0}, checks=0,
                        site=tmp_path / "site", pool_dir=tmp_path / "traffic-pool",
                        analysis_dir=tmp_path / "analysis-output")
    monkeypatch.delenv("GARYU_RUN_MODE", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-test-key")
    monkeypatch.setenv("TRAFFIC_POOL_DIR", str(h.pool_dir))
    monkeypatch.setenv("ANALYSIS_OUTPUT_DIR", str(h.analysis_dir))
    monkeypatch.setattr(storage, "_get_client", lambda: h.client)

    def read_buffer(max_age_weeks=8):
        h.reads += 1
        return copy.deepcopy(h.buffer)

    monkeypatch.setattr(storage, "get_traffic_buffer", read_buffer)
    monkeypatch.setattr(storage, "get_recent_hot_topic_reports", lambda *a, **k: [])
    monkeypatch.setattr("src.pipeline_config.load_pipeline_config", lambda *a, **k: CONFIG)
    monkeypatch.setattr("src.pipeline_config.load_category_taxonomy", lambda *a, **k: {"道安政策": [], "機車事故": []})
    monkeypatch.setattr("src.pipeline_config.load_relevance_rules", lambda *a, **k: {})
    monkeypatch.setattr("src.filter.normalise_title", tokens)

    h.texts = {analyzer.HOT_TOPIC_SYSTEM_PROMPT: HOT_TEXT, analyzer.DIGEST_SYSTEM_PROMPT: DIGEST_RAW}

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        h.posts.append(url)
        text = h.texts[json["system_instruction"]["parts"][0]["text"]]
        return _Resp({"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})

    monkeypatch.setattr(analyzer.requests, "post", fake_post)
    monkeypatch.setattr(analyzer.time, "sleep", lambda _s: None)
    monkeypatch.setattr(weekly.time, "sleep", lambda _s: None)

    def spy(counter, key, real):
        def wrapper(*a, **k):
            counter[key] += 1
            return real(*a, **k)
        return wrapper

    monkeypatch.setattr(analyzer, "analyze_hot_topic", spy(h.analyze, "hot", analyzer.analyze_hot_topic))
    monkeypatch.setattr(analyzer, "analyze_category_digest", spy(h.analyze, "digest", analyzer.analyze_category_digest))
    counts = {"check": 0}
    monkeypatch.setattr(report_review, "check_report", spy(counts, "check", report_review.check_report))
    h.check_calls = lambda: counts["check"]

    monkeypatch.setattr(publisher, "ROOT_DIR", h.site)
    (h.site / "pages" / "traffic").mkdir(parents=True)
    h.hot_topics = h.site / "pages" / "traffic" / "hot_topics.json"
    h.hot_topics.write_text('{"report_count": 0}', encoding="utf-8")
    h.collected = h.pool_dir / "collected.json"
    monkeypatch.setenv("GARYU_RUN_MODE", "dry-input")
    TrafficCategory()._dump_collected(copy.deepcopy(COLLECTED_IN))

    def run(mode):
        if mode is None:
            monkeypatch.delenv("GARYU_RUN_MODE", raising=False)
        else:
            monkeypatch.setenv("GARYU_RUN_MODE", mode)
        h.client = _Client()
        h.posts.clear()
        caplog.clear()
        with caplog.at_level(logging.INFO):
            try:
                weekly.main()
            finally:
                h.msgs = [r.getMessage() for r in caplog.records]
        return h.msgs

    h.run = run
    return h


# ── 兩級共通 ───────────────────────────────────────────────────

@pytest.mark.parametrize("mode", ["dry-input", "dry-full"])
def test_both_levels_skip_expiry_and_overlay_this_runs_collection_on_the_buffer(h, mode):
    before = _snapshot(h.site)
    msgs = h.run(mode)
    assert msgs[:2] == [START[mode], BANNER]
    assert EXPIRE_SKIP in msgs
    assert not [m for m in msgs if m.startswith("已清理過期 buffer")], "不發布時沒有清理，不能印清理了幾筆"
    assert msgs.index("buffer 中有 11 篇待分析文章") < msgs.index(OVERLAY)
    assert TRIGGER in msgs, "疊上這次收集的 3 篇新文章，彙整池才到門檻"
    assert h.client.calls == []
    assert _snapshot(h.site) == before, "pages/traffic/hot_topics.json 不該被產生或改動"


@pytest.mark.parametrize("mode", ["dry-input", "dry-full"])
def test_selection_artifact_carries_the_level_the_buckets_and_the_digest_pools(h, mode):
    msgs = h.run(mode)
    path = h.pool_dir / "selection.json"
    assert f"交通熱點選材：寫入 {path}（熱點 1 個，彙整 1 類）" in msgs
    data = _read(path)
    assert list(data) == ["run_mode", "week_start_date", "hot_topics", "digests"]
    assert (data["run_mode"], data["week_start_date"]) == (mode, weekly._week_start_date())
    (hot,) = data["hot_topics"]
    assert hot.pop("score") == pytest.approx(1.6 * math.log(3) ** 2)
    assert hot == {"bucket_id": "bucket_12", "topic_label": HOT_LABEL, "article_count": 2,
                   "articles": [_brief(M1A), _brief(M1B)]}
    (digest,) = data["digests"]
    selected = digest.pop("selected")
    assert digest == {"category": "道安政策", "selected_for_analysis": True, "pool_count": 12, "effective_count": 11,
                      "trigger_count": 10, "sources": [{"source": "政府", "count": 7}, {"source": "媒體", "count": 5}]}
    assert [a["title"] for a in selected] == ["p8", "p0", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p9", "p10"]
    by_title = {a["title"]: a for a in selected}
    assert by_title["p8"]["published"] == "2026-11-12T23:00:00+00:00", "這次收集的日期換成 buffer 讀回來的樣子（UTC）"
    assert by_title["p7"]["summary"] == "buffer 版：" + _news(7), "同一個 link 留 buffer 那份"


# ── 第一級 ─────────────────────────────────────────────────────

def test_dry_input_stops_after_selection_and_makes_no_generative_call(h):
    msgs = h.run("dry-input")
    selection = f"交通熱點選材：寫入 {h.pool_dir / 'selection.json'}（熱點 1 個，彙整 1 類）"
    assert msgs.index(TRIGGER) < msgs.index(selection) < msgs.index(STOP)
    assert msgs.index("本週熱點 topic（通過 novelty gate）：['bucket_12']") < msgs.index(STOP)
    assert msgs.count(STOP) == 1
    assert h.analyze == {"hot": 0, "digest": 0}
    assert h.posts == []
    assert h.check_calls() == 0
    assert not h.analysis_dir.exists()
    assert not [m for m in msgs if "略過 upsert_hot_topic_report" in m or "略過 站台檔" in m]
    assert msgs[-2:] == [STOP, _end(0, 0)]


def test_dry_input_with_nothing_selected_says_why_and_does_not_claim_a_stop(h):
    h.buffer = [_policy(4, D9, _news(4)), _policy(5, D9, _news(5)), _policy(6, D9, _news(6))]
    h.collected.unlink()
    msgs = h.run("dry-input")
    assert STOP not in msgs
    assert msgs[-2:] == ["無 bucket 達到 min_threshold，跳過本週熱點發布", _end(0, 0)]
    data = _read(h.pool_dir / "selection.json")
    assert data["hot_topics"] == []
    assert [(d["category"], d["selected_for_analysis"], d["pool_count"]) for d in data["digests"]] == [("道安政策", False, 3)]


# ── 第二級 ─────────────────────────────────────────────────────

def test_dry_full_writes_every_report_with_its_unadjudicated_check_hits(h):
    msgs = h.run("dry-full")
    assert STOP not in msgs
    assert h.analyze == {"hot": 1, "digest": 1}
    assert len(h.posts) == 2
    assert h.check_calls() == 2
    path = h.analysis_dir / "traffic_reports.json"
    assert f"報告全文：寫入 {path}（2 份報告）" in msgs
    data = _read(path)
    assert list(data) == ["run_mode", "week_start_date", "report_count", "reports"]
    assert (data["run_mode"], data["week_start_date"], data["report_count"]) == ("dry-full", weekly._week_start_date(), 2)
    hot, digest = data["reports"]
    assert (hot["template"], hot["topic_label"], hot["report_text"]) == ("hot", HOT_LABEL, HOT_TEXT)
    assert [a["title"] for a in hot["source_article_links"]] == ["m1_b", "m1_a"]
    assert hot["check_report"] == {"status": "未經逐條判定", "hits": HOT_HITS}
    assert (digest["template"], digest["topic_label"], digest["report_text"]) == ("digest", DIGEST_LABEL, DIGEST_TEXT)
    assert [a["title"] for a in digest["source_article_links"]] == DIGEST_ORDER
    assert digest["check_report"] == {"status": "未經逐條判定", "hits": DIGEST_HITS}
    assert digest["latest_source_date"] == "2026-11-12"


def test_dry_full_skips_every_write_and_the_site_file_and_does_not_say_published(h):
    msgs = h.run("dry-full")
    assert msgs.count("[不發布] 略過 upsert_hot_topic_report：1 筆") == 2
    assert "[不發布] 略過 mark_articles_analyzed：1 筆" in msgs
    assert "[不發布] 略過 站台檔 pages/traffic/hot_topics.json：2 筆" in msgs
    assert h.client.calls == []
    assert not [m for m in msgs if "consumed=" in m], "不發布時沒有消耗"
    assert not [m for m in msgs if "共發布" in m]
    assert msgs[-2:] == ["=== 週交通熱點分析完成，產生 2 份報告，沒有發布 ===", _end(2, 0)]


def test_dry_full_with_no_report_skips_no_site_file_and_still_writes_an_empty_artifact(h):
    h.texts = dict.fromkeys(h.texts, "")
    msgs = h.run("dry-full")
    assert not [m for m in msgs if "略過 站台檔" in m], "沒有報告時正式執行也不發布，沒有可略過的"
    assert _read(h.analysis_dir / "traffic_reports.json")["report_count"] == 0
    assert msgs[-2:] == ["=== 週交通熱點分析完成，產生 0 份報告，沒有發布 ===", _end(2, 0)]


def test_dry_full_keeps_every_report_when_one_check_does_not_finish(h, monkeypatch):
    checked = report_review.check_report

    def flaky(text, **kwargs):
        if kwargs["template"] == "hot":
            raise ValueError("檢查壞了")
        return checked(text, **kwargs)

    monkeypatch.setattr(report_review, "check_report", flaky)
    msgs = h.run("dry-full")
    hot, digest = _read(h.analysis_dir / "traffic_reports.json")["reports"]
    assert (hot["topic_label"], hot["report_text"]) == (HOT_LABEL, HOT_TEXT)
    assert hot["check_report"] == {"status": "檢查沒有跑完", "error": "ValueError: 檢查壞了"}
    assert digest["check_report"] == {"status": "未經逐條判定", "hits": DIGEST_HITS}
    assert f"check_report() 沒有跑完，{HOT_LABEL} 的報告照樣留下：ValueError: 檢查壞了" in msgs
    assert msgs[-2:] == ["=== 週交通熱點分析完成，產生 2 份報告，沒有發布 ===", _end(2, 0)]


def test_dry_full_reports_are_what_formal_would_upsert_after_the_same_collection(h):
    h.buffer = FORMAL_BUFFER
    h.run(None)
    formal = _upserted_reports(h.client)
    assert [r["topic_label"] for r in formal] == [HOT_LABEL, DIGEST_LABEL]
    h.buffer = BUFFER
    h.run("dry-full")
    dry = _read(h.analysis_dir / "traffic_reports.json")["reports"]
    assert [{k: r[k] for k in row} for r, row in zip(dry, formal)] == formal


def test_overlay_orders_like_the_buffer_read_and_keeps_the_buffer_copy(monkeypatch, tmp_path, caplog):
    def row(link, published, summary="收集版"):
        return {"link": link, "title": link, "published": published, "summary": summary}

    buffer = [row("b1", "2026-11-10T00:00:00+00:00", "buffer 版"), row("b2", "2026-11-08T00:00:00+00:00", "buffer 版")]
    collected = [row("c-none", None), row("c-taipei", "2026-11-11T07:00:00+08:00"), row("c-naive", "2026-11-09T00:00:00"),
                 row("b2", "2026-11-12T00:00:00+00:00"), row("c-tie", "2026-11-10T08:00:00+08:00")]
    (tmp_path / "collected.json").write_text(json.dumps({"articles": collected}), encoding="utf-8")
    monkeypatch.setenv("TRAFFIC_POOL_DIR", str(tmp_path))
    with caplog.at_level(logging.INFO, logger="traffic_weekly_analysis"):
        merged = weekly._overlay_collected(copy.deepcopy(buffer))
    assert [(a["link"], a["published"], a["summary"]) for a in merged] == [
        ("c-none", None, "收集版"),  # Postgres 的 DESC 把 NULL 排在最前
        ("c-taipei", "2026-11-10T23:00:00+00:00", "收集版"),
        ("b1", "2026-11-10T00:00:00+00:00", "buffer 版"),
        ("c-tie", "2026-11-10T00:00:00+00:00", "收集版"),  # 同一刻：既有的列 id 小，排在前面
        ("c-naive", "2026-11-09T00:00:00+00:00", "收集版"),
        ("b2", "2026-11-08T00:00:00+00:00", "buffer 版"),
    ]
    assert [r.getMessage() for r in caplog.records] == [
        "[不發布] 分析的輸入：buffer 2 篇，加上這次收集的 5 篇（其中 1 篇 buffer 裡已經有）"]


# ── 清單疊不上、路徑沒設 ───────────────────────────────────────

def test_missing_collection_file_says_it_was_not_overlaid(h):
    h.collected.unlink()
    msgs = h.run("dry-input")
    assert f"[不發布] 分析的輸入：buffer 11 篇，沒有疊上這次收集的清單（找不到 {h.collected}）" in msgs
    assert "digest[道安政策] pool=9 effective=8 threshold=10 → accumulate" in msgs
    assert msgs[-2:] == [STOP, _end(0, 0)]


def test_unreadable_collection_file_warns_and_runs_on_the_buffer(h):
    h.collected.write_text("{", encoding="utf-8")
    msgs = h.run("dry-input")
    head = f"[不發布] 分析的輸入：buffer 11 篇，沒有疊上這次收集的清單（讀不了 {h.collected}："
    assert [m for m in msgs if m.startswith(head)]
    assert "digest[道安政策] pool=9 effective=8 threshold=10 → accumulate" in msgs


@pytest.mark.parametrize("text", ['{"run_mode": "x"}', "[1, 2]", '{"articles": null}', '{"articles": ["s"]}'])
def test_collection_file_of_the_wrong_shape_warns_and_runs_on_the_buffer(h, text):
    h.collected.write_text(text, encoding="utf-8")
    msgs = h.run("dry-input")
    line = f"[不發布] 分析的輸入：buffer 11 篇，沒有疊上這次收集的清單（讀不了 {h.collected}：articles 不是物件的清單）"
    assert line in msgs
    assert "digest[道安政策] pool=9 effective=8 threshold=10 → accumulate" in msgs


def test_unset_artifact_dirs_say_so_and_do_not_fail(h, monkeypatch):
    monkeypatch.delenv("TRAFFIC_POOL_DIR")
    monkeypatch.delenv("ANALYSIS_OUTPUT_DIR")
    msgs = h.run("dry-full")
    assert "[不發布] 分析的輸入：buffer 11 篇，沒有疊上這次收集的清單（未設 TRAFFIC_POOL_DIR）" in msgs
    assert "交通熱點選材：未設 TRAFFIC_POOL_DIR，不寫檔" in msgs
    assert "報告全文：未設 ANALYSIS_OUTPUT_DIR，不寫檔" in msgs
    assert msgs[-1] == _end(1, 0)


# ── 每一條出口都印結尾那一行；模式先驗 ──────────────────────────

def test_too_few_articles_exit_still_prints_the_closing_line(h):
    h.buffer = BUFFER[:1]
    h.collected.unlink()
    msgs = h.run("dry-full")
    assert msgs[-2:] == ["buffer 文章不足 3 篇，本週跳過熱點分析（目前 1 篇）", _end(0, 0)]


@pytest.mark.parametrize("mode", ["dry-input", "dry-full"])
def test_a_run_that_raises_still_prints_the_closing_line(h, monkeypatch, mode):
    def broken(max_age_weeks=8):
        raise RuntimeError("讀不到 buffer")

    monkeypatch.setattr(storage, "get_traffic_buffer", broken)
    with pytest.raises(RuntimeError, match="讀不到 buffer"):
        h.run(mode)
    assert (h.msgs[0], h.msgs[-1]) == (START[mode], _end(0, 0))


def test_unknown_mode_fails_before_reading_anything(h):
    with pytest.raises(ValueError, match="dry-input"):
        h.run("full")
    assert (h.reads, h.client.calls, h.msgs) == (0, [], [])


# ── 正式模式 ───────────────────────────────────────────────────

def test_formal_mode_ignores_the_collection_file_and_writes_as_before(h):
    msgs = h.run(None)
    assert not [m for m in msgs if m.startswith("[不發布]")]
    assert "" not in msgs, "正式模式不該印空行"
    assert msgs[0] == BANNER
    assert "已清理過期 buffer：0 筆" in msgs
    assert "digest[道安政策] pool=9 effective=8 threshold=10 → accumulate" in msgs
    assert _writes(h.client) == [("articles", "delete", None), ("hot_topic_reports", "upsert", None),
                                 ("articles", "update", ["https://m/1b", "https://m/1a"])]
    assert h.check_calls() == 0
    published = _read(h.hot_topics)
    assert (published["report_count"], [r["topic_label"] for r in published["reports"]]) == (1, [HOT_LABEL])
    assert not (h.pool_dir / "selection.json").exists() and not h.analysis_dir.exists()
    assert msgs[-1] == "=== 週交通熱點分析完成，共發布 1 個熱點 ==="


def test_formal_mode_consumes_the_digest_pool_and_says_so(h):
    h.buffer = FORMAL_BUFFER
    msgs = h.run(None)
    assert not [m for m in msgs if m.startswith("[不發布]")]
    assert "digest[道安政策] consumed=12" in msgs
    digest_links = [f"https://p/{t[1:]}" for t in DIGEST_ORDER]
    assert _writes(h.client) == [("articles", "delete", None),
                                 ("hot_topic_reports", "upsert", None), ("articles", "update", ["https://m/1b", "https://m/1a"]),
                                 ("hot_topic_reports", "upsert", None), ("articles", "update", digest_links),
                                 ("articles", "update", ["https://p/11"])]
    assert h.check_calls() == 0
    assert _read(h.hot_topics)["report_count"] == 2
    assert msgs[-1] == "=== 週交通熱點分析完成，共發布 2 個熱點 ==="
