"""018 Unit 4：`scripts/replay_report_review.py` 的重生成模式。全部離線：假 Supabase client、
monkeypatch 的 `_call_gemini`／`_get_api_key`、tmp_path 輸出；`dotenv.load_dotenv` 換成記錄器，真的 `.env` 不載入。"""
import json
import os
import sys
from types import SimpleNamespace

import pytest
from postgrest.exceptions import APIError

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _REPO)

import scripts.replay_report_review as m  # noqa: E402
import src.analyzer as analyzer  # noqa: E402
from src.report_review import SC001_CHECKS  # noqa: E402

WEEK, DIGEST_TOPIC, HOT_TOPIC = "2026-11-02", "道安政策 · 彙整", "科技執法 · 新聞"
FILLER = "交通部說明新制內容與配套措施，各縣市將配合宣導並加強稽查。"


def article(link, title, summary, published, score):
    return {"link": link, "title": title, "summary": summary,
            "published": published, "initial_quality_score": score}


# 分數順序（A2 > A3 > A1）刻意與 source_article_links 順序（A1, A2, A3）不同；A1 的「11月5日」在第 400 字之後
A1 = article("https://ex.com/a1", "交通部公布新制 - 中央社", (FILLER * 20)[:420] + "11月5日上路",
             "2026-10-28T02:00:00+00:00", 0.5)
A2 = article("https://ex.com/a2", "立委質詢酒駕罰則 - 聯合報", "立委質詢酒駕罰則 聯合報",
             "2026-10-29T02:00:00+00:00", 0.9)
A3 = article("https://ex.com/a3", "台中道安會報", "台中市10月30日召開道安會報，市府報告上半年事故統計與路口改善進度。",
             "2026-10-30T02:00:00+00:00", 0.7)

DIGEST_ORIGINAL = """### 本期概覽
本期共收錄 3 起獨立事件，各事件互相獨立。

### 分節彙整
交通部公布新制，11 月 5 日上路 [1]。立委 10 月 9 日質詢酒駕罰則 [2]。台中 10 月 30 日召開道安會報 [3]。

### 待追蹤
本期無"""

DIGEST_REGENERATED_RAW = """### 本期概覽
涵蓋中央新制與地方道安會報。

### 分節彙整
台中市召開道安會報 [1]。交通部公布新制 [2]。

### 待追蹤
本期無"""

B1 = article("https://ex.com/b1", "科技執法新增測速照相", "警方宣布區間測速上路。" * 70,
             "2026-10-20T02:00:00+00:00", 0.8)
B2 = article("https://ex.com/b2", "測速照相罰單暴增 - TVBS", "測速照相罰單暴增 TVBS",
             "2026-10-21T02:00:00+00:00", 0.6)

HOT_ORIGINAL = """### 一、 事故因果解構
交織度分布：[工程主導] 1篇 ／ [雙因交織] 1篇 ／ [人因主導] 1篇
### 二、 政經變數審查
觸發條件：[1]
### 三、 官方論述偏誤
觸發條件：[5]"""

HOT_REGENERATED_RAW = """### 一、 事故因果解構
本批無事故報導，不適用
### 二、 政經變數審查
觸發條件：[1]
### 三、 官方論述偏誤
觸發條件：無官方統計宣稱，不適用"""


def report_row(id_, topic, links, text, week=WEEK):
    return {"id": id_, "week_start_date": week, "topic_label": topic,
            "report_text": text, "source_article_links": links}


def stored(a):
    return {"title": a["title"], "link": a["link"], "summary": a["summary"][:200]}


# ── 假 Supabase client：eq／in_ 真的過濾；select 以外的方法一被呼叫就記進 writes

