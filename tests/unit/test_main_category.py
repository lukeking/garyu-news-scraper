"""類別選擇（specs/BACKLOG.md GNS-20261013-4g9「類別選擇的契約」）：GARYU_CATEGORY 讓 main() 只跑一類。
跑真的 main()，邊界沿用 test_main_dry_run 的 h；[類別] 那一行、不發布的固定行與篇數用字面值寫。"""
import shutil

import pytest

from tests.unit import test_main_dry_run as dry
from tests.unit.test_main_dry_run import BANNER, START, STOP_FFXIV, _end, h, main_mod  # noqa: F401（h 是 fixture）

LINE = {"traffic": "[類別] 只跑 traffic；略過 ffxiv（GARYU_CATEGORY）",
        "ffxiv": "[類別] 只跑 ffxiv；略過 traffic（GARYU_CATEGORY）"}
OTHER = {"traffic": "ffxiv", "ffxiv": "traffic"}
COLLECTED = {"traffic": ["甲台", "乙台"], "ffxiv": ["FFXIV JP Forum - DPS"]}
MODES = [None, "dry-input", "dry-full"]
STOPPED = "第一級已在分析之前停下，其餘 category 沒有文章，結束執行"


def _begin(name):
    return f"--- [{name}] 開始處理 ---"


def _done(n):
    return f"========== 執行完成，共 {n} 篇 =========="


@pytest.fixture(autouse=True)
def _category_unset(monkeypatch):
    monkeypatch.delenv("GARYU_CATEGORY", raising=False)


def _run(h, monkeypatch, value, mode=None):
    """value 是 None 時不設 GARYU_CATEGORY；sys.exit 的退出碼記在 h.exit_code（沒有就是 None）。"""
    if value is None:
        monkeypatch.delenv("GARYU_CATEGORY", raising=False)
    else:
        monkeypatch.setenv("GARYU_CATEGORY", value)
    h.collected.clear()
    h.exit_code = None
    try:
        h.run(mode)
    except SystemExit as e:
        h.exit_code = e.code
    return h.msgs


def _alone(h, monkeypatch, name, mode):
    """對照組：沒設 GARYU_CATEGORY、CATEGORIES 本來就只有這一類時的執行紀錄。"""
    real_main = main_mod.main

    def narrowed():
        monkeypatch.setattr(main_mod, "CATEGORIES", [c for c in main_mod.CATEGORIES if c.name == name])
        real_main()

    monkeypatch.setattr(main_mod, "main", narrowed)
    try:
        return _run(h, monkeypatch, None, mode)
    finally:
        monkeypatch.setattr(main_mod, "main", real_main)


def _fresh(h, monkeypatch):
    """同一個測試裡每次執行之前：jieba 先載好（只在第一次載入時印一行）、站台重建、KB MISS 清空。"""
    dry.filter_mod._load_jieba()
    shutil.rmtree(h.site)
    dry._seed_site(h.site)
    monkeypatch.setattr(dry.analyzer, "_KB_MISS_ACCUMULATOR", set())


# ── 沒設或空白：兩類都跑，traffic 在前，不多印 ─────────────────────

@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("value", [None, "", "   ", "\t\n"])
def test_unset_or_blank_runs_both_traffic_first_without_a_category_line(h, monkeypatch, value, mode):
    msgs = _run(h, monkeypatch, value, mode)
    assert h.collected == [COLLECTED["traffic"], COLLECTED["ffxiv"]]
    assert not [m for m in msgs if m.startswith("[類別]")]
    assert msgs[msgs.index(BANNER) + 1] == _begin("traffic"), "開始執行之後直接是第一個類別"
    assert msgs.index(_begin("traffic")) < msgs.index(_begin("ffxiv"))


@pytest.mark.parametrize("mode", MODES)
def test_blank_value_log_is_line_for_line_the_unset_log(h, monkeypatch, mode):
    _fresh(h, monkeypatch)
    unset = _run(h, monkeypatch, None, mode)
    for value in ("", "  "):
        _fresh(h, monkeypatch)
        assert _run(h, monkeypatch, value, mode) == unset, f"GARYU_CATEGORY={value!r} 的紀錄跟沒設時不同"


# ── 只跑一類 ──────────────────────────────────────────────────────

