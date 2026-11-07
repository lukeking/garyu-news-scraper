"""spec 018 T008：彙整與三軸的生成指令、build_digest_input()／build_hot_topic_input()、彙整報告的程式組裝。
截斷長度與計數用字面值；Gemini 一律換成假的，不碰網路。
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.analyzer import (  # noqa: E402
    DIGEST_PROMPT_TEMPLATE,
    DIGEST_SYSTEM_PROMPT,
    HOT_TOPIC_PROMPT_TEMPLATE,
    HOT_TOPIC_SYSTEM_PROMPT,
    analyze_category_digest,
    analyze_hot_topic,
    build_digest_input,
    build_hot_topic_input,
)
from src.report_review import check_report  # noqa: E402

NUMBERS_RULE = ("範圍、期間與基準", "不得加上來源沒有的範圍詞", "不得把統計定義的改變寫成因果")
REAL_B = "台中市自下月起在三處路口啟用科技執法設備，取締闖紅燈與未禮讓行人。" + "市府表示將視成效逐步擴大到其他路口。" * 30
REAL_D = "立法委員在交通委員會質詢交通部，要求說明行人路權改善計畫的進度與經費來源。"
REAL_E = "某縣市道安會報討論校園周邊人行道改善，決議下個月由工務局提出具體工程規劃與預算需求。"
TITLE_A = "新北道安會報強化路口安全 - 自由時報"
TITLE_C = "交通部公布前七月道安統計 - 聯合新聞網"


def _article(title, summary, score, published, link):
    return {"title": title, "summary": summary, "initial_quality_score": score,
            "published": published, "link": link}


def _pool():
    """A、C 只有標題；E 分數最低，max_articles=4 時落選。"""
    return [
        _article("某縣市道安會報", REAL_E, None, "2026-09-30T02:00:00+00:00", "https://e"),
        _article("立委質詢行人路權", REAL_D, 6, "2026-10-01T03:00:00+00:00", "https://d"),
        _article(TITLE_C, "", 7, "2026-10-06T04:00:00+00:00", "https://c"),
        _article("台中市科技執法上路", REAL_B, 8, "2026-10-03T01:00:00+00:00", "https://b"),
        _article(TITLE_A, "新北道安會報強化路口安全  自由時報", 9, "2026-10-05T08:00:00+00:00", "https://a"),
    ]


def _fake_gemini(monkeypatch, reply):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-not-a-real-key")
    calls = []

    def fake(prompt, api_key, retries=None, system_prompt=None):
        calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return reply
    monkeypatch.setattr("src.analyzer._call_gemini", fake)
    return calls


def _between(text, start, end):
    return text.split(start, 1)[1].split(end, 1)[0]


CANNED_DIGEST = """
### 本期概覽
本期涵蓋地方科技執法與中央質詢兩個面向。

### 分節彙整
#### 地方政策
- 10 月 3 日報導，台中市在三處路口啟用科技執法 [1]。
#### 中央質詢
- 10 月 1 日報導，立委質詢行人路權 [2]。