class FakeQuery:
    def __init__(self, client, table, rows):
        self.client, self.table, self.rows = client, table, list(rows)

    def eq(self, col, val):
        self.rows = [r for r in self.rows if r.get(col) == val]
        return self

    def in_(self, col, vals):
        self.client.in_calls.append((self.table, list(vals)))
        self.rows = [r for r in self.rows if r.get(col) in vals]
        return self

    def __getattr__(self, name):
        return lambda *a, **k: self

    def execute(self):
        if self.table in self.client.errors:
            raise self.client.errors[self.table]
        return SimpleNamespace(data=[dict(r) for r in self.rows])


class FakeTable:
    def __init__(self, client, name):
        self.client, self.name = client, name

    def select(self, *cols, **kw):
        self.client.selects.append(self.name)
        return FakeQuery(self.client, self.name, self.client.tables.get(self.name, []))

    def __getattr__(self, method):
        return lambda *a, **k: self.client.writes.append((self.name, method)) or FakeQuery(self.client, self.name, [])


class FakeClient:
    def __init__(self, tables, errors=None):
        self.tables, self.errors = tables, dict(errors or {})
        self.selects, self.in_calls, self.writes = [], [], []

    def table(self, name):
        return FakeTable(self, name)

    def rpc(self, *a, **k):
        self.writes.append(("rpc", a))
        return FakeQuery(self, "rpc", [])


MISSING_TABLE = APIError({"code": "PGRST205", "message": "Could not find the table 'public.hot_topic_report_reviews' in the schema cache"})


def digest_db(**kw):
    tables = {"hot_topic_reports": [report_row("rep-digest-1", DIGEST_TOPIC, [stored(a) for a in (A1, A2, A3)], DIGEST_ORIGINAL)],
              "articles": [A3, A1, A2], "hot_topic_report_reviews": []}
    tables.update(kw.pop("tables", {}))
    return FakeClient(tables, **kw)


def hot_db():
    return FakeClient({"hot_topic_reports": [report_row("rep-hot-1", HOT_TOPIC, [stored(B1), stored(B2)], HOT_ORIGINAL)],
                       "articles": [B2, B1], "hot_topic_report_reviews": []})


@pytest.fixture(autouse=True)
def env_loads(monkeypatch):
    calls = []
    monkeypatch.setattr("dotenv.load_dotenv", lambda path=None, **k: calls.append(path) or True)
    return calls


@pytest.fixture
def gemini(monkeypatch):
    """記下每次送出的 prompt，回 `reply`（None＝呼叫失敗）；API key 是假的。"""
    state = SimpleNamespace(prompts=[], reply=DIGEST_REGENERATED_RAW)
    monkeypatch.setattr(analyzer, "_get_api_key", lambda: "test-key")
    monkeypatch.setattr(analyzer, "GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(analyzer, "_call_gemini",
                        lambda prompt, api_key, **k: state.prompts.append(prompt) or state.reply)
    return state


def run(monkeypatch, fake, tmp_path, *extra, week=WEEK, topic=DIGEST_TOPIC):
    monkeypatch.setattr("src.storage._get_client", lambda: fake)
    return m.main(["--week", week, "--topic", topic, "--out", str(tmp_path / "out"), *extra])


def output(tmp_path, stem):
    out = tmp_path / "out"
    j, md = out / f"{stem}.json", out / f"{stem}.md"
    assert j.exists(), sorted(os.listdir(out)) if out.exists() else "沒有輸出目錄"
    assert md.exists(), sorted(os.listdir(out))
    return json.loads(j.read_text(encoding="utf-8")), md.read_text(encoding="utf-8")


def no_output(tmp_path):
    out = tmp_path / "out"
    return not out.exists() or not os.listdir(out)


# ── 唯讀 ──────────────────────────────────────────────

def test_module_source_never_references_an_upsert():
    with open(m.__file__, encoding="utf-8") as f:
        assert "upsert" not in f.read()


def test_a_full_regenerate_run_sends_no_write_to_the_client(monkeypatch, tmp_path, gemini):
    fake = digest_db()
    assert run(monkeypatch, fake, tmp_path, "--regenerate") == 0
    assert fake.writes == []
    assert set(fake.selects) == {"hot_topic_reports", "hot_topic_report_reviews", "articles"}


