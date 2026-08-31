"""
機車事故 require_any token 表的回歸測試（BACKLOG #10，2026-08-31）。

與 `test_relevance_gate.py` 的分工：那支測**機制**（規則以參數傳入，不載入 YAML）；
本支測**資料**——實際出貨的那張 token 表抓不抓得到真事故。兩者都需要，因為 012 的
教訓正是「機制對了但表不好」：閘的單元測試全綠，而 prod 排除率 63.6%、裡面有真事故。

**為什麼讀 `.example.yml` 而不是 `categories_traffic.yml`**：後者 gitignored（真身是
GH environment variable `CATEGORIES_TRAFFIC_YML`），CI 上不存在。example 那份是唯一
會進 git 的副本，本測試讓它從裝飾變成承重。
⚠️ 已知缺口：這裡驗的是 example 的表，**沒有任何東西驗 example 與 prod 逐字相同**。

案例全部來自 2026-08-10 週報 log 的 `[off-topic]` 逐筆紀錄（E1 實測，run 31345438480），
不是手寫的假標題——所以「它咬得到」講的是真流量，不是我造的餌。
"""
import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.filter import is_topic_relevant

_EXAMPLE_CONFIG = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "categories_traffic.example.yml"
)


def _moto_rule() -> dict:
    with open(_EXAMPLE_CONFIG, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    return cfg["relevance_rules"]["機車事故"]


# ── 2026-08-10 prod 誤殺的真事故：補完近失詞後必須進得來 ────────────────────
# 每筆標註靠哪個新增 token 救回，好讓日後移除某個 token 時看得出代價。
MIS_KILLED_0810 = [
    ("土城 騎士遭輾 柑城橋接中山路拖8年 - 中時新聞網", "輾"),
    ("新北土城奪命車禍曝交通瓶頸 柑城橋卡關8年拚開放機車 - 中時新聞網", "奪命"),
    ("重機情侶魂斷砂石車　這貼文惹怒機車路權會：這態度叫恐嚇 - 三立新聞", "魂斷"),
    ("台13線驚悚意外！ 22歲重機騎士墜20米橋下失去生命跡象- 社會 - 中時新聞網", "生命跡象"),
    ("台南永康驚悚車禍！女騎士捲入貨車底救出已無心跳- 社會 - 中時新聞網", "無心跳"),
    ("新竹人嚇壞！光復路成滑水道騎士「連人帶車」沖走學生涉水畫面曝光- 社會 - 中時新聞網", "沖走"),
    ("台中車禍機車騎士困車底一度命危 搶救恢復心跳 - 放言Fount Media", "命危"),
    ("苗栗市1男1女涉違規穿越 機車遭擊落釀3傷 - 聯合影音", "擊落"),
]


def test_mis_killed_real_accidents_now_on_topic():
    """08-10 誤殺的 8 篇真事故全部進得來（逐筆報出是哪一篇失守，不要只說「有一筆」）。"""
    rule = _moto_rule()
    failed = [
        (title, token)
        for title, token in MIS_KILLED_0810
        if not is_topic_relevant({"title": title}, rule)
    ]
    assert not failed, "以下真事故仍被排除：" + "; ".join(
        f"{token} → {title[:40]}" for title, token in failed
    )


def test_each_new_token_is_load_bearing():
    """每個新增 token 都至少獨力救回一篇——移除它就會有案例失守，證明沒有冗餘。

    這條擋的是「順手多加幾個看起來合理的詞」：012 的 追撞/自撞/擦撞 就是那樣進來的，
    後來被證明是 撞 的子字串、純冗餘。
    """
    rule = _moto_rule()
    require = list(rule.get("require_any") or [])
    for title, token in MIS_KILLED_0810:
        assert token in require, f"{token} 不在 require_any 裡"
        without = {**rule, "require_any": [t for t in require if t != token]}
        assert not is_topic_relevant({"title": title}, without), (
            f"移除 {token} 後「{title[:40]}」仍然過關 → 它是冗餘的，不該加"
        )


# ── T012 的決策護欄：這些必須維持 off-topic ────────────────────────────────

def test_car_accident_token_stays_removed():
    """`車禍` 是 T012 刻意移除的，這兩筆是它獨力製造的 false positive。

    它們現在 off-topic 的唯一理由就是表裡沒有 `車禍`。任何人把 `車禍` 加回去，
    這條會紅——那正是我們要的：讓那個決策在被推翻的**那一刻**發出聲音，
    而不是等它悄悄回到已發布的報告裡。
    """
    rule = _moto_rule()
    assert "車禍" not in (rule.get("require_any") or [])
    assert is_topic_relevant({"title": "車禍線上律師 - 頻道"}, rule) is False
    assert is_topic_relevant({"title": "機車險釀車禍幸好及時煞住"}, rule) is False


def test_generic_near_miss_token_deliberately_declined():
    """`翻過` 刻意不收，這篇因此仍然 off-topic——**這是已知的漏抓，不是 bug**。

    兩個理由：(a) `翻過` 通用義太強（翻過去／翻過一頁），FP 面遠大於它救回的一篇；
    (b) 這篇本身是「神反應翻過引擎蓋落地」，無人傷亡，是近失而非事故。
    日後若要收它，先想清楚 (a)——這條紅了就是在提醒那件事。
    """
    rule = _moto_rule()
    assert "翻過" not in (rule.get("require_any") or [])
    assert is_topic_relevant(
        {"title": "轎車雙黃線突迴轉！21歲重機騎士神反應「翻過引擎蓋」落地畫面曝 - 中時新聞網"},
        rule,
    ) is False
