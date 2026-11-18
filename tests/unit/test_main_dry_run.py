"""main() 的兩級（spec 020 FR-002～FR-004、FR-007、FR-008、FR-010）：跑真的 main()，只換收集、HTTP、資料庫 client 與站台根目錄。
固定行、產物檔名與欄位照 contracts/dry-run.md 與這一片定下的格式，用字面值寫。"""
import importlib
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import dotenv
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src import analyzer, publisher, storage  # noqa: E402
from src import filter as filter_mod  # noqa: E402
from src.pipeline.ffxiv import FFXIVCategory  # noqa: E402
from src.pipeline.traffic import TrafficCategory  # noqa: E402

# 模組層會 load_dotenv() 與 logging.basicConfig()：擋掉，免得真的憑證進到 pytest 行程、全域 log 等級被改
with patch.object(dotenv, "load_dotenv", lambda *a, **k: False), \
        patch.object(logging, "basicConfig", lambda *a, **k: None):
    main_mod = importlib.import_module("src.main")

START = {"dry-input": "[不發布] 第一級：只到入選，不呼叫生成式 LLM",
         "dry-full": "[不發布] 第二級：呼叫 LLM，不寫入、不發布"}
STOP_FFXIV = "[不發布] 第一級在 FFXIV 分析 之前停下"
BANNER = "========== Garyu News Scraper 開始執行 =========="

PUB1 = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
PUB2 = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

TRAFFIC_SOURCES = [{"name": "甲台", "type": "rss"}, {"name": "乙台", "type": "rss"}]
FFXIV_SOURCES = [{"name": "FFXIV JP Forum - DPS", "type": "rss"}]
TRAFFIC_TITLES = ["台北機車路權新制上路", "颱風來襲停班停課", "騎士夜間安全宣導"]


def _traffic_raw():
    return [
        {"title": TRAFFIC_TITLES[0], "link": "https://t/1", "summary": "原始摘要", "source": "甲台", "published": PUB1},
        {"title": TRAFFIC_TITLES[1], "link": "https://t/2", "summary": "", "source": "甲台", "published": PUB1},
        {"title": TRAFFIC_TITLES[2], "link": "https://t/3", "summary": "", "source": "乙台", "published": PUB2},
    ]


def _ffxiv_raw():
    base = {"source": "FFXIV JP Forum - DPS", "content_type": "ffxiv", "source_weight": 80}
    return [
        {**base, "title": "Reaper adjustments", "link": "https://f/1", "summary": "body one", "published": PUB1},
        {**base, "title": "Viper job guide", "link": "https://f/2", "summary": "body two", "published": PUB2},
    ]


CONFIG = {"jaccard": {"merge_threshold": 0.45, "game_threshold": 0.50}, "buffer": {"max_age_weeks": 8}}

GEMINI_TEXT = "摘要：測試摘要\n分析：測試分析全文 [[テスト用語]]\n重要性：高\n重要性原因：測試原因\n標籤：版本更新\n地區：全球"
PARSED = {"summary": "測試摘要", "analysis": "測試分析全文 [[テスト用語]]", "importance": "高",
          "importance_reason": "測試原因", "tags": ["版本更新"], "location": "全球"}


class _Resp:
    status_code = 200
    headers: dict = {}
    text = ""

    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


class _Query:
    """PostgREST builder 的替身：鏈式呼叫照收；讀取回空，寫入記進 client.writes。"""

    def __init__(self, client, table):
        self._client, self._table, self._ops = client, table, []

    @property
    def not_(self):
        return self

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self._ops.append((name, args, kwargs))
            return self
        return call

    def execute(self):
        for name, args, kwargs in self._ops:
            if name in ("upsert", "insert", "update", "delete"):
                self._client.writes.append((self._table, name, args, kwargs))
                return SimpleNamespace(data=list(args[0]) if name in ("upsert", "insert") else [])
        return SimpleNamespace(data=[])


class _Client:
    def __init__(self):
        self.writes = []

    def table(self, name):
        return _Query(self, name)


def _fake_enrich(articles, throttle=0.4):
    for a in articles:
        a["summary"] = f"充實後：{a['title']}"
    return {}