def test_traffic_alone_collects_and_writes_only_traffic(h, monkeypatch):
    before = dry._snapshot(h.site)
    msgs = _run(h, monkeypatch, "traffic")
    assert h.collected == [COLLECTED["traffic"]], "沒選的 ffxiv 不該 collect"
    ((table, name, args, kwargs),) = h.client.writes
    assert (table, name, kwargs) == ("articles", "upsert", {"on_conflict": "link", "ignore_duplicates": True})
    assert {r["content_type"] for r in args[0]} == {"traffic"}
    assert dry._snapshot(h.site) == before, "沒選 ffxiv 時站台檔不該動"
    assert h.analyze_all_calls == 0 and dry._gen_posts(h) == []
    assert _begin("ffxiv") not in msgs
    assert msgs[-1] == _done(2)


def test_ffxiv_alone_collects_and_writes_only_ffxiv(h, monkeypatch):
    msgs = _run(h, monkeypatch, "ffxiv")
    assert h.collected == [COLLECTED["ffxiv"]], "沒選的 traffic 不該 collect"
    ((table, name, args, kwargs),) = h.client.writes
    assert (table, name, kwargs) == ("articles", "upsert", {"on_conflict": "link"})
    assert {r["content_type"] for r in args[0]} == {"ffxiv"}
    assert dry.analyzer.GEMINI_EMBED_URL not in h.posts, "沒選 traffic 時不該打 embedding"
    assert _begin("traffic") not in msgs
    assert msgs[-1] == _done(2)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("sel", ["traffic", "ffxiv"])
def test_category_line_once_after_the_banner_and_before_the_category_starts(h, monkeypatch, sel, mode):
    msgs = _run(h, monkeypatch, sel, mode)
    assert msgs.count(LINE[sel]) == 1
    assert msgs.index(BANNER) < msgs.index(LINE[sel]) < msgs.index(_begin(sel))


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("sel", ["traffic", "ffxiv"])
def test_selected_log_is_the_category_alone_plus_the_category_line(h, monkeypatch, sel, mode):
    _fresh(h, monkeypatch)
    alone = _alone(h, monkeypatch, sel, mode)
    alone_exit = h.exit_code
    _fresh(h, monkeypatch)
    got = _run(h, monkeypatch, sel, mode)
    assert [m for m in got if m != LINE[sel]] == alone, f"沒選的 {OTHER[sel]} 不該印任何一行"
    assert h.exit_code == alone_exit


@pytest.mark.parametrize("value", [" ffxiv", "ffxiv  ", "\tffxiv\n"])
def test_surrounding_whitespace_is_stripped(h, monkeypatch, value):
    msgs = _run(h, monkeypatch, value)
    assert h.collected == [COLLECTED["ffxiv"]]
    assert msgs.count(LINE["ffxiv"]) == 1


# ── 不認得的值：collect 之前丟錯，不被逐類別的 try 吞掉 ────────────

@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("value", ["FFXIV", "Traffic", " TRAFFIC ", "all", "traffic,ffxiv", "traffic ffxiv"])
def test_other_values_raise_before_any_collect_and_are_not_swallowed(h, monkeypatch, value, mode):
    with pytest.raises(ValueError) as exc:
        _run(h, monkeypatch, value, mode)
    assert str(exc.value) == f"GARYU_CATEGORY 的值不認得：{value!r}；認得的值：traffic、ffxiv（沒設或空字串是全部都跑）"
    assert h.collected == []
    assert h.msgs == [], "丟錯之前不該印任何一行"


# ── 跟不發布的兩級一起用：固定行照舊，只有選的那一類 ────────────────

@pytest.mark.parametrize("sel, mode, dry_lines, before_end", [
    ("traffic", "dry-input", ["[不發布] 略過 upsert_traffic_buffer：2 筆", _end(0, 2)], _done(2)),
    ("traffic", "dry-full", ["[不發布] 略過 upsert_traffic_buffer：2 筆", _end(0, 2)], _done(2)),
    ("ffxiv", "dry-input", [STOP_FFXIV, _end(0, 0)], STOPPED),
    ("ffxiv", "dry-full", ["[不發布] 略過 站台檔 pages/ffxiv：2 筆", "[不發布] 略過 upsert_articles：2 筆", _end(2, 0)],
     _done(2)),
])
def test_dry_levels_keep_the_fixed_lines_of_the_selected_category_only(h, monkeypatch, sel, mode, dry_lines,
                                                                        before_end):
    msgs = _run(h, monkeypatch, sel, mode)
    assert msgs[:2] == [START[mode], BANNER]
    assert [m for m in msgs if m.startswith("[不發布]")] == [START[mode], *dry_lines]
    assert msgs[-2:] == [before_end, dry_lines[-1]]
    assert h.client.writes == []
    assert h.collected == [COLLECTED[sel]]
