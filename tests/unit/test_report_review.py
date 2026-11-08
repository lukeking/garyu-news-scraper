"""spec 018 T006：is_title_only() 與 check_report()（contracts/check-report.md）。
門檻用字面值（20 字、30%）；咬合對照跑 tests/fixtures/report_review/ 的已發布原稿。
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.report_review import SC001_CHECKS, check_report, is_title_only  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "report_review")
LINE_PREFIX = "0則貼文 | 快來參與LINE TODAY討論牆上的討論 |"
TTV_INTRO = "台視影音：提供台視最新的綜藝、專題、節目預告及新聞影音，並有數個完整影音節目，供網友選擇收看。"
FCL_PROMO = ("台灣新聞雲報提供台灣最中立最公正最即時的各類型新聞報導，包括政治新聞、焦點新聞、社會新聞、國際新聞、地方新聞、娛樂新聞、"
             "科技新聞、專訪新聞、政黨新聞、藝文活動、美食推廣、體育賽事等相關新聞報導。歡迎各界好友踴躍贊助推廣。")
GN_TITLE = "單車少年闖紅燈！害女騎士路口急剎摔車 - 自由時報"
GN_ANCHOR = (
    '<a href="https://news.google.com/rss/articles/CBMia0FVX3lxTE81N2xtR2pnS0lKb0xGSkZGUUVLSnctMkJkTTlpOUtXbkJicmlxV1I2cVNpbjFZ'
    'dGRPbU9zTy10am5GMTJLTnkyQVVobHhTbkt4TEtEbWxPMHEwblJBNmhZM1dZQVZ2cGpCTnZJ0gFwQVVfeXFMT2kxcEVMUHBrZEZWNjVGOEw4R2kzdzUtODV4'
    'enhURUNHZjBfOUFPdExqYzQ2TUViQi1ZOUtSaTEzX1NVaFpXeDNQQTR3MVptV3lOeFUyRnYzNUhTSXNNUlhwUHB6MlBkcDR2Yks2U2VOeg?oc=5" '
    'target="_blank">單車少年闖紅燈！害女騎士路口急剎摔車</a>&nbsp;&nbsp;<font color="#6f6f6f">自由時報</font>'
)
GN_TRUNCATED_TITLE = "機車兩段式左轉取消？交通部拍板「因地制宜」 改採這招保護騎士 - Yahoo新聞"
GN_TRUNCATED = (   # 07-20 [1]：存進庫時就截在 500 字，斷在 href 的網址中間，沒有「>」
    '<a href="https://news.google.com/rss/articles/CBMijwNBVV95cUxNQUxGaXAzVVZkc1VMRHIxSUlSWE84MUxvS19NM1Q2MTQwZXo5Mkpxdjk0al'
    'RNckxxLTZTZlJOSWdDQkUyX2V3dDNra1hpQnJLek12UFh4NUIzazRvTFJfMjg4VTc5akVnNEVDRjJhbzR4OGpIa3gwUUNnektKYzFCblBqNTYwN09oaHRINU'
    'oyeG5xeEZHZEw1dnNHcUk1M2NBUlZ6a1dsODEwbHpDakU2MTFEcldadjh0TXU0OERySGk0d3R0MGtYd0V5bkR3c1E5QVhSQVlkbU45LUZRc0Y2aVJYZ282ZU'
    'ZzZGpjVEJYem9LN2xENnpzbzFxYVlBTGI4Ujl6SHVaS2JKY2xmNWlPdkluNE0wc0Z1ZXZfNHlHeTNkUWhzQ0ZtSWZJc2NnQmVfd3dKVXdDUTY0LVB1SGJKcU'
    'FCVE85RmFvalM2UWdTRE'
)
TWENTY = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉"   # 20 個不是標點的字
DIGEST_KEYS = {
    "missing_section", "id_out_of_range", "title_only_in_sections", "self_count",
    "independence_claim", "date_unlabeled", "replacement_new_number", "deletion_over_cap",
}
HOT_KEYS = {
    "missing_section", "id_out_of_range", "interweave_sum", "replacement_new_number", "deletion_over_cap",
}
SOURCES = [
    {"title": "台中市科技執法上路", "summary": "台中市自下月起在三處路口啟用科技執法設備，取締闖紅燈。", "published": "2026-10-01"},
    {"title": "新北道安會報", "summary": "新北道安會報", "published": "2026-10-02"},
    {"title": "交通部公布道安統計", "summary": "交通部公布前七月統計，死亡 1,569 人，年減 1.1%。", "published": "2026-10-03"},
]


def _load(name):
    with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def _digest(overview="本期收錄 3 篇報導，其中 1 篇只有標題。", sections="- 台中市啟用科技執法 [1]。",
            tracking="- 台中市後續 [1]。", title_only="- 新北道安會報 [2]"):
    lines = ["### 本期概覽", overview, "", "### 分節彙整", "#### 中央與地方", sections, "", "### 待追蹤", tracking]
    if title_only is not None:
        lines += ["", "### 僅標題", title_only]
    return "\n".join(lines)


def _hot(dist="交織度分布：[工程主導] 1 篇 ／ [雙因交織] 1 篇 ／ [人因主導] 1 篇"):
    lines = ["### 一、 事故因果解構"]
    if dist is not None:
        lines.append(dist)
    lines += ["代表個案：[1]", "人因變數：未禮讓 [直接證據]", "", "### 二、 政經變數審查", "審查結果：不適用",
              "", "### 三、 官方論述偏誤", "審查結果：[推斷，非直接證據] 引述 [3]"]
    return "\n".join(lines)


def _digest_check(text, **kw):
    kw.setdefault("title_only_ids", (2,))
    return check_report(text, template="digest", sources=SOURCES, **kw)


# ── is_title_only ─────────────────────────────────────────────────────────────

def test_title_only_empty_summary():
    """摘要空白（含只有空白與標點）＝只有標題。"""
    assert is_title_only("台中市科技執法上路", "") is True
    assert is_title_only("台中市科技執法上路", "  \n ， ") is True


def test_title_only_summary_equals_title_after_normalising():
    """正規化（NFKC、小寫、去標點與空白）後與標題相同。"""
    assert is_title_only("台中 科技執法！ＡＢＣ", "台中科技執法abc") is True
    assert is_title_only("屏東道安會報聚焦無照 - CNMA新聞聯合網", "屏東道安會報聚焦無照 CNMA新聞聯合網") is True


def test_title_only_summary_contained_in_title():
    """摘要只是標題的一段。"""
    assert is_title_only("新北市道安會報 侯友宜指示八方見警", "侯友宜指示八方見警") is True


def test_title_only_remainder_threshold_is_twenty_chars():
    """扣掉標題剩 19 字＝只有標題；剩 20 字＝有摘要（T001 定案的 20）。"""
    assert is_title_only("台中市科技執法上路", "台中市科技執法上路" + TWENTY[:19]) is True
    assert is_title_only("台中市科技執法上路", "台中市科技執法上路" + TWENTY) is False


def test_title_only_remainder_ignores_punctuation_and_spaces():
    """剩下的字數不算標點與空白：19 個字夾著標點仍是只有標題。"""
    padded = "，".join(TWENTY[:19]) + "  。"
    assert is_title_only("台中市科技執法上路", "台中市科技執法上路" + padded) is True


def test_title_only_strips_google_news_media_suffix():
    """標題去掉最後一段「 - 媒體名」也比一次：摘要＝標題本體＋19 字仍是只有標題。"""
    title = "台中市科技執法上路 - 自由時報"
    assert is_title_only(title, "台中市科技執法上路" + TWENTY[:19]) is True
    assert is_title_only(title, "台中市科技執法上路" + TWENTY) is False


def test_title_only_line_today_wall_prefix():
    """LINE TODAY 討論牆前綴加標題（research R4 的 09-14 [2] 那型）。"""
    title = "騎士闖紅燈遭撞 送醫不治"
    assert is_title_only(title, LINE_PREFIX + " " + title) is True


def test_title_only_ttv_video_intro():
    """台視影音簡介整段（08-10 [7] 那型），單獨出現或接在標題後面都算。"""
    title = "國道追撞 三車受損"
    assert is_title_only(title, TTV_INTRO) is True
    assert is_title_only(title, title + " " + TTV_INTRO) is True


def test_title_only_real_short_summary_is_not_title_only():
    """41 字的真摘要（09-28 [11] 那型）不是只有標題。"""
    summary = "有民眾在公共政策網路參與平臺提案，要求機車駕照考試加考道路駕駛，附議人數已超過五千人，交通部須在兩個月內回應。"
    assert is_title_only("機車考照加考道路駕駛提案", summary) is False


def test_title_only_google_news_html_anchor():
    """Google News RSS 的 HTML 錨點摘要（06-22 [1]，research R4「11-08 補」）：去掉標籤後是標題＋媒體名。"""
    assert is_title_only(GN_TITLE, GN_ANCHOR) is True


def test_title_only_fclnews_promo():
    """fclnews 推廣文字整段、前面加一個「-」（08-24 [2] 那型）。"""
    title = "港灣新聞網／迴轉瞬間撞上機車！高雄七賢、自立路口車禍 女騎士送醫肇因待釐清 - 台灣新聞雲報"
    assert is_title_only(title, "-" + FCL_PROMO) is True
    assert is_title_only(title, title + " -" + FCL_PROMO) is True


def test_title_only_tags_do_not_count_as_text():
    """標籤不算字：<p> 包著 19 字仍是只有標題，包著 20 字是有摘要。"""
    title = "台中市科技執法上路"
    assert is_title_only(title, f"<p>{title}</p><p>{TWENTY[:19]}</p>") is True
    assert is_title_only(title, f"<p>{title}</p><p>{TWENTY}</p>") is False


def test_title_only_entities_are_unescaped():
    """實體還原後才算字：五個 &nbsp; 不是 20 字的內容。"""
    assert is_title_only("台中市科技執法上路", "台中市科技執法上路" + "&nbsp;" * 5) is True


def test_title_only_strips_tags_before_unescaping():
    """先去標籤再還原實體（契約第 0 步）：&lt;b&gt; 還原成的 <b> 是內文，算 3 字。"""
    assert is_title_only("台中市科技執法上路", "台中市科技執法上路" + TWENTY[:17] + "&lt;b&gt;") is False


def test_title_only_paragraph_with_real_lead_is_not_title_only():
    """<p> 包著真導言，去掉標籤後扣掉標題仍至少 20 字，判成有摘要。"""
    title = "台中市科技執法上路"
    summary = f"<p><b>{title}</b></p><p>台中市自下月起在三處路口啟用科技執法設備，取締闖紅燈與未禮讓行人。</p>"
    assert is_title_only(title, summary) is False


def test_title_only_google_news_truncated_anchor():
    """存進庫時截在 href 中間、沒有閉合的錨點（07-20 [1]）：結尾沒閉合的標籤片段也去掉。"""
    assert is_title_only(GN_TRUNCATED_TITLE, GN_TRUNCATED) is True


def test_title_only_keeps_trailing_angle_bracket_before_digit():
    """結尾的「<」後面接數字是內文：<0.15 算 4 字，剩 20 字是有摘要。"""
    title = "酒駕罰則分級"
    assert is_title_only(title, title + "，騎士與駕駛的罰則分級標準為酒測值<0.15") is False


def test_title_only_closed_tag_then_text_to_end():
    """閉合的標籤後面接著內文到結尾：只去掉標籤，不把後面的字當成沒閉合的片段。"""
    title = "台中市科技執法上路"
    assert is_title_only(title, title + "<br>" + TWENTY) is False


def test_title_only_keeps_bare_angle_brackets_in_text():
    """「<」「>」後面不是標籤名的是內文，不當標籤去掉（免得去過頭）。"""
    title = "酒駕罰則分級"
    summary = title + "，酒測值<0.15毫克的騎士與酒測值>0.25毫克的駕駛罰則不同"
    assert is_title_only(title, summary) is False


def test_title_only_unclosed_lt_does_not_swallow_later_tag():
    """內文的「A<B」沒閉合，不跨過後面的 <br> 一起去掉：只去 <br>，內文還在（review e66db8b-1）。"""
    title = "台中市科技執法上路"
    assert is_title_only(title, title + "，比較A<B兩處路口" + TWENTY + "<br>") is False


@pytest.mark.parametrize("name", ["digest_2026-10-19", "digest_2026-10-26", "digest_2026-11-02"])
def test_title_only_matches_t001_on_fixtures(name):
    """三份彙整判出的 ID 與 T001 記下的 t001_title_only_ids 完全相同。"""
    d = _load(name)
    ids = [i for i, s in enumerate(d["sources"], 1) if is_title_only(s["title"], s["summary"])]
    assert ids == d["t001_title_only_ids"]


# ── check_report：介面 ────────────────────────────────────────────────────────

def test_check_report_digest_keys_and_clean_report_passes():
    """彙整回傳八個檢查名，乾淨的報告全部是空清單。"""
    r = _digest_check(_digest())
    assert set(r) == DIGEST_KEYS
    assert all(v == [] for v in r.values()), r


def test_check_report_hot_keys_and_clean_report_passes():
    """三軸回傳五個檢查名（沒有彙整專屬的四項），乾淨的報告全部是空清單。"""
    r = check_report(_hot(), template="hot", sources=SOURCES)
    assert set(r) == HOT_KEYS
    assert all(v == [] for v in r.values()), r


def test_check_report_rejects_unknown_template():
    with pytest.raises(ValueError):
        check_report(_digest(), template="weekly", sources=SOURCES)


def test_check_report_replacements_require_original_text():
    with pytest.raises(ValueError):
        _digest_check(_digest(), replacements=[("[1]", "")])


def test_sc001_checks_are_the_four_types():
    assert SC001_CHECKS == ("independence_claim", "date_unlabeled", "self_count", "title_only_in_sections")


# ── missing_section ───────────────────────────────────────────────────────────

def test_missing_section_digest():
    """缺「### 待追蹤」就命中那個標題。"""
    text = _digest().replace("### 待追蹤", "待追蹤")
    assert _digest_check(text)["missing_section"] == ["### 待追蹤"]