### 待追蹤
- 台中市將視成效擴大 [1]。
"""


# ── 彙整指令（FR-001、FR-002、FR-003、FR-005） ──────────────────────────────────

def test_digest_prompts_have_no_independence_claim():
    """兩段彙整指令都不再宣告事件互相獨立，也不出現檢查會抓的另兩個詞。"""
    for text in (DIGEST_SYSTEM_PROMPT, DIGEST_PROMPT_TEMPLATE):
        for word in ("互相獨立", "各事件互相獨立", "各自獨立", "無直接因果"):
            assert word not in text


def test_digest_prompts_forbid_inferring_relations():
    """不得自行推論關聯；來源明文寫出的照寫並標 Article ID。"""
    for text in (DIGEST_SYSTEM_PROMPT, DIGEST_PROMPT_TEMPLATE):
        assert "不得自行推論事件之間的因果、趨勢或" in text
        assert "來源明文寫出的關聯照寫" in text
        assert "Article ID" in text


def test_digest_template_says_dates_are_report_dates():
    """清單日期是報導日；寫時間標報導日，除非來源寫出事件日。"""
    assert "每篇的日期是報導日" in DIGEST_PROMPT_TEMPLATE
    instructions = _between(DIGEST_PROMPT_TEMPLATE, "【彙整指令】", "【輸出格式】")
    assert "報導日" in instructions
    assert "除非來源明文寫出事件發生的日期" in instructions


def test_digest_template_overview_leaves_counts_to_program():
    """本期概覽不要模型數篇數或事件數。"""
    overview = _between(DIGEST_PROMPT_TEMPLATE, "### 本期概覽", "### 分節彙整")
    assert "共幾個" not in DIGEST_PROMPT_TEMPLATE
    assert "不要寫篇數或事件數" in overview


def test_digest_template_has_numbers_rule():
    """FR-005 的數字規則在彙整指令裡。"""
    instructions = _between(DIGEST_PROMPT_TEMPLATE, "【彙整指令】", "【輸出格式】")
    for phrase in NUMBERS_RULE:
        assert phrase in instructions


def test_digest_template_formats_cleanly():
    """佔位符照舊，format 後不留大括號。"""
    out = DIGEST_PROMPT_TEMPLATE.format(topic_label="T", date_start="S", date_end="E",
                                        article_count=3, article_list="LIST")
    assert "LIST" in out and "「T」" in out and "3 篇" in out
    assert "{" not in out and "}" not in out


# ── build_digest_input（FR-002、FR-004） ─────────────────────────────────────────

def test_build_digest_input_lists_only_summarised_articles_with_report_date():
    """有摘要的編 [1]..[K]，用「報導日：」；只有標題的不在清單。"""
    article_list, _, _ = build_digest_input(_pool(), 4)
    expected = (
        "[1] 報導日：2026-10-03\n    標題：台中市科技執法上路\n    摘要：" + REAL_B[:400]
        + "\n\n[2] 報導日：2026-10-01\n    標題：立委質詢行人路權\n    摘要：" + REAL_D
    )
    assert article_list == expected
    assert "日期：" not in article_list.replace("報導日：", "")
    assert TITLE_A not in article_list and TITLE_C not in article_list
    assert "[3]" not in article_list


def test_build_digest_input_truncates_summary_at_400():
    """清單的摘要截 400 字。"""
    article_list, _, _ = build_digest_input(_pool(), 4)
    first = article_list.split("\n\n")[0]
    assert len(first.split("摘要：", 1)[1]) == 400


def test_build_digest_input_orders_links_summarised_first():
    """ordered_links 依 [1]..[N]：有摘要的在前、只有標題的接在後，組內照分數。"""
    _, links, counts = build_digest_input(_pool(), 4)
    assert [x["link"] for x in links] == ["https://b", "https://d", "https://a", "https://c"]
    assert links[2] == {"title": TITLE_A, "link": "https://a", "summary": "新北道安會報強化路口安全  自由時報"}
    assert links[3] == {"title": TITLE_C, "link": "https://c", "summary": ""}
    assert len(links[0]["summary"]) == 200 and links[0]["summary"] == REAL_B[:200]
    assert counts == {"articles": 4, "title_only": 2}


def test_build_digest_input_selects_by_score_before_splitting():
    """先依分數取 max_articles 篇再分組：低分的有摘要報導落選，高分的只有標題報導留下。"""
    _, links, counts = build_digest_input(_pool(), 5)
    assert [x["link"] for x in links] == ["https://b", "https://d", "https://e", "https://a", "https://c"]
    assert counts == {"articles": 5, "title_only": 2}
    _, links, counts = build_digest_input(_pool(), 1)
    assert [x["link"] for x in links] == ["https://a"]
    assert counts == {"articles": 1, "title_only": 1}


# ── analyze_category_digest 的組裝（FR-003、FR-004） ─────────────────────────────

def test_digest_report_gets_program_count_line_and_title_only_section(monkeypatch):
    """概覽第一行是程式寫的計數；文末 ### 僅標題 逐行照抄原標題附 ID。"""
    calls = _fake_gemini(monkeypatch, CANNED_DIGEST)
    report, links = analyze_category_digest(_pool(), "道安政策 · 彙整", "2026-10-05", 4)
    expected = (
        "### 本期概覽\n本期收錄 4 篇報導，其中 2 篇只有標題。\n" + CANNED_DIGEST.strip().split("\n", 1)[1]
        + "\n\n### 僅標題\n- " + TITLE_A + " [3]\n- " + TITLE_C + " [4]"
    )
    assert report == expected
    assert links == build_digest_input(_pool(), 4)[1]
    assert len(calls) == 1


def test_digest_prompt_holds_only_the_summarised_list(monkeypatch):
    """送給模型的是 K 篇的清單；篇數與日期區間都只算清單裡的。"""
    calls = _fake_gemini(monkeypatch, CANNED_DIGEST)
    analyze_category_digest(_pool(), "道安政策 · 彙整", "2026-10-05", 4)
    article_list, _, _ = build_digest_input(_pool(), 4)
    assert calls[0]["prompt"] == DIGEST_PROMPT_TEMPLATE.format(
        topic_label="道安政策 · 彙整", date_start="2026-10-01", date_end="2026-10-03",
        article_count=2, article_list=article_list,
    )
    assert calls[0]["system_prompt"] == DIGEST_SYSTEM_PROMPT
    assert TITLE_A not in calls[0]["prompt"]


