"""Unit tests for the analyzer input-quality measurement (BACKLOG #11).

Synthetic data only — these never touch Supabase. What they guard is the
denominator and the classification order, because both are the ways this metric
can silently turn into a reassuring number that cannot fail:

- the denominator must keep the Google-News-unresolved rows (36.8% of the
  population). Dropping them is exactly how measure_body_fetch.py reported a
  healthy 84.8% while the analyzer was being fed title echoes.
- normalisation must happen before classification. 7.5% of rows arrive as an
  <a> blob whose anchor text is the title; classified raw they look like
  content, stripped they are title echoes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.measure_input_quality import (  # noqa: E402
    CLASSES,
    MIN_BOILERPLATE,
    PREFIX_LEN,
    THIN_MAX_CHARS,
    boilerplate_keys,
    classify_row,
    effective_text,
    has_html_markup,
    is_echo,
    is_gn_unresolved,
    link_domain,
    measure,
    select_rows,
)

TITLE = "臺北市大同區發生機車事故 騎士送醫"

# 版型前言：長度必須 ≥ PREFIX_LEN，否則測到的會是別條路徑而不是 boilerplate
BOILER_LEAD = "本站提供最中立最公正最即時的各類型新聞報導，涵蓋政治、財經、社會、生活與國際"

# 真實形狀的 Google News anchor blob：錨點文字就是標題加來源名
GN_BLOB = (
    '<a href="https://news.google.com/rss/articles/CBMiVWh0dHBzOi8vbmV3cy5j'
    'bnllcy5jb20vbmV3cy9pZC82MTIzNDU2?oc=5" target="_blank">'
    "Uber擬在台推機車載客 交通部：法規禁載客、違法可罰平台最高2500萬元</a>"
    '&nbsp;&nbsp;<font color="#6f6f6f">news.cnyes.com</font>'
)
GN_TITLE = "Uber擬在台推機車載客 交通部：法規禁載客、違法可罰平台最高2500萬元"
GN_LINK = "https://news.google.com/rss/articles/CBMiVWh0dHBzOi8vbmV3cy5jbnll?oc=5"


def row(summary="", title=TITLE, link="https://example.com/a1",
        source="範例新聞", week_id="2026-W22", content_type="traffic",
        major_category="道安政策"):
    return {
        "title": title,
        "summary": summary,
        "link": link,
        "source": source,
        "week_id": week_id,
        "content_type": content_type,
        "major_category": major_category,
    }


class TestEffectiveText:
    def test_strips_tags_unescapes_entities_and_collapses_whitespace(self):
        assert effective_text(GN_BLOB) == (
            "Uber擬在台推機車載客 交通部：法規禁載客、違法可罰平台最高2500萬元 news.cnyes.com"
        )

    def test_plain_text_survives_unchanged(self):
        assert effective_text("  臺北市今晨發生連環車禍  ") == "臺北市今晨發生連環車禍"

    def test_missing_summary_is_empty(self):
        assert effective_text(None) == ""
        assert effective_text("") == ""
        assert effective_text("<p></p>\n  &nbsp; ") == ""

    def test_stripping_collapses_the_blob_to_a_fraction_of_its_length(self):
        """生產環境量到 stripped/raw 長度比中位數 0.15——這就是為什麼必須先正規化。"""
        assert len(effective_text(GN_BLOB)) < len(GN_BLOB) / 3


class TestFlags:
    def test_html_markup_is_detected_on_the_raw_summary(self):
        assert has_html_markup(GN_BLOB) is True
        assert has_html_markup("臺北市今晨發生連環車禍，警方已到場") is False
        assert has_html_markup(None) is False

    def test_gn_unresolved_link(self):
        assert is_gn_unresolved(GN_LINK) is True
        assert is_gn_unresolved("https://www.cna.com.tw/news/ahel/202601010001.aspx") is False
        assert is_gn_unresolved(None) is False

    def test_link_domain(self):
        assert link_domain("https://www.cna.com.tw/news/x.aspx") == "www.cna.com.tw"
        assert link_domain(GN_LINK) == "news.google.com"
        assert link_domain("") == ""


class TestSelectRows:
    def test_excludes_non_iso_week_ids(self):
        """整合測試曾把 "2025-W01-test" 寫進正式 articles 表，並讓一個已設定的
        指標偏移。這個分母不可以隨最後一個跑 pytest 的人而變。"""
        rows = [
            row(week_id="2026-W22"),
            row(week_id="2025-W01-test"),
            row(week_id="2025-W99-integration-test"),
            row(week_id=""),
        ]
        assert [r["week_id"] for r in select_rows(rows)] == ["2026-W22"]

    def test_excludes_other_content_types(self):
        rows = [row(content_type="traffic"), row(content_type="ffxiv")]
        assert [r["content_type"] for r in select_rows(rows)] == ["traffic"]

    def test_keeps_google_news_unresolved_rows(self):
        """GN 未還原的列**留在分母裡**。把它們排掉正是 measure_body_fetch.py
        產出一個不可能失敗的 84.8% 的方式。"""
        rows = [row(link=GN_LINK), row(link="https://www.cna.com.tw/news/x.aspx")]
        assert len(select_rows(rows)) == 2


class TestClassifyRow:
    def test_absent(self):
        assert classify_row(row(summary=""), set()) == "absent"
        assert classify_row(row(summary="<p>&nbsp;</p>"), set()) == "absent"

    def test_title_echo_plain(self):
        assert classify_row(row(summary=TITLE + " - 中央社"), set()) == "title_echo"

    def test_html_blob_that_echoes_the_title_classifies_as_title_echo(self):
        """承重的順序測試：先正規化、後分類。

        原始 summary 遠長於 THIN_MAX_CHARS，先分類就會被當成 substantive；
        剝掉標籤之後它只是標題加來源名。
        """
        raw = GN_BLOB
        assert len(raw) > THIN_MAX_CHARS      # 沒有正規化的話會落到 substantive
        assert is_echo(GN_TITLE, raw) is False   # 原始字串騙得過 echo 判準
        assert classify_row(
            row(summary=raw, title=GN_TITLE, link=GN_LINK), set()
        ) == "title_echo"

    def test_boilerplate(self):
        keys = {("fcl.example.com", BOILER_LEAD[:PREFIX_LEN])}
        r = row(summary=BOILER_LEAD + "。今日焦點：北市交通事故統計出爐",
                link="https://fcl.example.com/n/1")
        assert classify_row(r, keys) == "boilerplate"

    def test_thin_just_below_the_boundary(self):
        text = "新" * (THIN_MAX_CHARS - 1)
        assert classify_row(row(summary=text), set()) == "thin"

    def test_substantive_at_the_boundary(self):
        text = "新" * THIN_MAX_CHARS
        assert classify_row(row(summary=text), set()) == "substantive"

    def test_synthetic_placeholder_summaries_are_thin(self):
        """collector 產生的佔位摘要（8–16 字）根本不是正文。"""
        assert classify_row(row(summary="PTT gossiping 推文數：42"), set()) == "thin"
        assert classify_row(row(summary="交通部 官方公告"), set()) == "thin"


class TestBoilerplateKeys:
    def _rows(self, domains):
        return [
            row(summary=BOILER_LEAD + f"。第{i}則報導內容",
                link=f"https://{d}/n/{i}")
            for i, d in enumerate(domains)
        ]

    def test_precondition_lead_is_long_enough_to_form_a_prefix(self):
        assert len(BOILER_LEAD) >= PREFIX_LEN

    def test_contract_minimum_is_three_distinct_articles(self):
        """判準明文是「>= 3 篇不同文章」，這條直接釘住字面值。

        其餘 boilerplate 測試都以 MIN_BOILERPLATE **參數化**，所以常數自己漂掉時
        它們全都看不見——實測把 3 改成 2，本檔 29 條測試全綠。參數化的測試守得住
        「行為與常數一致」，守不住「常數是對的」，兩者要分開守。
        """
        assert MIN_BOILERPLATE == 3

    def test_two_articles_do_not_form_a_template(self):
        """字面 2 篇：不可以開火。刻意不寫 MIN_BOILERPLATE - 1——那會跟著常數漂。"""
        assert boilerplate_keys(self._rows(["fcl.example.com"] * 2)) == set()

    def test_three_articles_form_a_template(self):
        """字面 3 篇：必須開火。"""
        assert boilerplate_keys(self._rows(["fcl.example.com"] * 3)) == {
            ("fcl.example.com", BOILER_LEAD[:PREFIX_LEN])
        }

    def test_does_not_fire_across_different_domains(self):
        """同一句話出現在三個不同網域是巧合，不是某一站的版型。"""
        keys = boilerplate_keys(self._rows(["a.example.com", "b.example.com", "c.example.com"]))
        assert keys == set()

    def test_counts_distinct_articles_not_repeated_rows(self):
        dup = row(summary=BOILER_LEAD + "。重複的同一列",
                  link="https://fcl.example.com/n/dup")
        assert boilerplate_keys([dup] * MIN_BOILERPLATE) == set()

    def test_is_derived_from_the_data_not_hardcoded(self):
        """換一個從沒見過的站台與前言，偵測器仍要抓到——不需要改程式。"""
        lead = "歡迎收看本台新聞我們提供二十四小時不間斷的即時報導與深度分析節目"
        rows = [
            row(summary=lead + f"。今日第{i}則", link=f"https://brand.new.site/{i}")
            for i in range(MIN_BOILERPLATE)
        ]
        assert boilerplate_keys(rows) == {("brand.new.site", lead[:PREFIX_LEN])}


class TestMeasure:
    def _population(self):
        rows = [
            row(summary=""),                                              # absent
            row(summary=TITLE + " - 中央社"),                             # title_echo
            row(summary=GN_BLOB, title=GN_TITLE, link=GN_LINK),           # title_echo + html + gn
            row(summary="PTT gossiping 推文數：42"),                      # thin
            row(summary="新" * THIN_MAX_CHARS, link="https://cna.example.com/x"),
        ]
        rows += [
            row(summary=BOILER_LEAD + f"。第{i}則報導內容",
                link=f"https://fcl.example.com/n/{i}", source="新聞雲報")
            for i in range(MIN_BOILERPLATE)
        ]
        return rows

    def test_denominator_includes_google_news_unresolved_rows(self):
        """直接斷言分母。這是防止本腳本悄悄複製 measure_body_fetch.py 那個
        「只算有真實網址者」的空洞分母的守門測試。"""
        rows = self._population()
        gn = [r for r in rows if is_gn_unresolved(r["link"])]
        assert gn, "fixture 必須含 GN 未還原的列，否則這個測試是空的"
        assert measure(rows)["total"] == len(rows)

    def test_every_class_is_populated_and_they_partition_the_population(self):
        rep = measure(self._population())
        assert set(rep["classes"]) == set(CLASSES)
        assert rep["classes"] == {
            "absent": 1,
            "title_echo": 2,
            "boilerplate": MIN_BOILERPLATE,
            "thin": 1,
            "substantive": 1,
        }
        assert sum(rep["classes"].values()) == rep["total"]

    def test_flags_are_counted_independently_of_the_class(self):
        """同一列可以既是 title_echo 又是 arrived_as_html，兩個計數器都要看到它。"""
        rep = measure(self._population())
        assert rep["classes"]["title_echo"] == 2
        assert rep["flags"]["arrived_as_html"] == 1
        assert rep["flags"]["gn_unresolved_link"] == 1

    def test_test_rows_do_not_move_the_numbers(self):
        clean = self._population()
        polluted = clean + [row(summary="新" * 200, week_id="2025-W01-test")] * 20
        assert measure(clean) == measure(polluted)

    def test_breakdowns_are_reported(self):
        rep = measure(self._population())
        assert rep["by_week"]["2026-W22"]["n"] == rep["total"]
        assert rep["by_week"]["2026-W22"]["non_substantive"] == rep["total"] - 1
        assert rep["by_source"]["新聞雲報"]["non_substantive"] == MIN_BOILERPLATE
        assert rep["boilerplate_prefixes"][0]["domain"] == "fcl.example.com"

    def test_by_category_keys_on_major_category_not_source(self):
        """by_category 必須以 major_category 分桶，不是 source。

        這一維是 BACKLOG #11 真正要問的東西（政策四類 vs 非政策的落差），而它加進來
        時沒有任何測試——實測把鍵換成 `r.get("source")`，208 條全綠。那是個很像
        複製貼上手滑的改動，因為它就緊貼在 by_source 那一行下面。

        所以 fixture 刻意讓兩列**同 source、不同 category**：鍵一換就會塌成一桶。
        """
        rows = [
            row(summary="新" * 200, source="中時新聞網", major_category="機車事故"),
            row(summary=TITLE + " - 中央社", source="中時新聞網", major_category="道安政策"),
        ]
        rep = measure(rows)

        assert set(rep["by_category"]) == {"機車事故", "道安政策"}
        assert rep["by_category"]["機車事故"]["non_substantive"] == 0
        assert rep["by_category"]["道安政策"]["non_substantive"] == 1
        # 判別式：同一個 source 的兩列若被誤用 source 當鍵，會塌成單一桶 n=2
        assert rep["by_source"]["中時新聞網"]["n"] == 2

    def test_empty_population(self):
        rep = measure([])
        assert rep["total"] == 0
        assert rep["classes"] == {c: 0 for c in CLASSES}