def test_missing_section_title_only_heading_only_when_ids_given():
    """沒有只有標題的報導時不要求「### 僅標題」；有的時候缺了就命中。"""
    text = _digest(title_only=None)
    assert _digest_check(text, title_only_ids=())["missing_section"] == []
    assert _digest_check(text, title_only_ids=(2,))["missing_section"] == ["### 僅標題"]


def test_missing_section_hot_requires_line_start():
    """三軸看行首的「### 二、」，夾在行中不算。"""
    text = _hot().replace("### 二、 政經變數審查", "見上方 ### 二、 政經變數審查")
    assert check_report(text, template="hot", sources=SOURCES)["missing_section"] == ["### 二、"]


# ── id_out_of_range ───────────────────────────────────────────────────────────

def test_id_out_of_range_single_multi_and_non_numeric():
    """[4]、[0] 與多個編號裡的 5 超出 1..3；非數字括號不算。"""
    sections = "- 甲 [1]。乙 [4]。丙 [0]。丁 [2, 5]。戊 [1、3]。己 [推斷，非直接證據] [工程主導]。"
    assert _digest_check(_digest(sections=sections))["id_out_of_range"] == ["[4]", "[0]", "[5]"]


def test_id_out_of_range_upper_bound_is_len_sources():
    """[3] 是清單最後一篇（在範圍內），[4] 剛好超出。"""
    assert _digest_check(_digest(sections="- 甲 [3]。"))["id_out_of_range"] == []
    assert _digest_check(_digest(sections="- 甲 [4]。"))["id_out_of_range"] == ["[4]"]