def test_assembled_digest_passes_structural_checks(monkeypatch):
    """組裝出來的報告過 check_report 的缺節、自數、只有標題進分節三項。"""
    _fake_gemini(monkeypatch, CANNED_DIGEST)
    report, _ = analyze_category_digest(_pool(), "道安政策 · 彙整", "2026-10-05", 4)
    by_link = {a["link"]: a for a in _pool()}
    sources = [by_link[link] for link in ("https://b", "https://d", "https://a", "https://c")]
    result = check_report(report, template="digest", sources=sources, title_only_ids=[3, 4])
    assert result["missing_section"] == []
    assert result["self_count"] == []
    assert result["title_only_in_sections"] == []
    assert result["id_out_of_range"] == []


def test_digest_without_title_only_has_no_title_only_section(monkeypatch):
    """沒有只有標題的報導時，計數照寫 0 篇，不加 ### 僅標題。"""
    _fake_gemini(monkeypatch, CANNED_DIGEST)
    pool = [a for a in _pool() if a["link"] in ("https://b", "https://d")]
    report, links = analyze_category_digest(pool, "道安政策 · 彙整", "2026-10-05", 4)
    assert report.splitlines()[1] == "本期收錄 2 篇報導，其中 0 篇只有標題。"
    assert "### 僅標題" not in report
    assert len(links) == 2


def test_digest_count_line_goes_after_first_overview_heading(monkeypatch):
    """計數行插在第一個 ### 本期概覽 那一行之後（行尾空白不影響），只插一次。"""
    _fake_gemini(monkeypatch, "前言一行\n### 本期概覽  \n概覽甲\n### 本期概覽\n概覽乙")
    report, _ = analyze_category_digest(_pool(), "道安政策 · 彙整", "2026-10-05", 4)
    lines = report.splitlines()
    assert lines[:4] == ["前言一行", "### 本期概覽  ", "本期收錄 4 篇報導，其中 2 篇只有標題。", "概覽甲"]
    assert report.count("本期收錄") == 1
    assert report.count("### 本期概覽") == 2


def test_digest_without_overview_heading_gets_one_prepended(monkeypatch):
    """模型沒寫 ### 本期概覽 時，程式在最前面補上標題與計數行。"""
    _fake_gemini(monkeypatch, "### 分節彙整\n- 甲 [1]\n\n### 待追蹤\n本期無")
    report, _ = analyze_category_digest(_pool(), "道安政策 · 彙整", "2026-10-05", 4)
    assert report.startswith("### 本期概覽\n本期收錄 4 篇報導，其中 2 篇只有標題。\n\n### 分節彙整\n")


def test_digest_all_title_only_skips_generation(monkeypatch, caplog):
    """全部只有標題就不呼叫模型，回空並印出原因。"""
    calls = _fake_gemini(monkeypatch, CANNED_DIGEST)
    pool = [a for a in _pool() if a["link"] in ("https://a", "https://c")]
    with caplog.at_level(logging.WARNING, logger="src.analyzer"):
        result = analyze_category_digest(pool, "道安政策 · 彙整", "2026-10-05", 4)
    assert result == ("", [])
    assert calls == []
    assert any("全部只有標題" in r.getMessage() and "道安政策 · 彙整" in r.getMessage() for r in caplog.records)


def test_digest_empty_pool_and_failed_call_return_empty(monkeypatch, caplog):
    """空池不呼叫模型、也不報成全部只有標題；模型回空字串時照舊回 ("", [])。"""
    calls = _fake_gemini(monkeypatch, "")
    with caplog.at_level(logging.WARNING, logger="src.analyzer"):
        assert analyze_category_digest([], "道安政策 · 彙整", "2026-10-05", 4) == ("", [])
    assert calls == []
    assert not any("全部只有標題" in r.getMessage() for r in caplog.records)
    assert analyze_category_digest(_pool(), "道安政策 · 彙整", "2026-10-05", 4) == ("", [])
    assert len(calls) == 1


# ── 三軸指令（FR-004、FR-005、FR-005a、FR-006） ───────────────────────────────────

def test_hot_template_axis_c_has_numbers_rule():
    """FR-005 的數字規則在 C 軸。"""
    axis_c = _between(HOT_TOPIC_PROMPT_TEMPLATE, "▌ C", "【輸出格式】")
    for phrase in NUMBERS_RULE:
        assert phrase in axis_c