def _seed_site(site):
    data = site / "pages" / "ffxiv" / "data"
    data.mkdir(parents=True)
    (data / "index.json").write_text('[{"week_id": "2026-W01", "article_count": 1}]', encoding="utf-8")
    (site / "pages" / "ffxiv" / "feed.xml").write_text("<rss/>", encoding="utf-8")


def _snapshot(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def h(monkeypatch, tmp_path, caplog):
    h = SimpleNamespace(client=_Client(), posts=[], collected=[], analyze_all_calls=0, site=tmp_path / "site",
                        pool_dir=tmp_path / "traffic-pool", analysis_dir=tmp_path / "analysis-output",
                        ffxiv_pool=tmp_path / "ffxiv-pool.json")
    for name in ("GARYU_RUN_MODE", "GARYU_CATEGORY", "SUPABASE_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SUPABASE_URL", "http://supabase.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "dummy-test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-test-key")
    monkeypatch.setenv("TRAFFIC_POOL_DIR", str(h.pool_dir))
    monkeypatch.setenv("ANALYSIS_OUTPUT_DIR", str(h.analysis_dir))
    monkeypatch.setenv("FFXIV_POOL_DUMP", str(h.ffxiv_pool))
    monkeypatch.setattr(storage, "_get_client", lambda: h.client)

    h.traffic_raw, h.ffxiv_raw = _traffic_raw, _ffxiv_raw

    def fake_collect(sources):
        h.collected.append([s["name"] for s in sources])
        return h.traffic_raw() if sources is TRAFFIC_SOURCES else h.ffxiv_raw()

    monkeypatch.setattr("src.collector.load_sources", lambda *a, **k: TRAFFIC_SOURCES)
    monkeypatch.setattr("src.collector.load_ffxiv_sources", lambda *a, **k: FFXIV_SOURCES)
    monkeypatch.setattr("src.collector.collect_sources", fake_collect)
    monkeypatch.setattr("src.pipeline_config.load_pipeline_config", lambda *a, **k: CONFIG)
    monkeypatch.setattr("src.pipeline_config.load_category_taxonomy", lambda *a, **k: {})
    monkeypatch.setattr("src.pipeline_config.load_source_default_categories", lambda *a, **k: {"甲台": "主類A"})
    monkeypatch.setattr("src.gn_resolver.enrich_articles", _fake_enrich)

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        h.posts.append(url)
        if url == analyzer.GEMINI_EMBED_URL:
            title = json["content"]["parts"][0]["text"].split("\n\n", 1)[1].split("\n", 1)[0]
            vec = [0.0] * len(TRAFFIC_TITLES)
            vec[TRAFFIC_TITLES.index(title)] = 1.0
            return _Resp({"embedding": {"values": vec}})
        if url.endswith(":generateContent"):
            return _Resp({"candidates": [{"content": {"parts": [{"text": GEMINI_TEXT}]}, "finishReason": "STOP"}]})
        raise AssertionError(f"未預期的 POST：{url}")

    monkeypatch.setattr(analyzer.requests, "post", fake_post)
    monkeypatch.setattr(analyzer.time, "sleep", lambda _s: None)
    monkeypatch.setattr(analyzer, "_KB_CACHE", {"既有用語": {"tw": "既有", "en": "known", "category": "test"}})
    monkeypatch.setattr(analyzer, "_KB_MISS_ACCUMULATOR", set())
    real_analyze_all = analyzer.analyze_all

    def spy_analyze_all(articles, *a, **k):
        h.analyze_all_calls += 1
        return real_analyze_all(articles, *a, **k)

    monkeypatch.setattr(analyzer, "analyze_all", spy_analyze_all)
    monkeypatch.setattr(publisher, "ROOT_DIR", h.site)
    _seed_site(h.site)

    def run(mode):
        if mode is None:
            monkeypatch.delenv("GARYU_RUN_MODE", raising=False)
        else:
            monkeypatch.setenv("GARYU_RUN_MODE", mode)
        monkeypatch.setattr(main_mod, "CATEGORIES", [TrafficCategory(), FFXIVCategory()])
        h.client = _Client()
        h.posts.clear()
        caplog.clear()
        with caplog.at_level(logging.INFO):
            try:
                main_mod.main()
            finally:
                h.msgs = [r.getMessage() for r in caplog.records]
        return h.msgs

    h.run = run
    return h


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _gen_posts(h):
    return [u for u in h.posts if u.endswith(":generateContent")]


def _end(gen, emb):
    return f"[不發布] 生成式 LLM 呼叫 {gen} 次，embedding 呼叫 {emb} 次"


def _no_stamps(rows):
    return [{k: v for k, v in r.items() if k not in ("buffered_at", "buffer_expires_at")} for r in rows]


# ── 兩級共通 ───────────────────────────────────────────────────

@pytest.mark.parametrize("mode", ["dry-input", "dry-full"])
def test_first_log_line_is_the_level_line_then_the_banner(h, mode):
    msgs = h.run(mode)
    assert msgs[:2] == [START[mode], BANNER]


@pytest.mark.parametrize("mode", ["dry-input", "dry-full"])
def test_traffic_runs_collect_filter_embedding_and_enrichment_then_skips_the_buffer(h, mode):
    msgs = h.run(mode)
    assert h.collected == [["甲台", "乙台"], ["FFXIV JP Forum - DPS"]]
    assert "[不發布] 略過 upsert_traffic_buffer：2 筆" in msgs
    assert h.client.writes == [], "不發布時 client 不該收到任何寫入"
    data = _read(h.pool_dir / "collected.json")
    assert list(data) == ["run_mode", "week_id", "sources", "article_count", "articles"]
    assert data["run_mode"] == mode
    assert data["week_id"] == TrafficCategory()._current_week_id()
    assert data["sources"] == [
        {"source": "甲台", "collected": 2, "after_freshness": 2, "after_keyword_filter": 1, "after_source_block": 1,
         "after_batch_dedup": 1, "after_vector_dedup": 1, "kept": 1, "kept_in_confluence": 0},
        {"source": "乙台", "collected": 1, "after_freshness": 1, "after_keyword_filter": 1, "after_source_block": 1,
         "after_batch_dedup": 1, "after_vector_dedup": 1, "kept": 1, "kept_in_confluence": 0},
    ]
    rows = data["articles"]
    assert data["article_count"] == 2
    assert sorted(r["title"] for r in rows) == sorted([TRAFFIC_TITLES[0], TRAFFIC_TITLES[2]])
    assert all(r["summary"] == f"充實後：{r['title']}" for r in rows), "清單要是充實之後的"
    assert sorted(r["embedding"] for r in rows) == [[0.0, 0.0, 1.0], [1.0, 0.0, 0.0]], "embedding 去重照常跑"
    assert h.posts.count(analyzer.GEMINI_EMBED_URL) == 2
    assert f"交通候選清單：寫入 {h.pool_dir / 'collected.json'}（2 篇）" in msgs


@pytest.mark.parametrize("mode", ["dry-input", "dry-full"])
def test_ffxiv_pool_dump_carries_the_level_first(h, mode):
    h.run(mode)
    dump = _read(h.ffxiv_pool)
    assert list(dump) == ["run_mode", "pool_count", "selected_count", "articles"]
    assert (dump["run_mode"], dump["pool_count"], dump["selected_count"]) == (mode, 2, 2)


@pytest.mark.parametrize("mode", ["dry-input", "dry-full"])
def test_no_site_file_is_created_or_changed(h, mode):
    before = _snapshot(h.site)
    h.run(mode)
    assert _snapshot(h.site) == before


# ── 第一級 ─────────────────────────────────────────────────────

def test_dry_input_stops_before_ffxiv_analysis_and_makes_no_generative_call(h):
    msgs = h.run("dry-input")
    pool_line = f"FFXIV 候選池內容：寫入 {h.ffxiv_pool}（2 篇，入選 2 篇）"
    assert msgs.index(pool_line) < msgs.index(STOP_FFXIV)
    assert msgs.count(STOP_FFXIV) == 1
    assert h.analyze_all_calls == 0
    assert _gen_posts(h) == []
    assert not [m for m in msgs if m.startswith(("[不發布] 略過 站台檔", "[不發布] 略過 upsert_articles"))]
    assert not h.analysis_dir.exists()
    assert msgs[-1] == _end(0, 2)


# ── 第二級 ─────────────────────────────────────────────────────

def test_dry_full_analyzes_ffxiv_and_writes_the_full_analysis_but_no_site_file(h):
    msgs = h.run("dry-full")
    assert STOP_FFXIV not in msgs
    assert h.analyze_all_calls == 1
    assert len(_gen_posts(h)) == 2
    assert "[不發布] 略過 站台檔 pages/ffxiv：2 筆" in msgs
    assert "[不發布] 略過 upsert_articles：2 筆" in msgs
    assert h.client.writes == []
    data = _read(h.analysis_dir / "ffxiv_articles.json")
    assert list(data) == ["run_mode", "week_id", "article_count", "articles"]
    assert (data["run_mode"], data["article_count"]) == ("dry-full", 2)
    assert sorted(data["articles"], key=lambda a: a["link"]) == [
        {"title": "Reaper adjustments", "link": "https://f/1", "source": "FFXIV JP Forum - DPS", "analysis": PARSED},
        {"title": "Viper job guide", "link": "https://f/2", "source": "FFXIV JP Forum - DPS", "analysis": PARSED},
    ]
    assert f"逐篇分析全文：寫入 {h.analysis_dir / 'ffxiv_articles.json'}（2 篇）" in msgs
    assert msgs[-1] == _end(2, 2)


# ── 正式模式 ───────────────────────────────────────────────────

def test_formal_mode_writes_as_before_and_prints_no_dry_line(h):
    msgs = h.run(None)
    assert not [m for m in msgs if m.startswith("[不發布]")]
    assert "" not in msgs, "正式模式不該印空行"
    assert msgs[0] == BANNER
    assert h.analyze_all_calls == 1
    (t1, n1, a1, k1), (t2, n2, a2, k2) = h.client.writes
    assert (t1, n1, k1) == ("articles", "upsert", {"on_conflict": "link", "ignore_duplicates": True})
    assert sorted(r["title"] for r in a1[0]) == sorted([TRAFFIC_TITLES[0], TRAFFIC_TITLES[2]])
    assert (t2, n2, k2) == ("articles", "upsert", {"on_conflict": "link"})
    assert [(r["content_type"], r["analysis"]) for r in a2[0]] == [("ffxiv", PARSED)] * 2
    week = TrafficCategory()._current_week_id()
    site = h.site / "pages" / "ffxiv"
    assert _read(site / "data" / f"{week}.json")["article_count"] == 2
    assert [w["week_id"] for w in _read(site / "data" / "index.json")] == [week, "2026-W01"]
    assert (site / "data" / "tags.json").exists() and (site / "week" / f"{week}.html").exists()
    assert (site / "feed.xml").read_text(encoding="utf-8") != "<rss/>"
    assert not h.pool_dir.exists() and not h.analysis_dir.exists(), "不發布的產物在正式模式不該出現"
    assert list(_read(h.ffxiv_pool)) == ["pool_count", "selected_count", "articles"]


def test_dry_collected_articles_are_the_rows_formal_would_insert(h):
    h.run(None)
    formal_rows = h.client.writes[0][2][0]
    h.run("dry-input")
    dry_rows = _read(h.pool_dir / "collected.json")["articles"]
    assert _no_stamps(dry_rows) == _no_stamps(formal_rows)
    for r in dry_rows:
        gap = datetime.fromisoformat(r["buffer_expires_at"]) - datetime.fromisoformat(r["buffered_at"])
        assert gap == timedelta(weeks=8)


def test_unknown_mode_fails_before_collection(h):
    with pytest.raises(ValueError, match="dry-input"):
        h.run("full")
    assert h.collected == []
    assert h.msgs == []


# ── 每一條出口都印結尾那一行 ─────────────────────────────────────

@pytest.mark.parametrize("mode, ffxiv", [("dry-full", False), ("dry-input", True)])
def test_closing_line_on_the_early_exit_when_nothing_was_analyzed(h, mode, ffxiv):
    h.traffic_raw = list
    if not ffxiv:
        h.ffxiv_raw = list
    with pytest.raises(SystemExit) as exc:
        h.run(mode)
    assert exc.value.code == 0
    # 第一級有類別在分析之前停下時，不說「所有 category 均無文章」：FFXIV 其實有候選
    reason = "第一級已在分析之前停下，其餘 category 沒有文章，結束執行" if ffxiv else "所有 category 均無文章，結束執行"
    assert h.msgs[-2:] == [reason, _end(0, 0)]


def test_formal_early_exit_prints_no_closing_line(h):
    h.traffic_raw = h.ffxiv_raw = list
    with pytest.raises(SystemExit):
        h.run(None)
    assert h.msgs[-1] == "所有 category 均無文章，結束執行"
    assert not [m for m in h.msgs if m.startswith("[不發布]")]


def test_closing_line_when_main_raises_after_the_loop(h, monkeypatch):
    def boom():
        raise RuntimeError("boom")
    monkeypatch.setattr(main_mod, "get_kb_miss_summary", boom)
    with pytest.raises(RuntimeError, match="boom"):
        h.run("dry-full")
    assert h.msgs[-1] == _end(2, 2)


# ── 產物路徑沒設、Supabase 沒設 ─────────────────────────────────

def test_unset_artifact_dirs_say_so_and_do_not_fail(h, monkeypatch):
    monkeypatch.delenv("TRAFFIC_POOL_DIR")
    monkeypatch.delenv("ANALYSIS_OUTPUT_DIR")
    msgs = h.run("dry-full")
    assert "交通候選清單：未設 TRAFFIC_POOL_DIR，不寫檔" in msgs
    assert "逐篇分析全文：未設 ANALYSIS_OUTPUT_DIR，不寫檔" in msgs
    assert "[不發布] 略過 upsert_traffic_buffer：2 筆" in msgs
    assert "[不發布] 略過 站台檔 pages/ffxiv：2 筆" in msgs
    assert msgs[-1] == _end(2, 2)


def test_unwritable_artifact_dirs_warn_and_the_run_still_finishes(h, monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("TRAFFIC_POOL_DIR", str(blocker))
    monkeypatch.setenv("ANALYSIS_OUTPUT_DIR", str(blocker))
    msgs = h.run("dry-full")
    assert [m for m in msgs if m.startswith(f"交通候選清單：寫入 {blocker / 'collected.json'} 失敗（")]
    assert [m for m in msgs if m.startswith(f"逐篇分析全文：寫入 {blocker / 'ffxiv_articles.json'} 失敗（")]
    assert msgs[-1] == _end(2, 2)


@pytest.mark.parametrize("loaded, weeks", [({"buffer": {"max_age_weeks": 3}}, 3), ({"buffer": {}}, 8), ({}, 8), (None, 8)])
def test_buffer_max_age_weeks_reads_config_and_falls_back_to_8(monkeypatch, loaded, weeks):
    def load(*a, **k):
        if loaded is None:
            raise RuntimeError("設定壞了")
        return loaded
    monkeypatch.setattr("src.pipeline_config.load_pipeline_config", load)
    assert TrafficCategory()._buffer_max_age_weeks() == weeks


def test_dry_run_without_supabase_still_writes_the_traffic_list(h, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL")
    msgs = h.run("dry-input")
    data = _read(h.pool_dir / "collected.json")
    assert data["run_mode"] == "dry-input" and data["article_count"] == 2
    assert all(r["embedding"] is None for r in data["articles"])
    assert "[traffic] Supabase 未設定，跳過 buffer 寫入" in msgs
    assert msgs[-1] == _end(0, 0)


# ── buffer 的列：抽成純函數之後，正式模式送給 client 的列不變 ─────────

NOW = datetime(2026, 11, 15, 4, 0, tzinfo=timezone.utc)
BUFFER_IN = [
    {"title": "甲", "link": " https://x/1 ", "source": "s", "published": "2026-11-14T00:00:00+00:00", "summary": "摘要",
     "major_category": "主類A", "initial_quality_score": 0.5, "embedding": [0.1], "image": "https://img/1"},
    {"title": "甲的重複", "link": "https://x/1", "source": "s"},
    {"title": "沒連結", "link": "", "source": "s", "published": None},
]


def test_traffic_buffer_rows_literal():
    rows = storage.traffic_buffer_rows(BUFFER_IN, "2026-W46", NOW, max_age_weeks=2)
    common = {"week_id": "2026-W46", "analysis": {}, "content_type": "traffic", "buffered_at": "2026-11-15T04:00:00+00:00",
              "buffer_expires_at": "2026-11-29T04:00:00+00:00", "hot_topic_analyzed": False}
    assert rows == [
        {**common, "title": "甲", "link": "https://x/1", "source": "s", "published": "2026-11-14T00:00:00+00:00",
         "summary": "摘要", "content_fingerprint": filter_mod.title_fingerprint({"title": "甲"}),
         "major_category": "主類A", "initial_quality_score": 0.5, "embedding": [0.1], "image_url": "https://img/1"},
        {**common, "title": "沒連結", "link": storage.stable_synthetic_link("2026-W46", BUFFER_IN[2])[0], "source": "s",
         "published": None, "summary": "", "content_fingerprint": filter_mod.title_fingerprint({"title": "沒連結"}),
         "major_category": None, "initial_quality_score": None, "embedding": None, "image_url": None},
    ]


def test_formal_upsert_traffic_buffer_sends_exactly_the_built_rows(monkeypatch):
    monkeypatch.delenv("GARYU_RUN_MODE", raising=False)
    client = _Client()
    monkeypatch.setattr(storage, "_get_client", lambda: client)
    assert storage.upsert_traffic_buffer(BUFFER_IN, "2026-W46", max_age_weeks=3) == 2
    ((table, name, args, kwargs),) = client.writes
    assert (table, name, kwargs) == ("articles", "upsert", {"on_conflict": "link", "ignore_duplicates": True})
    sent = args[0]
    now = datetime.fromisoformat(sent[0]["buffered_at"])
    assert sent == storage.traffic_buffer_rows(BUFFER_IN, "2026-W46", now, max_age_weeks=3)
    assert datetime.fromisoformat(sent[0]["buffer_expires_at"]) - now == timedelta(weeks=3)


def test_formal_upsert_traffic_buffer_empty_input_skips_the_client(monkeypatch):
    monkeypatch.delenv("GARYU_RUN_MODE", raising=False)
    got = []
    monkeypatch.setattr(storage, "_get_client", lambda: got.append(1))
    assert storage.upsert_traffic_buffer([], "2026-W46") == 0
    assert got == []


# ── ffxiv-pool：正式模式逐位元組不變 ─────────────────────────────

POOL = [{"source": "S", "source_weight": 80, "title": "t1", "link": "https://f/1", "published": "p", "summary": "s1"},
        {"source": "S", "source_weight": 80, "title": "t2", "link": "https://f/2", "published": "p", "summary": "s2"}]
POOL_EXPECTED = {"pool_count": 2, "selected_count": 1, "articles": [
    {"rank": 1, "selected": True, "source": "S", "source_weight": 80, "title": "t1", "link": "https://f/1",
     "published": "p", "summary": "s1"},
    {"rank": 2, "selected": False, "source": "S", "source_weight": 80, "title": "t2", "link": "https://f/2",
     "published": "p", "summary": "s2"},
]}


def test_ffxiv_pool_dump_is_byte_for_byte_unchanged_in_formal_mode(monkeypatch, tmp_path):
    monkeypatch.delenv("GARYU_RUN_MODE", raising=False)
    path = tmp_path / "pool.json"
    monkeypatch.setenv("FFXIV_POOL_DUMP", str(path))
    filter_mod._dump_ffxiv_pool(POOL, 1)
    assert path.read_text(encoding="utf-8") == json.dumps(POOL_EXPECTED, ensure_ascii=False, indent=1, default=str)


@pytest.mark.parametrize("mode", ["dry-input", "dry-full"])
def test_ffxiv_pool_dump_adds_only_the_level_in_dry_modes(monkeypatch, tmp_path, mode):
    monkeypatch.setenv("GARYU_RUN_MODE", mode)
    path = tmp_path / "pool.json"
    monkeypatch.setenv("FFXIV_POOL_DUMP", str(path))
    filter_mod._dump_ffxiv_pool(POOL, 1)
    expected = {"run_mode": mode, **POOL_EXPECTED}
    assert path.read_text(encoding="utf-8") == json.dumps(expected, ensure_ascii=False, indent=1, default=str)