def test_id_out_of_range_digit_bearing_non_id_brackets():
    """括號裡有數字但不全是編號（[1-3]、[2026年報告 5]）不算編號。"""
    sections = "- 甲 [1]。乙 [1-3]。丙 [2026年報告 5]。"
    assert _digest_check(_digest(sections=sections))["id_out_of_range"] == []


def test_id_out_of_range_hot_fixture_ignores_evidence_tags():
    """09-07 三軸的 [直接證據]、[工程主導] 不是編號，[6]、[8] 在 8 篇以內。"""
    d = _load("hot_2026-09-07")
    r = check_report(d["report_text"], template="hot", sources=d["sources"])
    assert r["id_out_of_range"] == []


# ── title_only_in_sections ────────────────────────────────────────────────────

def test_title_only_in_sections_hits_section_and_subsection():
    """只有標題的 [2] 出現在分節彙整（含 #### 子節、多編號括號）就命中。"""
    assert _digest_check(_digest(sections="- 新北 [1, 2]。"))["title_only_in_sections"] == ["[2]"]


def test_title_only_in_sections_ignores_other_sections():
    """[2] 只出現在概覽、待追蹤、僅標題，不算。"""
    text = _digest(overview="概覽提到 [2]。", tracking="- 新北後續 [2]。")
    assert _digest_check(text)["title_only_in_sections"] == []


