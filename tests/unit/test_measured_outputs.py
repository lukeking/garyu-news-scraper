"""spec 018 Unit 21：已量過的重生成輸出（fixture 的 sc001_／sc007_／sc008_，出處見 SOURCES.md）在現行 check_report() 下的判定。
期望值照 evaluation.md 的表抄成字面值，不從 fixture 算。
"""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.report_review import check_report  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "report_review")
NOT_APPLICABLE = "本批無事故報導，不適用"
SIX = ("工程主導", "雙因交織", "人因主導", "工程未見放大", "工程資料未載", "非事故")
_PAIR = re.compile(r"\[([^\[\]]+)\]\s*(\d+)\s*篇")

SC001_DIGESTS = ["sc001_digest_2026-10-19", "sc001_digest_2026-10-26", "sc001_digest_2026-11-02"]
SC001_HOT = ["sc001_hot_2026-10-19", "sc001_hot_2026-09-14"]
ZERO_CHECKS = ("independence_claim", "self_count", "title_only_in_sections", "missing_section")
# evaluation.md GNS-011 節「FR-005c 之後」的表，順序同 SIX；07-20 是「本批無事故報導，不適用」，另一條測
SC007 = {
    "2026-06-22": (0, 0, 0, 0, 3, 0),
    "2026-08-03": (0, 0, 0, 0, 3, 7),
    "2026-08-24": (0, 0, 0, 1, 3, 0),
    "2026-09-21": (0, 0, 0, 0, 1, 4),
    "2026-09-28": (0, 0, 0, 2, 2, 0),
    "2026-10-26": (0, 0, 0, 1, 5, 0),
}
# evaluation.md「GNS-20261108-5xf」節「FR-005c 之後」的表：每組 run1 的 [1][2]、[3][4] 歸類換成各類篇數，順序同 SIX
SC008 = {
    "body-only": (0, 2, 0, 0, 2, 0),
    "placebo": (0, 1, 0, 1, 2, 0),
    "unrelated": (0, 1, 0, 1, 2, 0),
    "real": (0, 2, 0, 0, 2, 0),
    "counterfactual": (0, 0, 0, 2, 2, 0),
    "positive": (0, 0, 2, 0, 2, 0),
}


def _load(name):
    with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def _check(d, text=None, sources=None):
    return check_report(d["report_text"] if text is None else text, template=d["template"],
                        sources=d["sources"] if sources is None else sources, title_only_ids=d["title_only_ids"])


def _axis_a(text):
    """「### 一、」那一行之後，到下一個「### 」開頭的行為止。"""
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("### "):
            inside = line.startswith("### 一、")
        elif inside:
            out.append(line)
    return "\n".join(out).strip()


def _distribution(text):
    """A 軸「交織度分布：」那一行的（類別, 篇數）；沒有這一行回 None。"""
    lines = [line for line in _axis_a(text).splitlines() if line.startswith("交織度分布：")]
    if not lines:
        return None
    assert len(lines) == 1, lines
    pairs = _PAIR.findall(lines[0])
    return tuple(label for label, _ in pairs), tuple(int(n) for _, n in pairs)


def _replace_once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)


def _assert_distribution(d, expected):
    """六類照順序、篇數等於表；check_report 讀到同一組數字：對這份清單不命中，對少一篇的清單命中。"""
    assert _distribution(d["report_text"]) == (SIX, expected)
    n = len(d["sources"])
    assert _check(d)["interweave_sum"] == []
    short = _check(d, sources=d["sources"][:-1])
    assert short["interweave_sum"] == ["+".join(map(str, expected)) + f"={sum(expected)}≠{n - 1}"]


# ── SC-001（T048）─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", SC001_DIGESTS)
def test_sc001_digest_regenerations_have_zero_hits_except_dates(name):
    """三份彙整：前三類與 missing_section 0 命中；date_unlabeled 由 main 逐條判（evaluation.md），不斷言。"""
    r = _check(_load(name))
    assert {k: r[k] for k in ZERO_CHECKS} == {k: [] for k in ZERO_CHECKS}


def _inject(d, check):
    """往這份輸出放一處該檢查會抓的錯型，回傳（新全文, 期望命中）。"""
    text = d["report_text"]
    if check == "independence_claim":
        return _replace_once(text, "\n### 待追蹤", "\n- 兩案互相獨立 [1]。\n\n### 待追蹤"), ["互相獨立"]
    if check == "self_count":
        return _replace_once(text, "### 本期概覽\n", "### 本期概覽\n本期共收錄 19 起獨立事件。\n"), ["本期共收錄 19 起獨立事件"]
    if check == "title_only_in_sections":
        i = d["title_only_ids"][0]
        return _replace_once(text, "### 分節彙整\n", f"### 分節彙整\n- 只有標題的那篇 [{i}]。\n"), [f"[{i}]"]
    assert check == "missing_section", check
    return _replace_once(text, "### 待追蹤", "待追蹤"), ["### 待追蹤"]


@pytest.mark.parametrize("check", ZERO_CHECKS)
@pytest.mark.parametrize("name", SC001_DIGESTS)
def test_sc001_digest_checks_bite_on_the_same_outputs(name, check):
    """對照：同一份輸出放進一處錯型，那一項就命中，上面的 0 命中不是讀不到這種寫法。"""
    d = _load(name)
    text, expected = _inject(d, check)
    assert _check(d, text=text)[check] == expected


@pytest.mark.parametrize("name", SC001_HOT)
def test_sc001_hot_regenerations_without_accidents_write_axis_a_not_applicable(name):
    """10-19「科技執法 · 新聞」、09-14「道安政策 · 交通安全」：A 軸整節只有那一句，沒有交織度分布。"""
    d = _load(name)
    assert _axis_a(d["report_text"]) == NOT_APPLICABLE
    assert _check(d)["missing_section"] == []


# ── SC-007（T049）─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("week", list(SC007))
def test_sc007_regenerations_have_six_classes_matching_evaluation(week):
    """FR-005c 的 7 份（這裡 6 份有分布）：六類、各類篇數（含非事故）與表相同，interweave_sum 不命中。"""
    _assert_distribution(_load(f"sc007_hot_{week}"), SC007[week])


def test_sc007_0720_policy_batch_writes_axis_a_not_applicable():
    """07-20「路權政策 · 機車」：A 軸只有「本批無事故報導，不適用」，interweave_sum 不檢查也不命中。"""
    d = _load("sc007_hot_2026-07-20")
    assert _axis_a(d["report_text"]) == NOT_APPLICABLE
    assert _check(d)["interweave_sum"] == []


# ── SC-008（T050）─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("group", list(SC008))
def test_sc008_run1_distribution_sums_to_four_and_matches_evaluation(group):
    """09-28「機車事故 · UDN」六組各 run1：六類加總等於 4 篇，各類篇數與表相同。"""
    d = _load(f"sc008_{group}_run1")
    assert sum(SC008[group]) == len(d["sources"]) == 4
    _assert_distribution(d, SC008[group])