def test_loads_the_repo_env_file(monkeypatch, tmp_path, gemini, env_loads):
    run(monkeypatch, digest_db(), tmp_path)
    assert env_loads == [os.path.join(m._REPO_ROOT, ".env")]


# ── 輸入：快照或重建（FR-016） ───────────────────────────────

def test_report_without_review_record_is_reconstructed_in_the_old_digest_format(monkeypatch, tmp_path, gemini, capsys):
    assert run(monkeypatch, digest_db(), tmp_path) == 0
    data, _ = output(tmp_path, f"{WEEK}-rep-digest-1")
    assert data["input"] == "reconstructed"
    assert data["template"] == "digest"
    assert data["original"]["input_text"] == "\n\n".join([
        f"[1] 日期：2026-10-28\n    標題：{A1['title']}\n    摘要：{A1['summary'][:400]}",
        f"[2] 日期：2026-10-29\n    標題：{A2['title']}\n    摘要：{A2['summary']}",
        f"[3] 日期：2026-10-30\n    標題：{A3['title']}\n    摘要：{A3['summary']}",
    ])
    assert [s["link"] for s in data["original"]["sources"]] == [A1["link"], A2["link"], A3["link"]]
    assert data["original"]["title_only_ids"] == [2]
    assert "沒有這份報告的審核紀錄" in capsys.readouterr().out


def test_old_reports_storing_bare_link_strings_are_reconstructed(monkeypatch, tmp_path, gemini):
    fake = digest_db(tables={"hot_topic_reports": [
        report_row("rep-old", DIGEST_TOPIC, [A3["link"], A1["link"]], DIGEST_ORIGINAL)]})
    assert run(monkeypatch, fake, tmp_path) == 0
    data, _ = output(tmp_path, f"{WEEK}-rep-old")
    assert [s["title"] for s in data["original"]["sources"]] == [A3["title"], A1["title"]]


def test_links_beyond_one_batch_are_all_read_in_order(monkeypatch, tmp_path, gemini):
    many = [article(f"https://ex.com/n{i}", f"標題{i}", FILLER * 2, "2026-10-28T02:00:00+00:00", i / 100)
            for i in range(m.BATCH + 2)]
    fake = digest_db(tables={"articles": many[::-1], "hot_topic_reports": [
        report_row("rep-many", DIGEST_TOPIC, [a["link"] for a in many], DIGEST_ORIGINAL)]})
    assert run(monkeypatch, fake, tmp_path) == 0
    data, _ = output(tmp_path, f"{WEEK}-rep-many")
    assert [s["link"] for s in data["original"]["sources"]] == [a["link"] for a in many]
    assert all(len(links) <= m.BATCH for table, links in fake.in_calls if table == "articles")


def test_hot_report_is_reconstructed_in_the_old_three_axis_format(monkeypatch, tmp_path, gemini):
    assert run(monkeypatch, hot_db(), tmp_path, topic=HOT_TOPIC) == 0
    data, _ = output(tmp_path, f"{WEEK}-rep-hot-1")
    assert data["template"] == "hot"
    assert data["original"]["input_text"] == (
        f"[1] 標題：{B1['title']}\n    摘要：{B1['summary'][:600]}\n\n"
        f"[2] 標題：{B2['title']}\n    摘要：{B2['summary']}")
    assert data["original"]["sources"][0]["summary"] == B1["summary"][:600]


def test_missing_review_table_counts_as_no_snapshot_and_says_why(monkeypatch, tmp_path, gemini, capsys):
    fake = digest_db(errors={"hot_topic_report_reviews": MISSING_TABLE})
    assert run(monkeypatch, fake, tmp_path) == 0
    data, _ = output(tmp_path, f"{WEEK}-rep-digest-1")
    assert data["input"] == "reconstructed"
    out = capsys.readouterr().out
    assert "hot_topic_report_reviews 表不存在" in out and "PGRST205" in out