def test_hot_template_marks_title_only_citations():
    """摘要寫（僅標題）的報導，引用時標「僅標題」，不補寫主詞、範圍或日期。"""
    head = HOT_TOPIC_PROMPT_TEMPLATE.split("【分析指令】", 1)[0]
    assert "（僅標題）" in head
    assert "標「僅標題」" in head
    assert "不得補寫標題沒有的主詞、範圍或日期" in head


def test_hot_template_axis_a_has_no_accident_exit():
    """A 軸在本批沒有事故時寫「本批無事故報導，不適用」，輸出格式把它列成交織度分布那一段的替代。"""
    axis_a = _between(HOT_TOPIC_PROMPT_TEMPLATE, "▌ A", "▌ B")
    assert "本批無事故報導，不適用" in axis_a
    section_one = _between(HOT_TOPIC_PROMPT_TEMPLATE, "### 一、", "### 二、")
    assert "本批無事故報導，不適用" in section_one
    assert section_one.index("本批無事故報導，不適用") < section_one.index("交織度分布：")


def test_hot_template_allows_source_not_stated():
    """人因與工程欄可寫「來源未載」，不寫成斷言、不標成證據。"""
    axis_a = _between(HOT_TOPIC_PROMPT_TEMPLATE, "▌ A", "▌ B")
    assert "來源未載" in axis_a and "不得寫成斷言" in axis_a and "標成證據" in axis_a
    lines = HOT_TOPIC_PROMPT_TEMPLATE.splitlines()
    for field in ("人因變數：", "工程變數："):
        line = next(x for x in lines if x.startswith(field))
        assert "來源未載" in line


def test_hot_template_formats_cleanly():
    """佔位符照舊，format 後不留大括號。"""
    out = HOT_TOPIC_PROMPT_TEMPLATE.format(topic_label="T", article_count=3, article_list="LIST")
    assert "LIST" in out and "「T」" in out and "共 3 篇" in out
    assert "{" not in out and "}" not in out


# ── build_hot_topic_input 與 analyze_hot_topic ─────────────────────────────────

def _hot_bucket():
    """11 篇，分數 11..1；分數第 2 高的只有標題，第 3 高的摘要超過 600 字。"""
    body = "記者在現場訪問多名騎士與附近居民，了解事故經過與路口設計。"
    bucket = [_article(f"熱點{i}", f"第{i}篇報導的內文，" + body, 12 - i, "", f"https://h{i}") for i in range(1, 12)]
    bucket[1]["summary"] = "熱點2"
    bucket[2]["summary"] = "第3篇報導的內文，" + body * 30
    return list(reversed(bucket))


def test_build_hot_topic_input_marks_title_only_in_place():
    """前 10 篇照分數編號不重排；只有標題的摘要寫（僅標題）；摘要截 600 字。"""
    article_list, links, counts = build_hot_topic_input(_hot_bucket())
    entries = article_list.split("\n\n")
    assert len(entries) == 10
    assert entries[0] == "[1] 標題：熱點1\n    摘要：第1篇報導的內文，記者在現場訪問多名騎士與附近居民，了解事故經過與路口設計。"
    assert entries[1] == "[2] 標題：熱點2\n    摘要：（僅標題）"
    assert len(entries[2].split("摘要：", 1)[1]) == 600
    assert "熱點11" not in article_list
    assert [x["link"] for x in links] == [f"https://h{i}" for i in range(1, 11)]
    assert links[1] == {"title": "熱點2", "link": "https://h2", "summary": "熱點2"}
    assert len(links[2]["summary"]) == 200
    assert counts == {"articles": 10, "title_only": 1}


def test_analyze_hot_topic_uses_built_input(monkeypatch):
    """analyze_hot_topic 送出的 prompt 用 build_hot_topic_input 的清單，回傳值照舊。"""
    calls = _fake_gemini(monkeypatch, "\n### 一、 事故因果解構\n本批無事故報導，不適用\n")
    report, links = analyze_hot_topic(_hot_bucket(), "道安政策 · 交通安全", "2026-10-05")
    article_list, expected_links, _ = build_hot_topic_input(_hot_bucket())
    assert calls[0]["prompt"] == HOT_TOPIC_PROMPT_TEMPLATE.format(
        topic_label="道安政策 · 交通安全", article_count=10, article_list=article_list)
    assert calls[0]["system_prompt"] == HOT_TOPIC_SYSTEM_PROMPT
    assert report == "### 一、 事故因果解構\n本批無事故報導，不適用"
    assert links == expected_links