# ── self_count ────────────────────────────────────────────────────────────────

def test_self_count_hits_model_counts_in_overview():
    assert _digest_check(_digest(overview="本期共收錄 19 起獨立事件，涵蓋三面向。"))["self_count"] == [
        "本期共收錄 19 起獨立事件"]
    assert _digest_check(_digest(overview="本期共彙整 24 個獨立事件（排除 1 篇）。"))["self_count"] == [
        "本期共彙整 24 個獨立事件"]


def test_self_count_ignores_program_line_and_other_sections():
    """程式寫的「本期收錄 N 篇報導」不算；分節彙整裡的「共 N 起事件」也不算。"""
    assert _digest_check(_digest(overview="本期收錄 25 篇報導，其中 3 篇只有標題。"))["self_count"] == []
    assert _digest_check(_digest(overview="本期收錄 25 篇報導。"))["self_count"] == []
    assert _digest_check(_digest(sections="- 本期共收錄 3 起獨立事件 [1]。"))["self_count"] == []


def test_self_count_needs_gong_and_counts_events_not_articles():
    """沒有「共」的範圍描述、以「篇」計的報導數，都不是模型自數的事件數。"""
    assert _digest_check(_digest(overview="本期收錄 25 篇報導，涵蓋 2 個縣市的道安事件。"))["self_count"] == []
    assert _digest_check(_digest(overview="本期共收錄 25 篇道安事件報導。"))["self_count"] == []


