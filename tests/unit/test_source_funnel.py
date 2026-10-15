"""014 C1：逐來源漏斗。先測純函數（記帳與格式），再跑一次真的 collect() → filter()，只換邊界。
行格式是契約（週驗收 routine grep 它），所以用字面值寫，不從程式裡的常數推。"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.pipeline.traffic import (  # noqa: E402
    TrafficCategory, confluence_categories, funnel_line, source_funnel,
)


def _a(source, cat=None):
    return {"source": source, "major_category": cat}


# ── 純函數：source_funnel ──────────────────────────────────────

def test_attempted_source_with_zero_articles_gets_an_all_zero_row():
    """C1-1：收了 0 篇的來源只出現在嘗試名單，也要有一列；沉默與「跑了但沒東西」分不出來。"""
    x = _a("甲")
    funnel = source_funnel(["甲", "空"], [[x]] * 7, set())
    assert funnel == {"甲": (1, 1, 1, 1, 1, 1, 1, 0), "空": (0, 0, 0, 0, 0, 0, 0, 0)}


def test_counts_never_increase_across_stages():
    """C1-2：每一關都是前一關的子集。Jaccard 留下較長那篇時，算在留下那篇的來源（y1 取代 x2）。"""
    x1, x2, x3, y1, y2, z1 = _a("X"), _a("X"), _a("X"), _a("Y", "主類A"), _a("Y"), _a("Z")
    stages = [
        [x1, x2, x3, y1, y2, z1],
        [x1, x2, y1, y2, z1],
        [x1, x2, y1, z1],
        [x1, x2, y1],
        [x1, y1],
        [x1, y1],
        [y1],
    ]
    funnel = source_funnel(["X", "Y", "Z"], stages, {"主類A"})
    assert funnel == {
        "X": (3, 2, 2, 2, 1, 1, 0, 0),
        "Y": (2, 2, 1, 1, 1, 1, 1, 1),
        "Z": (1, 1, 1, 0, 0, 0, 0, 0),
    }
    assert all(row[i] >= row[i + 1] for row in funnel.values() for i in range(7))


def test_confluence_count_only_counts_confluence_categories():
    final = [_a("S", "主類A"), _a("S", "併入B"), _a("S", "無關C"), _a("S", None)]
    funnel = source_funnel(["S"], [final] * 7, {"主類A", "併入B"})
    assert funnel == {"S": (4, 4, 4, 4, 4, 4, 4, 2)}


def test_vector_stage_unchanged_means_f_equals_e():
    """C1-3：向量去重沒跑時 f 那關就是 e 那關的同一個 list，f 照 e 印，不印成 0。"""
    x1, x2, y1 = _a("X"), _a("X"), _a("Y")
    deduped = [x1, y1]
    stages = [[x1, x2, y1], [x1, x2, y1], [x1, x2, y1], [x1, x2, y1], deduped, deduped, deduped]
    funnel = source_funnel(["X", "Y"], stages, set())
    assert funnel == {"X": (2, 2, 2, 2, 1, 1, 1, 0), "Y": (1, 1, 1, 1, 1, 1, 1, 0)}


def test_sources_outside_the_attempted_list_follow_in_first_appearance_order():
    raw = [_a("丙"), _a("甲"), _a("丁"), _a("丙")]
    funnel = source_funnel(["乙", "甲"], [raw] * 7, set())
    assert list(funnel) == ["乙", "甲", "丙", "丁"]
    assert funnel["乙"] == (0,) * 8 and funnel["丙"] == (2,) * 7 + (0,)


# ── 純函數：funnel_line、confluence_categories ─────────────────

def test_line_matches_the_contract_text():
    line = funnel_line("交通部", (30, 25, 20, 18, 15, 15, 12, 4))
    assert line == ("[來源漏斗] 交通部：收集 30 → 新鮮度 25 → 過濾 20 → 封鎖 18 → "
                    "同批去重 15 → 向量去重 15 → 寫入上限 12（匯流四類 4）")


def test_confluence_categories_are_derived_from_category_digest():
    """匯流類別＝每個 digest 的主類別＋其 include_categories；類別名一律來自設定。"""
    config = {"category_digest": {"主類A": {"include_categories": ["併入B", "併入C"]},
                                  "主類D": {}}}
    assert confluence_categories(config) == {"主類A", "併入B", "併入C", "主類D"}
    assert confluence_categories({}) == set()
    assert confluence_categories({"category_digest": None}) == set()


# ── 真的 collect() → filter()，只換邊界 ─────────────────────────

SOURCES = [{"name": n, "type": "rss"} for n in ("甲台", "乙台", "丙台", "空台", "封鎖台")]


def _raw(n, source, title, **extra):
    return {"title": title, "link": f"https://example.com/{n}", "summary": "",
            "source": source, "published": "", **extra}


RAW = [
    _raw(1, "甲台", "台北機車路權新制上路"),
    _raw(2, "甲台", "【聯合報】台北機車路權新制上路"),               # 同批去重（去掉媒體標籤後同 token）
    _raw(3, "甲台", "機車族注意舊制", published="2020-01-01T00:00:00+00:00"),  # 新鮮度
    _raw(4, "甲台", "颱風來襲停班停課"),                              # 過濾（無機車關鍵字）
    _raw(5, "甲台", "機車保養業配優惠"),                              # 封鎖（內容關鍵字）
    _raw(6, "乙台", "公路局召開說明會", relevance_exempt=True),
    _raw(7, "乙台", "交通部公告修法草案", relevance_exempt=True),
    _raw(8, "丙台", "騎士夜間安全宣導"),
    _raw(9, "封鎖台", "機車停車格增設"),                              # 封鎖（來源）
]

CONFIG = {
    "blocked_sources": ["封鎖"],
    "blocked_content_keywords": ["業配"],
    "jaccard": {"merge_threshold": 0.45},
    "buffer": {"max_daily_articles": 3},
    "source_weights": {"甲台": 1.0, "乙台": 0.0, "丙台": 1.0},
    "category_digest": {"主類A": {"include_categories": ["併入B"]}},
}


@pytest.fixture
def boundary(monkeypatch):
    calls = []

    def no_file_read():
        raise AssertionError("collect(sources) 不該再讀 sources 設定檔")

    monkeypatch.setattr("src.collector.load_sources", no_file_read)
    monkeypatch.setattr("src.collector.collect_sources", lambda srcs: calls.append(srcs) or [dict(a) for a in RAW])
    monkeypatch.setattr("src.storage.is_configured", lambda: False)
    monkeypatch.setattr("src.pipeline_config.load_pipeline_config", lambda *a, **k: CONFIG)
    monkeypatch.setattr("src.pipeline_config.load_category_taxonomy", lambda *a, **k: {})
    monkeypatch.setattr("src.pipeline_config.load_source_default_categories",
                        lambda *a, **k: {"甲台": "主類A", "乙台": "併入B", "丙台": "無關C"})
    return calls


def _funnel_lines(caplog):
    return [m for m in caplog.messages if m.startswith("[來源漏斗] ")]


def test_real_filter_records_and_logs_the_funnel_per_source(boundary, caplog):
    """每關各有一篇掉在甲台，甲台那行就把每一關對到 filter() 裡哪個 list 釘死；空台收 0 篇也有一行。"""
    cat = TrafficCategory()
    with caplog.at_level(logging.INFO, logger="src.pipeline.traffic"):
        kept = cat.filter(cat.collect(SOURCES))

    lines = _funnel_lines(caplog)
    assert "[來源漏斗] 空台：收集 0 → 新鮮度 0 → 過濾 0 → 封鎖 0 → 同批去重 0 → 向量去重 0 → 寫入上限 0（匯流四類 0）" in lines
    assert "[來源漏斗] 甲台：收集 5 → 新鮮度 4 → 過濾 3 → 封鎖 2 → 同批去重 1 → 向量去重 1 → 寫入上限 1（匯流四類 1）" in lines
    assert cat.last_funnel == {
        "甲台": (5, 4, 3, 2, 1, 1, 1, 1),
        "乙台": (2, 2, 2, 2, 2, 2, 1, 1),
        "丙台": (1, 1, 1, 1, 1, 1, 1, 0),
        "空台": (0, 0, 0, 0, 0, 0, 0, 0),
        "封鎖台": (1, 1, 1, 0, 0, 0, 0, 0),
    }
    assert list(cat.last_funnel) == ["甲台", "乙台", "丙台", "空台", "封鎖台"]
    assert lines == [funnel_line(n, c) for n, c in cat.last_funnel.items()]
    assert all(c[5] == c[4] for c in cat.last_funnel.values())  # C1-3：未設定 Supabase，向量去重沒跑
    assert boundary == [SOURCES]
    assert [a["title"] for a in kept] == ["台北機車路權新制上路", "騎士夜間安全宣導", "交通部公告修法草案"]


def _fake_embeddings(articles):
    vectors = {"甲台": [0.0, 1.0], "乙台": [1.0, 0.0], "丙台": [0.6, -0.8]}  # 乙台兩篇同向量
    for a in articles:
        a["embedding"] = vectors[a["source"]]


def test_vector_dedup_drop_is_counted_in_the_vector_stage(boundary, monkeypatch, caplog):
    """向量去重真的跑時，被它擋掉的那篇要落在「向量去重」那關，不能算進前後兩關。"""
    monkeypatch.setattr("src.storage.is_configured", lambda: True)
    monkeypatch.setattr("src.storage.get_existing_title_fingerprints", lambda: set())
    monkeypatch.setattr("src.storage.get_traffic_buffer", lambda *a, **k: [])
    monkeypatch.setattr("src.storage.get_recent_consumed_traffic", lambda *a, **k: [])
    monkeypatch.setattr("src.analyzer.attach_embeddings", _fake_embeddings)
    cat = TrafficCategory()
    with caplog.at_level(logging.INFO, logger="src.pipeline.traffic"):
        cat.filter(cat.collect(SOURCES))
    assert "[來源漏斗] 乙台：收集 2 → 新鮮度 2 → 過濾 2 → 封鎖 2 → 同批去重 2 → 向量去重 1 → 寫入上限 1（匯流四類 1）" in _funnel_lines(caplog)


def test_vector_dedup_failure_prints_f_as_e(boundary, monkeypatch, caplog):
    """C1-3 的另一條路：向量去重拋例外而略過時，f 照 e 印（不印成 0），並留下既有的 warning。"""
    def boom(self, deduped, config, now=None):
        raise RuntimeError("Gemini 掛了")
    monkeypatch.setattr("src.storage.is_configured", lambda: True)
    monkeypatch.setattr("src.storage.get_existing_title_fingerprints", lambda: set())
    monkeypatch.setattr(TrafficCategory, "_embedding_dedup", boom)
    cat = TrafficCategory()
    with caplog.at_level(logging.INFO, logger="src.pipeline.traffic"):
        cat.filter(cat.collect(SOURCES))
    assert "嵌入去重複失敗，略過" in caplog.text
    assert "[來源漏斗] 乙台：收集 2 → 新鮮度 2 → 過濾 2 → 封鎖 2 → 同批去重 2 → 向量去重 2 → 寫入上限 1（匯流四類 1）" in _funnel_lines(caplog)
    assert all(c[5] == c[4] for c in cat.last_funnel.values())


def test_config_failure_clears_the_previous_funnel_and_prints_nothing(boundary, monkeypatch, caplog):
    """分類設定載入失敗走早退：既有 warning 就是訊號，不印漏斗；上一次的 last_funnel 不可殘留。"""
    def broken(*a, **k):
        raise RuntimeError("設定壞了")
    monkeypatch.setattr("src.pipeline_config.load_pipeline_config", broken)
    cat = TrafficCategory()
    cat.last_funnel = {"上一次": (1,) * 8}
    with caplog.at_level(logging.INFO, logger="src.pipeline.traffic"):
        cat.filter(cat.collect(SOURCES))
    assert _funnel_lines(caplog) == []
    assert cat.last_funnel == {}