@pytest.mark.parametrize("error", [
    APIError({"code": "42501", "message": "permission denied for table hot_topic_report_reviews"}),
    ConnectionError("連線逾時"),
])
def test_any_other_review_lookup_error_exits_1_without_falling_back(monkeypatch, tmp_path, gemini, capsys, error):
    fake = digest_db(errors={"hot_topic_report_reviews": error})
    assert run(monkeypatch, fake, tmp_path, "--regenerate") == 1
    assert str(error) in capsys.readouterr().err
    assert no_output(tmp_path)
    assert gemini.prompts == []


def test_a_review_record_supplies_the_input_snapshot(monkeypatch, tmp_path, gemini):
    fake = digest_db(tables={"hot_topic_report_reviews": [
        {"week_start_date": WEEK, "topic_label": DIGEST_TOPIC, "input_snapshot": "快照全文"}]})
    assert run(monkeypatch, fake, tmp_path) == 0
    data, _ = output(tmp_path, f"{WEEK}-rep-digest-1")
    assert data["input"] == "snapshot"
    assert data["original"]["input_text"] == "快照全文"


def test_a_review_record_of_another_report_is_not_used(monkeypatch, tmp_path, gemini):
    fake = digest_db(tables={"hot_topic_report_reviews": [
        {"week_start_date": "2026-10-26", "topic_label": DIGEST_TOPIC, "input_snapshot": "別週"},
        {"week_start_date": WEEK, "topic_label": "機車事故 · 彙整", "input_snapshot": "別題"}]})
    assert run(monkeypatch, fake, tmp_path) == 0
    data, _ = output(tmp_path, f"{WEEK}-rep-digest-1")
    assert data["input"] == "reconstructed"


# ── 找不到、重建失敗 ───────────────────────────────────────

def test_report_not_found_exits_1_and_names_it(monkeypatch, tmp_path, gemini, capsys):
    assert run(monkeypatch, digest_db(), tmp_path, "--regenerate", topic="不存在 · 彙整") == 1
    err = capsys.readouterr().err
    assert "找不到" in err and WEEK in err and "不存在 · 彙整" in err
    assert no_output(tmp_path)
    assert gemini.prompts == []


def test_a_source_missing_from_articles_fails_closed_and_names_the_link(monkeypatch, tmp_path, gemini, capsys):
    gone = "https://news.google.com/rss/articles/gone"
    fake = digest_db(tables={"hot_topic_reports": [
        report_row("rep-gone", DIGEST_TOPIC, [stored(A1), gone, stored(A3)], DIGEST_ORIGINAL)]})
    assert run(monkeypatch, fake, tmp_path, "--regenerate") == 1
    err = capsys.readouterr().err
    assert gone in err and A1["link"] not in err
    assert no_output(tmp_path)
    assert gemini.prompts == []


@pytest.mark.parametrize("table", ["hot_topic_reports", "articles"])
def test_a_failed_read_exits_1_naming_the_table(monkeypatch, tmp_path, gemini, capsys, table):
    fake = digest_db(errors={table: ConnectionError("連線逾時")})
    assert run(monkeypatch, fake, tmp_path, "--regenerate") == 1
    assert f"讀 {table} 失敗：連線逾時" in capsys.readouterr().err
    assert no_output(tmp_path)
    assert gemini.prompts == []


def test_an_unconfigured_client_exits_1_with_the_reason(monkeypatch, tmp_path, gemini, capsys):
    def unconfigured():
        raise RuntimeError("SUPABASE_URL 或金鑰未設定。")
    monkeypatch.setattr("src.storage._get_client", unconfigured)
    assert m.main(["--week", WEEK, "--topic", DIGEST_TOPIC, "--out", str(tmp_path / "out")]) == 1
    assert "SUPABASE_URL 或金鑰未設定。" in capsys.readouterr().err
    assert no_output(tmp_path)