# ── independence_claim ────────────────────────────────────────────────────────

@pytest.mark.parametrize("word", ["互相獨立", "無直接因果", "各自獨立"])
def test_independence_claim_words(word):
    assert _digest_check(_digest(sections=f"- 甲與乙{word} [1]。"))["independence_claim"] == [word]


# ── date_unlabeled ────────────────────────────────────────────────────────────

def test_date_unlabeled_hits_date_without_label_or_source():
    """2026 年 10 月 9 日既沒標報導、來源也沒有 → 命中原文。"""
    text = _digest(sections="- 立委於 2026 年 10 月 9 日質詢 [1]。")
    assert _digest_check(text)["date_unlabeled"] == ["2026 年 10 月 9 日"]


def test_date_unlabeled_formats_with_and_without_spaces():
    text = _digest(sections="- 甲於 2026年10月2日預告 [1]。乙於 10 月 6 日起執法 [1]。丙定 116 年 1 月 8 日開罰 [1]。")
    assert _digest_check(text)["date_unlabeled"] == ["2026年10月2日", "10 月 6 日", "116 年 1 月 8 日"]


def test_date_unlabeled_report_label_within_ten_chars():
    """「報導」整個落在日期後 10 字內就通過；往後挪一字就命中。"""
    ok = _digest(sections="- 甲於 10 月 9 日" + "一二三四五六七八" + "報導 [1]。")
    late = _digest(sections="- 甲於 10 月 9 日" + "一二三四五六七八九" + "報導 [1]。")
    assert _digest_check(ok)["date_unlabeled"] == []
    assert _digest_check(late)["date_unlabeled"] == ["10 月 9 日"]


