"""014 C3：`scripts/evaluate_sources.py`。全部離線：假 Supabase client、假 fetcher、tmp_path 裡的檔案。
`dotenv.load_dotenv` 由 autouse fixture 換成記錄器，真的 `.env` 一次都不會載入。"""
import itertools
import os
import sys
import tempfile
from types import SimpleNamespace

import pytest
import yaml

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import evaluate_sources as m  # noqa: E402
import src.analyzer  # noqa: E402
import src.collector  # noqa: E402
import src.storage  # noqa: E402
from src.pipeline.traffic import TrafficCategory  # noqa: E402

CONFIG_DIR = os.path.realpath(os.path.join(_REPO, "config")) + os.sep

CATEGORIES = {
    "categories": {"機車事故": {"keywords": ["車禍"]}},
    "source_defaults": {"甲台": "舊類", "丙台": "無關C"},
    "relevance_rules": {"主類A": {"require_any": ["機車"]}},
}
CONFIG = {"category_digest": {"主類A": {"include_categories": ["併入B"]}}}
VALID = "sources:\n  - {name: 甲台, type: rss}\n"


# ── 假 Supabase client：select 回固定列；寫入方法一被呼叫就記進 writes（代理擋住時應該一筆都沒有）

class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def __getattr__(self, name):
        return self

    def __call__(self, *a, **k):
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class FakeTable:
    def __init__(self, client, name):
        self.client, self.name = client, name

    def select(self, *cols, **kw):
        self.client.selects.append((self.name, cols))
        return FakeQuery(self.client.rows)

    def __getattr__(self, method):
        return lambda *a, **k: self.client.writes.append((self.name, method)) or FakeQuery([])


class FakeClient:
    def __init__(self, rows=()):
        self.rows, self.selects, self.writes = list(rows), [], []

    def table(self, name):
        return FakeTable(self, name)

    def rpc(self, *a, **k):
        self.writes.append(("rpc", a))
        return FakeQuery([])


@pytest.fixture(autouse=True)
def env_loads(monkeypatch):
    calls = []
    monkeypatch.setattr("dotenv.load_dotenv", lambda path=None, **k: calls.append(path) or True)
    return calls