def test_a_report_with_no_source_links_exits_1(monkeypatch, tmp_path, gemini, capsys):
    fake = digest_db(tables={"hot_topic_reports": [report_row("rep-empty", DIGEST_TOPIC, [], DIGEST_ORIGINAL)]})
    assert run(monkeypatch, fake, tmp_path) == 1
    assert "source_article_links" in capsys.readouterr().err
    assert no_output(tmp_path)


# ── 檢查（SC-001）與重生成 ───────────────────────────────────

def test_original_check_bites_on_the_published_digest(monkeypatch, tmp_path, gemini):
    assert run(monkeypatch, digest_db(), tmp_path) == 0
    data, _ = output(tmp_path, f"{WEEK}-rep-digest-1")
    hits = data["checks"]["original"]["hits"]
    assert hits["independence_claim"] == ["互相獨立"]
    assert hits["self_count"] == ["本期共收錄 3 起獨立事件"]
    assert hits["title_only_in_sections"] == ["[2]"]
    assert hits["date_unlabeled"] == ["11 月 5 日", "10 月 9 日"]
    assert data["checks"]["original"]["counts"]["date_unlabeled"] == 2
    assert data["checks"]["original"]["sc001"] == {
        "independence_claim": 1, "date_unlabeled": 2, "self_count": 1, "title_only_in_sections": 1}


def test_without_regenerate_no_gemini_call_and_regenerated_is_null(monkeypatch, tmp_path, gemini, capsys):
    assert run(monkeypatch, digest_db(), tmp_path) == 0
    data, md = output(tmp_path, f"{WEEK}-rep-digest-1")
    assert gemini.prompts == []
    assert data["regenerated"] is None and data["checks"]["regenerated"] is None
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("估算費用：US$0")
    assert lines[-1].startswith("token 數：0")
    assert DIGEST_ORIGINAL in md


def test_regenerate_digest_goes_through_build_digest_input_with_every_article(monkeypatch, tmp_path, gemini):
    assert run(monkeypatch, digest_db(), tmp_path, "--regenerate") == 0
    data, _ = output(tmp_path, f"{WEEK}-rep-digest-1")
    expected_list, expected_links, _ = analyzer.build_digest_input([A1, A2, A3], 3)
    assert len(gemini.prompts) == 1
    assert expected_list in gemini.prompts[0]
    assert f"[2] 報導日：2026-10-28\n    標題：{A1['title']}" in gemini.prompts[0]
    regen = data["regenerated"]
    assert regen["input_text"] == expected_list
    assert [s["link"] for s in regen["sources"]] == [l["link"] for l in expected_links] == [A3["link"], A1["link"], A2["link"]]
    assert regen["title_only_ids"] == [3]
    assert regen["text"].endswith(f"### 僅標題\n- {A2['title']} [3]")
    assert regen["model"] == "gemini-3.8-flash"


def test_regenerate_digest_keeps_every_article_beyond_the_default_and_config_caps(monkeypatch, tmp_path, gemini):
    # 30 篇＞analyze_category_digest 預設的 15、也＞設定檔的 25：重生成的輸入要是同一批，一篇都不丟（review c6e945c-1）
    many = [article(f"https://ex.com/m{i}", f"標題{i}", FILLER * 2, "2026-10-28T02:00:00+00:00", (100 - i) / 100)
            for i in range(30)]
    fake = digest_db(tables={"articles": many, "hot_topic_reports": [
        report_row("rep-30", DIGEST_TOPIC, [a["link"] for a in many], DIGEST_ORIGINAL)]})
    assert run(monkeypatch, fake, tmp_path, "--regenerate") == 0
    data, _ = output(tmp_path, f"{WEEK}-rep-30")
    assert [s["link"] for s in data["regenerated"]["sources"]] == [a["link"] for a in many]
    assert "[30] 報導日：" in gemini.prompts[0]