def test_date_unlabeled_passes_when_source_has_the_date():
    """來源的標題或摘要（去掉空白）含 M月D日 或 M/D 就通過。"""
    text = _digest(sections="- 甲於 2026 年 10 月 9 日質詢 [1]。")
    by_title = [dict(SOURCES[0], title="立委 10 月 9 日質詢")] + SOURCES[1:]
    by_slash = [dict(SOURCES[0], summary="立委（10/9）質詢院長")] + SOURCES[1:]
    for sources in (by_title, by_slash):
        r = check_report(text, template="digest", sources=sources, title_only_ids=(2,))
        assert r["date_unlabeled"] == []


@pytest.mark.parametrize("source_text", ["自 11/8 起開罰", "自 11 月 8 日起開罰"])
def test_date_unlabeled_source_date_needs_digit_boundary(source_text):
    """來源的 11/8、11月8日 不能替 1 月 8 日作證。"""
    text = _digest(sections="- 甲於 1 月 8 日開罰 [1]。")
    sources = [dict(SOURCES[0], summary=source_text)] + SOURCES[1:]
    r = check_report(text, template="digest", sources=sources, title_only_ids=(2,))
    assert r["date_unlabeled"] == ["1 月 8 日"]


# ── interweave_sum ────────────────────────────────────────────────────────────

def test_interweave_sum_mismatch():
    r = check_report(_hot("交織度分布：[工程主導] 0 篇 ／ [雙因交織] 1 篇 ／ [人因主導] 1 篇"),
                     template="hot", sources=SOURCES)
    assert r["interweave_sum"] == ["0+1+1=2≠3"]


def test_interweave_sum_counts_all_five_classes():
    """FR-005b 的五類（含 [工程資料未載]、[非事故]）整行加總：等於篇數不命中，不等就命中。"""
    head = "交織度分布：[工程主導] 0 篇 ／ [雙因交織] 0 篇 ／ [人因主導] 1 篇 ／ [工程資料未載] 1 篇 ／ [非事故] "
    assert check_report(_hot(head + "1 篇"), template="hot", sources=SOURCES)["interweave_sum"] == []
    r = check_report(_hot(head + "2 篇"), template="hot", sources=SOURCES)
    assert r["interweave_sum"] == ["0+0+1+1+2=4≠3"]


def test_interweave_sum_counts_all_six_classes():
    """FR-005c 的六類（加 [工程未見放大]）整行加總：等於篇數不命中，不等就命中。"""
    head = "交織度分布：[工程主導] 0 篇 ／ [雙因交織] 0 篇 ／ [人因主導] 1 篇 ／ [工程未見放大] 1 篇 ／ [工程資料未載] 0 篇 ／ [非事故] "
    assert check_report(_hot(head + "1 篇"), template="hot", sources=SOURCES)["interweave_sum"] == []
    r = check_report(_hot(head + "2 篇"), template="hot", sources=SOURCES)
    assert r["interweave_sum"] == ["0+0+1+1+0+2=4≠3"]


def test_interweave_sum_skipped_when_axis_a_not_applicable():
    """A 軸寫「不適用」時沒有交織度分布那一行，不檢查（FR-005a）。"""
    r = check_report(_hot(dist=None), template="hot", sources=SOURCES)
    assert r["interweave_sum"] == []


def test_interweave_sum_line_without_counts_is_not_checked():
    """「交織度分布：不適用」這種沒有「N 篇」的行，當成沒有這一行。"""
    r = check_report(_hot("交織度分布：不適用"), template="hot", sources=SOURCES)
    assert r["interweave_sum"] == []


# ── replacement_new_number ────────────────────────────────────────────────────

def _with_replacement(quote, replacement):
    original = _digest(sections=f"- {quote} [1]。")
    revised = original.replace(quote, replacement)
    return _digest_check(revised, original_text=original, replacements=[(quote, replacement)])


