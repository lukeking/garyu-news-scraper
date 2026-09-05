"""`scripts/replay_digest_pool.py` 的契約——在此之前零測試，而 BACKLOG #8 的決定局讀
它的數字。優先守「靜靜算少了／算多了」那幾條路。邊界只換 gh 與 DB，選材用真的。
"""
import io
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

import replay_digest_pool as rp  # noqa: E402

CATEGORY = "道安政策"
SIBLING = "交通法規"
CFG = {"quality_floor": 0.2, "max_articles": 15,
       "include_categories": [SIBLING], "trigger_count": 10}


def _patch_line(*links):
    """一行 PostgREST PATCH，連結以 URL 編碼躺在 `in.(...)` 裡——log 裡唯一的池成員紀錄。"""
    inner = "%2C".join(f"%22{l}%22" for l in links)
    return f'time=x PATCH https://x.supabase.co/rest/v1/articles?link=in.%28{inner}%29 "HTTP/2 204"'


def _fake_gh(monkeypatch, stdout):
    monkeypatch.setattr(
        rp.subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(stdout=stdout, returncode=0),
    )


def test_pool_is_reconstructed_from_every_patch_call_not_just_the_first():
    """池成員散在多次 PATCH 裡；只讀第一次就會靜靜地重建出一個比較小的池。"""
    log = "\n".join([
        "some unrelated line",
        _patch_line("https://a.test/1", "https://a.test/2"),
        "GET https://x.supabase.co/rest/v1/articles?select=link",
        _patch_line("https://a.test/2", "https://a.test/3"),
    ])
    got = rp.PATCH_LINKS.findall(log)
    assert len(got) == 2, "兩次 PATCH 都要被抓到"

    import urllib.parse
    links = sorted({
        s.strip('"')
        for m in got
        for s in urllib.parse.unquote(m).split('","')
    })
    assert links == ["https://a.test/1", "https://a.test/2", "https://a.test/3"]


def test_both_comma_encodings_decode(monkeypatch):
    """log 裡的分隔逗號可能是 %2C 也可能是字面 `,`，兩種都得解得出同一組連結。"""
    for sep in ("%2C", ","):
        inner = sep.join(f"%22https://a.test/{i}%22" for i in (1, 2))
        _fake_gh(monkeypatch, f'x PATCH /rest/v1/articles?link=in.%28{inner}%29 "HTTP/2 204"')
        assert rp.links_from_log("1", "o/r") == ["https://a.test/1", "https://a.test/2"]


def test_only_the_marking_calls_carry_that_url_shape():
    """重建假設 log 裡 `link=in.(...)` 只來自標記用的 PATCH。多一個 GET 就會靜靜灌水。"""
    src = io.open(os.path.join(os.path.dirname(__file__), "..", "..",
                               "src", "storage.py"), encoding="utf-8").read()
    sites = [i for i in range(len(src)) if src.startswith('.in_(', i)]
    assert len(sites) == 2, "src/storage.py 的 `.in_(` 呼叫點數變了——確認新的那個不是 GET"
    for i in sites:
        assert 'update({"hot_topic_analyzed": True})' in src[max(0, i - 200):i], \
            "新的 `.in_(` 不在 update() 鏈上，那它就是 GET，會被當成池成員讀進去"


def test_links_from_log_dedupes_and_sorts(monkeypatch):
    _fake_gh(monkeypatch, "\n".join([
        _patch_line("https://a.test/2", "https://a.test/1"),
        _patch_line("https://a.test/1"),
    ]))
    assert rp.links_from_log("123", "o/r") == ["https://a.test/1", "https://a.test/2"]


def test_unreadable_log_fails_closed_instead_of_replaying_an_empty_pool(monkeypatch):
    """log 過期被清掉時回空池，會讓 SC-001 讀出一組「全部歸零」而看起來像真的。"""
    _fake_gh(monkeypatch, "")
    with pytest.raises(SystemExit):
        rp.links_from_log("123", "o/r")


def test_missing_category_config_fails_closed(monkeypatch):
    import src.pipeline_config as pc
    monkeypatch.setattr(pc, "load_pipeline_config", lambda: {"category_digest": {}})
    with pytest.raises(SystemExit):
        rp.digest_config(CATEGORY)


def test_every_link_is_queried_even_when_the_batch_does_not_divide_evenly(monkeypatch):
    """25 條連結分 10/10/5 三批；尾批掉了就是靜靜少算 5 篇。"""
    links = [f"https://a.test/{i}" for i in range(25)]
    rows = [{"link": l, "major_category": CATEGORY} for l in links]
    rows.append({"link": "https://other.test/x", "major_category": "機車事故"})
    asked = []

    class _T:
        def select(self, *a): return self
        def in_(self, col, batch):
            asked.append(list(batch)); self._b = set(batch); return self
        def execute(self):
            return types.SimpleNamespace(data=[r for r in rows if r["link"] in self._b])

    import src.storage as st
    monkeypatch.setattr(st, "_get_client", lambda: types.SimpleNamespace(table=lambda n: _T()))

    got = rp.rows_for(links + ["https://other.test/x"], [CATEGORY, SIBLING])
    assert [len(b) for b in asked] == [10, 10, 6]
    assert sorted(l for b in asked for l in b) == sorted(links + ["https://other.test/x"])
    assert {r["link"] for r in got} == set(links), "非本池類別要被濾掉"


def test_report_keeps_the_two_denominators_apart(capsys):
    """匯流與不匯流是兩個分母，混用會讓 SC-001 讀出一個不存在的數字。"""
    rows = (
        [{"link": f"u{i}", "title": "t", "source": "聯合",
          "major_category": CATEGORY, "initial_quality_score": 0.5} for i in range(6)]
        + [{"link": f"c{i}", "title": "t", "source": "中時",
            "major_category": CATEGORY, "initial_quality_score": 0.5} for i in range(2)]
        + [{"link": f"l{i}", "title": "t", "source": "自由",
            "major_category": SIBLING, "initial_quality_score": 0.5} for i in range(5)]
    )
    rp.report(rows, CATEGORY, CFG)
    out = capsys.readouterr().out

    assert "現行(不匯流): pool=8" in out and "抽掉最大剩=2" in out
    assert "匯流: pool=13" in out and "抽掉最大剩=7" in out
    assert "匯流新進 5 篇" in out, "新進＝匯流選上而現行沒選上的那幾篇"