def test_regenerated_digest_checks_are_clean_and_both_checks_are_written(monkeypatch, tmp_path, gemini):
    assert run(monkeypatch, digest_db(), tmp_path, "--regenerate") == 0
    data, md = output(tmp_path, f"{WEEK}-rep-digest-1")
    regen = data["checks"]["regenerated"]
    assert regen["sc001"] == dict.fromkeys(SC001_CHECKS, 0)
    assert all(v == [] for v in regen["hits"].values())
    assert data["checks"]["original"]["counts"]["independence_claim"] == 1
    assert "| independence_claim | 1：互相獨立 | 0 |" in md.splitlines()
    assert DIGEST_ORIGINAL in md and data["regenerated"]["text"] in md


def test_regenerate_hot_goes_through_build_hot_topic_input(monkeypatch, tmp_path, gemini):
    gemini.reply = HOT_REGENERATED_RAW
    assert run(monkeypatch, hot_db(), tmp_path, "--regenerate", topic=HOT_TOPIC) == 0
    data, _ = output(tmp_path, f"{WEEK}-rep-hot-1")
    expected_list, _, _ = analyzer.build_hot_topic_input([B1, B2])
    assert expected_list in gemini.prompts[0]
    assert "摘要：（僅標題）" in gemini.prompts[0]
    assert data["regenerated"]["input_text"] == expected_list
    assert data["regenerated"]["text"] == HOT_REGENERATED_RAW
    assert data["checks"]["original"]["hits"]["interweave_sum"] == ["1+1+1=3≠2"]
    assert data["checks"]["original"]["hits"]["id_out_of_range"] == ["[5]"]
    assert all(v == [] for v in data["checks"]["regenerated"]["hits"].values())
    assert "self_count" not in data["checks"]["original"]["counts"]
    assert data["checks"]["original"]["sc001"] == {} == data["checks"]["regenerated"]["sc001"]


def test_failed_regeneration_exits_1_writes_nothing_and_says_tokens_not_obtained(monkeypatch, tmp_path, gemini, capsys):
    gemini.reply = None
    assert run(monkeypatch, digest_db(), tmp_path, "--regenerate") == 1
    captured = capsys.readouterr()
    assert "重生成" in captured.err
    assert no_output(tmp_path)
    assert captured.out.splitlines()[-1].startswith("token 數：未取得")


def test_missing_api_key_exits_1_with_the_reason(monkeypatch, tmp_path, gemini, capsys):
    def no_key():
        raise RuntimeError("GEMINI_API_KEY 環境變數未設定")
    monkeypatch.setattr(analyzer, "_get_api_key", no_key)
    assert run(monkeypatch, digest_db(), tmp_path, "--regenerate") == 1
    assert "GEMINI_API_KEY 環境變數未設定" in capsys.readouterr().err
    assert no_output(tmp_path)


# ── 費用與 token ─────────────────────────────────────────

def test_regenerate_prints_the_cost_estimate_first_and_tokens_not_obtained_last(monkeypatch, tmp_path, gemini, capsys):
    assert run(monkeypatch, digest_db(), tmp_path, "--regenerate") == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("估算費用：")
    assert "gemini-3.8-flash" in lines[0] and "0.0123" in lines[0] and "0.0246" in lines[0]
    assert lines[-1].startswith("token 數：未取得") and "usageMetadata" in lines[-1]
    data, _ = output(tmp_path, f"{WEEK}-rep-digest-1")
    assert data["usage"]["tokens"] is None and "usageMetadata" in data["usage"]["tokens_note"]
    assert isinstance(data["usage"]["seconds"], float)


def test_a_model_without_a_measured_price_says_so(monkeypatch, tmp_path, gemini, capsys):
    monkeypatch.setattr(analyzer, "GEMINI_MODEL", "gemini-9-unknown")
    assert run(monkeypatch, digest_db(), tmp_path, "--regenerate") == 0
    first = capsys.readouterr().out.splitlines()[0]
    assert first.startswith("估算費用：未知") and "gemini-9-unknown" in first