def test_replacement_new_number_hits_number_absent_from_quote_and_sources():
    """1,777 與 10.7 在原句與清單都沒有。"""
    r = _with_replacement("死亡人數下降", "死亡 1,777 人，減少 10.7%")
    assert r["replacement_new_number"] == ["1,777", "10.7"]


def test_replacement_new_number_passes_when_number_in_quote_or_sources():
    """3 在原句；1,569 與 1.1 在清單摘要；1569 不寫千分位也算同一個數。"""
    assert _with_replacement("三處路口共 3 處", "3 處路口")["replacement_new_number"] == []
    assert _with_replacement("死亡人數下降", "死亡 1,569 人，年減 1.1%")["replacement_new_number"] == []
    assert _with_replacement("死亡人數下降", "死亡 1569 人")["replacement_new_number"] == []


def test_replacement_new_number_compares_whole_numbers():
    """清單有 1,569，替換寫 156 仍是新數字（不是子字串比對）。"""
    assert _with_replacement("死亡人數下降", "死亡 156 人")["replacement_new_number"] == ["156"]


# ── deletion_over_cap ─────────────────────────────────────────────────────────

def _deletion(deleted, added_elsewhere=0):
    original = "一" * 100
    reps = [("一" * deleted, "")]
    if added_elsewhere:
        reps.append(("二", "二" * (1 + added_elsewhere)))
    return check_report(original, template="hot", sources=SOURCES, original_text=original,
                        replacements=reps)["deletion_over_cap"]


def test_deletion_cap_29_and_30_percent_pass_31_fails():
    assert _deletion(29) == []
    assert _deletion(30) == []
    assert _deletion(31) == ["31.0%"]


def test_deletion_cap_does_not_net_out_lengthened_replacements():
    """加長的替換不抵銷刪掉的字：刪 31 字、另一條加 10 字仍是 31%。"""
    assert _deletion(31, added_elsewhere=10) == ["31.0%"]


# ── 只算修稿新增的失敗 ───────────────────────────────────────────────────────

def test_only_new_failures_count_against_revision():
    """原稿就有的「互相獨立」與缺節不算；修稿新加的「各自獨立」才算。"""
    original = _digest(sections="- 甲與乙互相獨立 [1]。").replace("### 待追蹤", "待追蹤")
    same = _digest_check(original, original_text=original)
    assert same["independence_claim"] == [] and same["missing_section"] == []
    revised = original.replace("互相獨立", "互相獨立，丙各自獨立")
    assert _digest_check(revised, original_text=original)["independence_claim"] == ["各自獨立"]


# ── 咬合對照：已發布原稿 ──────────────────────────────────────────────────────

def _fixture_check(name):
    d = _load(name)
    return check_report(d["report_text"], template="digest", sources=d["sources"],
                        title_only_ids=d["t001_title_only_ids"])


@pytest.mark.parametrize("name,claim,count,self_count", [
    ("digest_2026-10-19", ["無直接因果"], 11, []),
    ("digest_2026-10-26", ["各自獨立"], 6, ["本期共彙整 24 個獨立事件"]),
    ("digest_2026-11-02", ["無直接因果"], 7, ["本期共收錄 19 起獨立事件"]),
])
def test_bite_published_digests(name, claim, count, self_count):
    """已發布的三份彙整：互相獨立類 > 0、事件數（10-26、11-02）> 0、只有標題進分節 11／6／7。"""
    r = _fixture_check(name)
    assert r["independence_claim"] == claim
    assert r["self_count"] == self_count
    assert len(r["title_only_in_sections"]) == count


def test_bite_published_digest_unlabeled_question_date():
    """s3h 錨點：10-19 把報導日寫成質詢日的「2026 年 10 月 9 日」。"""
    assert "2026 年 10 月 9 日" in _fixture_check("digest_2026-10-19")["date_unlabeled"]


def test_bite_published_hot_interweave_sum():
    d = _load("hot_2026-09-07")
    r = check_report(d["report_text"], template="hot", sources=d["sources"])
    assert r["interweave_sum"] == ["0+4+3=7≠8"]