@pytest.fixture(autouse=True)
def categories_file(monkeypatch, tmp_path):
    path = tmp_path / "categories_traffic.yml"
    path.write_text(yaml.safe_dump(CATEGORIES, allow_unicode=True, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("CATEGORIES_TRAFFIC_YML_PATH", str(path))
    return path


def _proposal(tmp_path, text):
    path = tmp_path / "proposal.yml"
    path.write_text(text, encoding="utf-8")
    return path


def _run(monkeypatch, path) -> int:
    monkeypatch.setattr(sys, "argv", ["evaluate_sources.py", str(path)])
    return m.main()


# ── C3-1 唯讀代理 ──────────────────────────────────────────────

def test_select_passes_through_to_the_real_builder():
    fake, attempts = FakeClient(rows=[{"id": 1}]), []
    query = m.ReadOnlyClient(fake, attempts).table("articles").select("id")
    assert query.eq("content_type", "traffic").range(0, 999).execute().data == [{"id": 1}]
    assert fake.selects == [("articles", ("id",))]
    assert attempts == []


@pytest.mark.parametrize("method", ["upsert", "insert", "update", "delete", "merge_future"])
def test_table_writes_and_unknown_methods_raise_are_recorded_and_never_reach_the_client(method):
    fake, attempts = FakeClient(), []
    with pytest.raises(m.WriteAttempt):
        getattr(m.ReadOnlyClient(fake, attempts).table("articles"), method)({"link": "x"})
    assert attempts == [("articles", method)]
    assert fake.writes == []


def test_any_other_client_attribute_raises_and_is_recorded():
    """白名單只有 table().select()：rpc 這類也能寫庫的入口，不會因為沒被列名而漏掉。"""
    fake, attempts = FakeClient(), []
    with pytest.raises(m.WriteAttempt):
        m.ReadOnlyClient(fake, attempts).rpc("bump", {})
    assert attempts == [("<client>", "rpc")]
    assert fake.writes == []


def test_boundaries_put_the_proxy_on_storage_and_restore_everything(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr("src.storage._get_client", lambda: fake)
    before = (src.storage._get_client, src.analyzer.attach_embeddings, dict(src.collector.FETCHERS))
    with m.boundaries() as probe:
        with pytest.raises(m.WriteAttempt):
            src.storage._get_client().table("articles").delete()
    assert probe.attempts == [("articles", "delete")]
    assert fake.writes == []
    assert (src.storage._get_client, src.analyzer.attach_embeddings, dict(src.collector.FETCHERS)) == before


def test_embedding_count_is_articles_without_a_vector(monkeypatch):
    seen = []
    monkeypatch.setattr("src.analyzer.attach_embeddings", lambda arts: seen.append(len(arts)))
    with m.boundaries() as probe:
        src.analyzer.attach_embeddings([{"title": "甲"}, {"title": "乙", "embedding": [1.0, 0.0]}])
        src.analyzer.attach_embeddings([{"title": "丙"}])
    assert probe.embedded == 2
    assert seen == [2, 1]


def test_fetch_time_is_recorded_per_source_name(monkeypatch):
    monkeypatch.setitem(src.collector.FETCHERS, "rss", lambda s: [{"title": s["name"]}])
    monkeypatch.setattr(m, "time", SimpleNamespace(monotonic=iter([0.0, 1.5, 10.0, 10.25]).__next__))
    with m.boundaries() as probe:
        got = [src.collector.FETCHERS["rss"]({"name": n}) for n in ("甲台", "乙台")]
    assert got == [[{"title": "甲台"}], [{"title": "乙台"}]]
    assert probe.seconds == {"甲台": 1.5, "乙台": 0.25}


# ── main() 跑在假的 collect／filter 上：寫入被吞掉也要失敗 ──────────────

@pytest.fixture
def patched_run(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr("src.storage._get_client", lambda: fake)
    monkeypatch.setattr("src.pipeline_config.load_pipeline_config", lambda *a, **k: CONFIG)
    collected = []
    monkeypatch.setattr(TrafficCategory, "collect", lambda self, sources=None: collected.append(sources) or [])
    return SimpleNamespace(fake=fake, collected=collected,
                           use=lambda fn: monkeypatch.setattr(TrafficCategory, "filter", fn))


def _funnel_filter(funnel, write=False):
    def fake_filter(self, raw):
        if write:
            try:
                src.storage._get_client().table("articles").upsert({"link": "x"})
            except Exception:
                pass  # 跟真的 filter() 一樣：吞掉例外、只記 warning、繼續跑
        self.last_funnel = funnel
        return []
    return fake_filter


def test_a_write_swallowed_inside_filter_still_fails_the_run(patched_run, tmp_path, monkeypatch, capsys):
    patched_run.use(_funnel_filter({"甲台": (1,) * 8}, write=True))
    code = _run(monkeypatch, _proposal(tmp_path, VALID))
    assert code != 0
    assert patched_run.fake.writes == []
    assert "articles.upsert" in capsys.readouterr().err


def test_clean_run_exits_zero_and_prints_the_c1_lines(patched_run, tmp_path, monkeypatch, capsys, env_loads):
    patched_run.use(_funnel_filter({"甲台": (3, 3, 2, 2, 2, 2, 1, 1), "空台": (0,) * 8}))
    code = _run(monkeypatch, _proposal(tmp_path, VALID))
    lines = capsys.readouterr().out.splitlines()
    assert code == 0
    assert "[來源漏斗] 甲台：收集 3 → 新鮮度 3 → 過濾 2 → 封鎖 2 → 同批去重 2 → 向量去重 2 → 寫入上限 1（匯流四類 1）" in lines
    assert "[來源漏斗] 空台：收集 0 → 新鮮度 0 → 過濾 0 → 封鎖 0 → 同批去重 0 → 向量去重 0 → 寫入上限 0（匯流四類 0）" in lines
    assert env_loads == [os.path.join(m._REPO, ".env")]


def test_category_config_failure_is_reported_as_could_not_evaluate(patched_run, tmp_path, monkeypatch, capsys):
    patched_run.use(_funnel_filter({}))
    code = _run(monkeypatch, _proposal(tmp_path, VALID))
    assert code != 0
    assert "無法評估" in capsys.readouterr().err


def test_disabled_sources_are_not_handed_to_collect(patched_run, tmp_path, monkeypatch):
    patched_run.use(_funnel_filter({"甲台": (0,) * 8}))
    text = ("sources:\n  - {name: 甲台, type: rss}\n  - {name: 停用台, type: rss, enabled: false}\n"
            "  - {name: 乙台, type: rss, enabled: true}\n")
    _run(monkeypatch, _proposal(tmp_path, text))
    assert patched_run.collected == [[{"name": "甲台", "type": "rss"}, {"name": "乙台", "type": "rss", "enabled": True}]]


# ── C3-5 提案檔格式錯誤：在收集與載入 .env 之前就以非零結束 ──────────

MALFORMED = {
    "top-level-not-mapping": ("- 甲台\n- 乙台\n", ["最上層"]),
    "sources-missing": ("source_defaults: {}\n", ["`sources`"]),
    "sources-not-list": ("sources: {name: 甲台, type: rss}\n", ["`sources`"]),
    "entry-not-mapping": ("sources:\n  - 甲台\n", ["sources[0]"]),
    "entry-missing-name": ("sources:\n  - {type: rss}\n", ["sources[0]", "`name`"]),
    "entry-missing-type": ("sources:\n  - {name: 甲台, type: rss}\n  - {name: 乙台}\n", ["sources[1]", "乙台", "`type`"]),
    "entry-empty-name": ("sources:\n  - {name: '', type: rss}\n", ["sources[0]", "`name`"]),
    "source-defaults-not-mapping": (VALID + "source_defaults: [甲台]\n", ["`source_defaults`"]),
    "yaml-syntax-error": ("sources: [\n", ["無法解析"]),
    "no-enabled-source": ("sources:\n  - {name: 甲台, type: rss, enabled: false}\n", ["沒有啟用的來源"]),
}


@pytest.mark.parametrize("text,needles", MALFORMED.values(), ids=MALFORMED.keys())
def test_malformed_proposal_exits_nonzero_naming_the_problem_and_collects_nothing(
        text, needles, tmp_path, monkeypatch, capsys, env_loads):
    collected = []

    def must_not_collect(self, sources=None):
        collected.append(sources)
        raise AssertionError("格式錯誤時不該開始收集")
    monkeypatch.setattr(TrafficCategory, "collect", must_not_collect)
    code = _run(monkeypatch, _proposal(tmp_path, text))
    err = capsys.readouterr().err
    assert code != 0
    assert all(n in err for n in needles), err
    assert collected == []
    assert env_loads == []


# ── C3-3 source_defaults 合併進暫存副本 ─────────────────────────────

def test_categories_copy_merges_proposal_defaults_and_leaves_the_original_alone(categories_file):
    before = categories_file.read_bytes()
    tmp = m.categories_copy(str(categories_file), {"甲台": "主類A", "乙台": "併入B"})
    assert os.path.realpath(tmp) != os.path.realpath(categories_file)
    with open(tmp, encoding="utf-8") as f:
        copy = yaml.safe_load(f)
    os.remove(tmp)
    assert copy["source_defaults"] == {"甲台": "主類A", "丙台": "無關C", "乙台": "併入B"}
    assert {k: v for k, v in copy.items() if k != "source_defaults"} == {
        k: v for k, v in CATEGORIES.items() if k != "source_defaults"}
    assert categories_file.read_bytes() == before
    assert not os.path.realpath(tmp).startswith(CONFIG_DIR)
    assert os.path.dirname(os.path.realpath(tmp)) == os.path.realpath(tempfile.gettempdir())


# ── 真的 collect() → collect_sources() → filter()：只換邊界 ─────────────

def _raw(n, source, title):
    return {"title": title, "link": f"https://example.com/{n}", "summary": "", "source": source, "published": ""}


FEED = {
    "甲台": [_raw(1, "甲台", "台北機車路權新制上路"), _raw(2, "甲台", "颱風來襲停班停課")],
    "乙台": [_raw(3, "乙台", "交通部公告修法草案")],
    "丙台": [_raw(4, "丙台", "騎士夜間安全宣導")],
    "停用台": [_raw(5, "停用台", "機車停車格增設")],
}
PROPOSAL = {
    "sources": [
        {"name": "甲台", "type": "rss"},
        {"name": "乙台", "type": "rss", "relevance_exempt": True},
        {"name": "丙台", "type": "rss"},
        {"name": "停用台", "type": "rss", "enabled": False},
    ],
    "source_defaults": {"甲台": "主類A", "乙台": "併入B"},
}


def _one_hot(articles):
    for i, a in enumerate(articles):
        a["embedding"] = [1.0 if j == i else 0.0 for j in range(len(articles))]


def _never(*a, **k):
    raise AssertionError("評估工具不該呼叫 prefetch()／publish()")


@pytest.fixture
def real_run(monkeypatch, tmp_path, categories_file, capsys):
    seen_paths, fake = [], FakeClient()

    def fake_rss(source):
        seen_paths.append(os.environ["CATEGORIES_TRAFFIC_YML_PATH"])
        return [dict(a) for a in FEED[source["name"]]]
    monkeypatch.setitem(src.collector.FETCHERS, "rss", fake_rss)
    monkeypatch.setattr("src.collector.time", SimpleNamespace(sleep=lambda s: None))
    clock = itertools.chain([0.0, 1.5, 10.0, 10.25, 20.0, 20.0], itertools.repeat(30.0))
    monkeypatch.setattr(m, "time", SimpleNamespace(monotonic=clock.__next__))
    monkeypatch.setattr("src.storage.is_configured", lambda: True)
    monkeypatch.setattr("src.storage._get_client", lambda: fake)
    monkeypatch.setattr("src.analyzer.attach_embeddings", _one_hot)
    monkeypatch.setattr("src.pipeline_config.load_pipeline_config", lambda *a, **k: CONFIG)
    monkeypatch.setattr("src.pipeline_config._category_taxonomy_cache", None)
    monkeypatch.setattr("src.pipeline_config._source_defaults_cache", None)
    monkeypatch.setattr(TrafficCategory, "prefetch", _never)
    monkeypatch.setattr(TrafficCategory, "publish", _never)
    before = categories_file.read_bytes()
    code = _run(monkeypatch, _proposal(tmp_path, yaml.safe_dump(PROPOSAL, allow_unicode=True)))
    out = capsys.readouterr()
    return SimpleNamespace(code=code, lines=out.out.splitlines(), err=out.err, fake=fake,
                           seen_paths=seen_paths, original=categories_file, before=before)


def test_real_entry_point_reads_through_the_proxy_and_exits_zero(real_run):
    assert real_run.code == 0, real_run.err
    assert ("articles", ("content_fingerprint",)) in real_run.fake.selects
    assert real_run.fake.writes == []


def test_real_run_prints_one_c1_line_per_enabled_source(real_run):
    funnel = [line for line in real_run.lines if line.startswith("[來源漏斗] ")]
    assert funnel == [
        "[來源漏斗] 甲台：收集 2 → 新鮮度 2 → 過濾 1 → 封鎖 1 → 同批去重 1 → 向量去重 1 → 寫入上限 1（匯流四類 1）",
        "[來源漏斗] 乙台：收集 1 → 新鮮度 1 → 過濾 1 → 封鎖 1 → 同批去重 1 → 向量去重 1 → 寫入上限 1（匯流四類 1）",
        "[來源漏斗] 丙台：收集 1 → 新鮮度 1 → 過濾 1 → 封鎖 1 → 同批去重 1 → 向量去重 1 → 寫入上限 1（匯流四類 0）",
    ]
    assert not any("停用台" in line for line in real_run.lines)


def test_real_run_lists_confluence_titles_per_source(real_run):
    lines = real_run.lines
    assert "甲台（1 篇）" in lines and "乙台（1 篇）" in lines
    assert lines[lines.index("甲台（1 篇）") + 1] == "  [主類A] 台北機車路權新制上路"
    assert lines[lines.index("乙台（1 篇）") + 1] == "  [併入B] 交通部公告修法草案"
    assert "（另有 1 個來源沒有任何一篇進匯流四類）" in lines


def test_real_run_prints_embedding_count_and_fetch_time(real_run):
    assert "本次呼叫 Gemini embedding：3 篇" in real_run.lines
    assert ["甲台：1.50 秒", "乙台：0.25 秒", "丙台：0.00 秒", "合計 1.75 秒"] == [
        line for line in real_run.lines if line.endswith(" 秒")]


def test_proposal_defaults_reach_the_real_loaders_through_a_temp_copy(real_run):
    """甲台被覆寫成主類A、乙台新增為併入B，兩篇都進了匯流四類：載入器讀到的是暫存副本。"""
    assert len(set(real_run.seen_paths)) == 1
    path = real_run.seen_paths[0]
    assert os.path.realpath(path) != os.path.realpath(real_run.original)
    assert not os.path.realpath(path).startswith(CONFIG_DIR)
    assert not os.path.exists(path)
    assert real_run.original.read_bytes() == real_run.before
    assert "  [主類A] 台北機車路權新制上路" in real_run.lines
