"""spec 020 FR-001、FR-004～FR-006、FR-010：`weekly-dry-run.yml` 跟 `weekly.yml`、`auto-kb.yml` 保持一致。
每一類檢查是一個回傳問題清單的函式：沒改過的檔要全空，改壞一處的副本要有問題（對照組）。
PyYAML 把 `on` 讀成布林 True。"""
import copy
import os
import sys

import pytest
import yaml

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _REPO)

from src import run_mode  # noqa: E402

WF = os.path.join(_REPO, ".github", "workflows")
LEVELS = ["dry-input", "dry-full"]
LEVEL_EXPR = "${{ inputs.level }}"
ALWAYS = "${{ !cancelled() }}"
DRY_FULL_ONLY = "${{ inputs.level == 'dry-full' }}"
ARTIFACT_VARS = {"TRAFFIC_POOL_DIR", "ANALYSIS_OUTPUT_DIR", "FFXIV_POOL_DUMP"}
MAIN, TRAFFIC, AUTO_KB = "python main.py", "python scripts/traffic_weekly_analysis.py", "python scripts/auto_kb.py"
TAKE, COMPARE = "python scripts/dry_run_counts.py take", "python scripts/dry_run_counts.py compare"


def load(name):
    with open(os.path.join(WF, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def raw(name):
    with open(os.path.join(WF, name), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def files():
    return {"weekly": load("weekly.yml"), "dry": load("weekly-dry-run.yml"), "autokb": load("auto-kb.yml")}


def the_job(wf):
    jobs = wf.get("jobs") or {}
    assert len(jobs) == 1, f"預期一個 job，實際 {list(jobs)}"
    return next(iter(jobs.values()))


def steps(wf):
    return the_job(wf).get("steps") or []


def run_of(step):
    return (step.get("run") or "").strip()


def is_program(step):
    return "python " in run_of(step)


def find_run(wf, cmd):
    found = [s for s in steps(wf) if run_of(s) == cmd]
    return found[0] if len(found) == 1 else None


# ── 各類檢查：回傳問題清單

def prep_problems(weekly, dry):
    w = steps(weekly)
    names = [s.get("name") for s in w]
    if "安裝相依套件" not in names:
        return ["weekly.yml 找不到「安裝相依套件」，準備步驟的終點不見了"]
    prep = w[:names.index("安裝相依套件") + 1]
    problems = []
    if len(prep) != 8 or not prep[0].get("uses", "").startswith("actions/checkout@") \
            or sum((s.get("name") or "").startswith("寫入 config/") for s in prep) != 5 \
            or not prep[6].get("uses", "").startswith("actions/setup-python@"):
        problems.append("weekly.yml 的準備步驟不是 checkout、五個寫設定檔、設定 Python、安裝相依（比對的範圍要重定）")
    d = steps(dry)[:len(prep)]
    for i, (ws, ds) in enumerate(zip(prep, d)):
        if ws != ds:
            problems.append(f"準備步驟第 {i + 1} 步不同：weekly.yml {ws!r}／weekly-dry-run.yml {ds!r}")
    if len(d) < len(prep):
        problems.append(f"weekly-dry-run.yml 的準備步驟少了：{len(d)} 步，weekly.yml 是 {len(prep)} 步")
    return problems


def trigger_problems(dry, autokb):
    problems = []
    on = dry.get(True)
    if not isinstance(on, dict) or set(on) != {"workflow_dispatch"}:
        problems.append(f"觸發條件只能有 workflow_dispatch，實際：{on!r}")
    name = dry.get("name") or ""
    listed = autokb[True]["workflow_run"]["workflows"]
    if not name or name in listed or any(name.startswith(n) or n.startswith(name) for n in listed):
        problems.append(f"workflow 的 name {name!r} 會被 auto-kb.yml 的 workflow_run 認成週報：{listed}")
    return problems


def forbidden_problems(dry, text):
    problems = []
    for needle in ("wrangler", "pages deploy", "setup-node", "read-after-write", "cp pages/shared"):
        if needle in text:
            problems.append(f"weekly-dry-run.yml 出現 {needle!r}：不發布的執行不部署、不驗剛寫入的資料、不複製站台資源")
    for s in steps(dry):
        if "驗證本週資料" in (s.get("name") or ""):
            problems.append(f"有「驗證本週資料可由 Supabase 讀取」那一步：{s.get('name')}")
        if "CLOUDFLARE_API_TOKEN" in (s.get("env") or {}) and not run_of(s).startswith(TAKE):
            problems.append(f"CLOUDFLARE_API_TOKEN 只能給讀部署時間的計數步驟，這一步不是：{s.get('name')!r}")
        if s.get("uses", "").startswith("cloudflare/"):
            problems.append(f"用了 Cloudflare 的 action：{s['uses']}")
    return problems


def level_problems(dry):
    problems = []
    inputs = ((dry.get(True) or {}).get("workflow_dispatch") or {}).get("inputs") or {}
    level = inputs.get("level") or {}
    if set(inputs) != {"level"}:
        problems.append(f"輸入只能有 level，實際：{sorted(inputs)}")
    if level.get("required") is not True or level.get("type") != "choice" or level.get("options") != LEVELS:
        problems.append(f"level 要是必填的選項、值恰好是 {LEVELS}：{level!r}")
    for s in steps(dry):
        if is_program(s) and (s.get("env") or {}).get("GARYU_RUN_MODE") != LEVEL_EXPR:
            problems.append(f"程式步驟 {s.get('name')!r} 的 GARYU_RUN_MODE 不是 {LEVEL_EXPR}")
    return problems


def _env_pair(ref_step, dry_step, where):
    if ref_step is None:
        return [f"{where}：參照的檔裡找不到這一步（比對的依據不見了）"]
    if dry_step is None:
        return [f"{where}：weekly-dry-run.yml 找不到對應的步驟"]
    ref, got = ref_step.get("env") or {}, dry_step.get("env") or {}
    problems = [f"{where}：{k} 缺少或值不同（{ref[k]!r} → {got.get(k)!r}）" for k in ref if got.get(k) != ref[k]]
    extra = set(got) - set(ref) - ARTIFACT_VARS - {"GARYU_RUN_MODE"}
    if extra:
        problems.append(f"{where}：多出 {sorted(extra)}，多的只能是 GARYU_RUN_MODE 與產物路徑")
    return problems


def env_problems(weekly, dry, autokb):
    problems = []
    for cmd in (MAIN, TRAFFIC):
        problems += _env_pair(find_run(weekly, cmd), find_run(dry, cmd), cmd)
    problems += _env_pair(find_run(autokb, AUTO_KB), find_run(dry, AUTO_KB), AUTO_KB + "（對 auto-kb.yml）")
    known = {}
    for s in steps(weekly) + steps(autokb):
        for k, v in (s.get("env") or {}).items():
            known.setdefault(k, set()).add(v)
    for s in steps(dry):
        for k, v in (s.get("env") or {}).items():
            if k in known and v not in known[k]:
                problems.append(f"{s.get('name')!r} 的 {k} 是 {v!r}，參照檔裡是 {sorted(known[k])}")
    for var in ("TRAFFIC_POOL_DIR", "ANALYSIS_OUTPUT_DIR"):
        values = {(s.get("env") or {}).get(var) for s in steps(dry) if var in (s.get("env") or {})}
        if len(values) != 1:
            problems.append(f"{var} 在各步驟的值要相同：{values}")
    needs = {MAIN: {"TRAFFIC_POOL_DIR", "ANALYSIS_OUTPUT_DIR"}, TRAFFIC: {"TRAFFIC_POOL_DIR", "ANALYSIS_OUTPUT_DIR"},
             AUTO_KB: {"ANALYSIS_OUTPUT_DIR"}}
    for cmd, want in needs.items():
        step = find_run(dry, cmd)
        if step is not None and not want <= set(step.get("env") or {}):
            problems.append(f"{cmd} 少了產物路徑：{sorted(want - set(step.get('env') or {}))}")
    return problems


def job_problems(weekly, dry):
    w, d = the_job(weekly), the_job(dry)
    problems = [f"{k} 不同：{w.get(k)!r} → {d.get(k)!r}" for k in ("timeout-minutes", "environment", "runs-on")
                if w.get(k) != d.get(k)]
    if weekly.get("permissions") != dry.get("permissions"):
        problems.append(f"permissions 不同：{weekly.get('permissions')!r} → {dry.get('permissions')!r}")
    return problems


def order_problems(dry):
    progs = [s for s in steps(dry) if is_program(s)]
    runs = [run_of(s) for s in progs]
    shape = [TAKE, MAIN, TRAFFIC, AUTO_KB, TAKE, COMPARE]
    if len(runs) != len(shape) or not all(r == want or (want in (TAKE, COMPARE) and r.startswith(want))
                                          for r, want in zip(runs, shape)):
        return [f"程式步驟的順序要是 計數、main、交通分析、術語收錄、計數、比對：{runs}"]
    problems = []
    before, after, cmp_ = runs[0], runs[4], runs[5]
    if "counts_before.json" not in before or "counts_after.json" not in after \
            or "counts_before.json" not in cmp_ or "counts_after.json" not in cmp_:
        problems.append(f"比對要讀兩次計數寫的檔：{before!r}／{after!r}／{cmp_!r}")
    if any("$TRAFFIC_POOL_DIR/" not in r for r in (before, after, cmp_)):
        problems.append("兩份計數要寫在 TRAFFIC_POOL_DIR 裡（traffic-pool 產物）")
    if any(p.get("if") for p in progs[:3]):
        problems.append("計數、main、交通分析照預設：前面失敗就不跑")
    if progs[3].get("if") != DRY_FULL_ONLY:
        problems.append(f"術語收錄只在第二級跑：if 要是 {DRY_FULL_ONLY}，實際 {progs[3].get('if')!r}")
    for p in progs[4:]:
        if p.get("if") != ALWAYS:
            problems.append(f"{p.get('name')!r} 要在前面失敗時也跑：if 要是 {ALWAYS}")
    return problems


def upload_problems(weekly, dry):
    all_steps = steps(dry)
    uploads = [s for s in all_steps if s.get("uses", "").startswith("actions/upload-artifact@")]
    by_name = {(s.get("with") or {}).get("name"): s for s in uploads}
    if sorted(by_name) != ["analysis-output", "ffxiv-pool", "traffic-pool"] or len(uploads) != 3:
        return [f"產物要恰好是 ffxiv-pool、traffic-pool、analysis-output：{sorted(map(str, by_name))}"]
    problems = []
    w_ffxiv = [s for s in steps(weekly) if (s.get("with") or {}).get("name") == "ffxiv-pool"]
    if [by_name["ffxiv-pool"]] != w_ffxiv:
        problems.append("ffxiv-pool 的上傳步驟要跟 weekly.yml 的相同（沿用現有的）")
    env = {}
    for s in all_steps:
        env.update(s.get("env") or {})
    for name, var in (("ffxiv-pool", "FFXIV_POOL_DUMP"), ("traffic-pool", "TRAFFIC_POOL_DIR"),
                      ("analysis-output", "ANALYSIS_OUTPUT_DIR")):
        if (by_name[name].get("with") or {}).get("path") != env.get(var):
            problems.append(f"{name} 的 path 要是 {var} 的值 {env.get(var)!r}")
    if by_name["traffic-pool"].get("if") != ALWAYS:
        problems.append(f"traffic-pool 要在前面失敗時也上傳：if 要是 {ALWAYS}")
    if by_name["analysis-output"].get("if") != "${{ !cancelled() && inputs.level == 'dry-full' }}":
        problems.append("analysis-output 只有第二級有，前面失敗時也上傳")
    last_program = max(i for i, s in enumerate(all_steps) if is_program(s))
    if any(all_steps.index(u) < last_program for u in uploads):
        problems.append("上傳要排在最後的計數與比對之後，兩份計數才會在產物裡")
    return problems


# ── 沒改過的檔：全部沒有問題

def test_preparation_steps_are_identical(files):
    assert prep_problems(files["weekly"], files["dry"]) == []


def test_only_manual_trigger_and_not_seen_by_auto_kb(files):
    assert trigger_problems(files["dry"], files["autokb"]) == []


def test_no_deploy_no_read_after_write(files):
    assert forbidden_problems(files["dry"], raw("weekly-dry-run.yml")) == []


def test_level_is_a_required_choice_passed_unchanged(files):
    assert LEVELS == [run_mode.DRY_INPUT, run_mode.DRY_FULL]
    assert level_problems(files["dry"]) == []


def test_program_step_env_matches_weekly_and_auto_kb(files):
    assert env_problems(files["weekly"], files["dry"], files["autokb"]) == []


def test_job_settings_match_weekly(files):
    assert job_problems(files["weekly"], files["dry"]) == []


def test_step_order_and_conditions(files):
    assert order_problems(files["dry"]) == []


def test_three_artifacts_uploaded_even_after_failure(files):
    assert upload_problems(files["weekly"], files["dry"]) == []


def test_weekly_still_has_the_steps_the_dry_run_leaves_out(files):
    text = raw("weekly.yml")
    assert "wrangler" in text and "read-after-write" in text, "forbidden_problems 找的字樣要在 weekly.yml 裡真的存在"
    assert "GARYU_RUN_MODE" not in text, "正式排程的檔不設執行模式"


# ── 對照組：改壞一處的副本要有問題

def _step(wf, pred):
    return next(s for s in steps(wf) if pred(s))


def _set_env(cmd, key, value):
    def mutate(f):
        env = _step(f["dry"], lambda s: run_of(s) == cmd).setdefault("env", {})
        if value is None:
            env.pop(key)
        else:
            env[key] = value
    return mutate


def _edit_prep_char(f):
    s = steps(f["dry"])[1]
    s["run"] = s["run"].replace("sources_traffic.yml", "sources_traffic.ym", 1)


def _weekly_gains_var(f):
    _step(f["weekly"], lambda s: run_of(s) == MAIN)["env"]["GEMINI_MODEL_DIGEST"] = "${{ vars.GEMINI_MODEL_DIGEST }}"


def _add_deploy(f):
    steps(f["dry"]).append({"name": "Deploy", "run": "npx wrangler@4.144.0 pages deploy .",
                            "env": {"CLOUDFLARE_API_TOKEN": "${{ secrets.CLOUDFLARE_API_TOKEN }}"}})


def _token_on_main(f):
    _set_env(MAIN, "CLOUDFLARE_API_TOKEN", "${{ secrets.CLOUDFLARE_API_TOKEN }}")(f)


def _add_verify(f):
    steps(f["dry"]).append({"name": "驗證本週資料可由 Supabase 讀取", "run": "echo ok"})


def _with(path, fn):
    def mutate(f):
        fn(f, path)
    return mutate


def _upload(f, name):
    return _step(f["dry"], lambda s: (s.get("with") or {}).get("name") == name)


MUTATIONS = {
    "準備步驟改一個字": (_edit_prep_char, "prep"),
    "準備步驟的 Python 版本": (lambda f: steps(f["dry"])[6]["with"].update({"python-version": "3.12"}), "prep"),
    "準備步驟少一步": (lambda f: steps(f["dry"]).pop(3), "prep"),
    "加排程": (lambda f: f["dry"][True].update({"schedule": [{"cron": "0 0 * * 1"}]}), "trigger"),
    "加 workflow_run": (lambda f: f["dry"][True].update({"workflow_run": {"workflows": ["x"]}}), "trigger"),
    "name 跟週報相同": (lambda f: f["dry"].update({"name": "Garyu News Scraper 週報"}), "trigger"),
    "name 以週報的名字開頭": (lambda f: f["dry"].update({"name": "Garyu News Scraper 週報 試跑"}), "trigger"),
    "加部署步驟": (_add_deploy, "forbidden"),
    "token 給了 main": (_token_on_main, "forbidden"),
    "加讀回驗證": (_add_verify, "forbidden"),
    "level 多一個值": (lambda f: f["dry"][True]["workflow_dispatch"]["inputs"]["level"]["options"].append("formal"), "level"),
    "level 不必填": (lambda f: f["dry"][True]["workflow_dispatch"]["inputs"]["level"].update({"required": False}), "level"),
    "level 不是選項": (lambda f: f["dry"][True]["workflow_dispatch"]["inputs"]["level"].update({"type": "string"}), "level"),
    "多一個輸入": (lambda f: f["dry"][True]["workflow_dispatch"]["inputs"].update({"x": {"type": "string"}}), "level"),
    "交通分析寫死 dry-full": (_set_env(TRAFFIC, "GARYU_RUN_MODE", "dry-full"), "level"),
    "計數步驟沒帶模式": (lambda f: _step(f["dry"], lambda s: run_of(s).startswith(TAKE))["env"].pop("GARYU_RUN_MODE"), "level"),
    "main 少了模型變數": (_set_env(MAIN, "GEMINI_MODEL_NAME", None), "env"),
    "main 的值不同": (_set_env(MAIN, "GEMINI_MODEL_NAME", "${{ vars.GEMINI_MODEL_NAME }}"), "env"),
    "交通分析少了設定路徑": (_set_env(TRAFFIC, "JIEBA_USERDICT_PATH", None), "env"),
    "術語收錄少了 key": (_set_env(AUTO_KB, "GEMINI_API_KEY", None), "env"),
    "多出無關的變數": (_set_env(MAIN, "DEBUG", "1"), "env"),
    "weekly 加了新變數沒跟上": (_weekly_gains_var, "env"),
    "計數步驟的 secret 打錯": (lambda f: _step(f["dry"], lambda s: run_of(s).startswith(TAKE))["env"].update(
        {"SUPABASE_URL": "${{ secrets.SUPABASE_URI }}"}), "env"),
    "產物目錄不一致": (_set_env(TRAFFIC, "TRAFFIC_POOL_DIR", "elsewhere"), "env"),
    "術語收錄少了產物目錄": (_set_env(AUTO_KB, "ANALYSIS_OUTPUT_DIR", None), "env"),
    "timeout 不同": (lambda f: the_job(f["dry"]).update({"timeout-minutes": 20}), "job"),
    "environment 不同": (lambda f: the_job(f["dry"]).update({"environment": "staging"}), "job"),
    "permissions 不同": (lambda f: f["dry"].update({"permissions": {"contents": "write"}}), "job"),
    "術語收錄每級都跑": (lambda f: _step(f["dry"], lambda s: run_of(s) == AUTO_KB).pop("if"), "order"),
    "比對在失敗後不跑": (lambda f: _step(f["dry"], lambda s: run_of(s).startswith(COMPARE)).pop("if"), "order"),
    "結束的計數在失敗後不跑": (lambda f: [s for s in steps(f["dry"]) if run_of(s).startswith(TAKE)][1].pop("if"), "order"),
    "main 在失敗後也跑": (lambda f: _step(f["dry"], lambda s: run_of(s) == MAIN).update({"if": ALWAYS}), "order"),
    "比對讀錯檔": (lambda f: _step(f["dry"], lambda s: run_of(s).startswith(COMPARE)).update(
        {"run": "python scripts/dry_run_counts.py compare a.json b.json"}), "order"),
    "少了結束的計數": (lambda f: steps(f["dry"]).remove([s for s in steps(f["dry"]) if run_of(s).startswith(TAKE)][1]),
                "order"),
    "traffic-pool 失敗時不上傳": (_with("traffic-pool", lambda f, n: _upload(f, n).pop("if")), "upload"),
    "analysis-output 改名": (_with("analysis-output", lambda f, n: _upload(f, n)["with"].update({"name": "analysis"})), "upload"),
    "analysis-output 第一級也傳": (_with("analysis-output", lambda f, n: _upload(f, n).update({"if": ALWAYS})), "upload"),
    "traffic-pool 路徑不對": (_with("traffic-pool", lambda f, n: _upload(f, n)["with"].update({"path": "x"})), "upload"),
    "ffxiv-pool 跟週報不同": (_with("ffxiv-pool", lambda f, n: _upload(f, n)["with"].update(
        {"if-no-files-found": "error"})), "upload"),
    "上傳排在比對前面": (lambda f: steps(f["dry"]).insert(9, steps(f["dry"]).pop(
        steps(f["dry"]).index(_upload(f, "traffic-pool")))), "upload"),
}

CHECKS = {
    "prep": lambda f, t: prep_problems(f["weekly"], f["dry"]),
    "trigger": lambda f, t: trigger_problems(f["dry"], f["autokb"]),
    "forbidden": lambda f, t: forbidden_problems(f["dry"], t),
    "level": lambda f, t: level_problems(f["dry"]),
    "env": lambda f, t: env_problems(f["weekly"], f["dry"], f["autokb"]),
    "job": lambda f, t: job_problems(f["weekly"], f["dry"]),
    "order": lambda f, t: order_problems(f["dry"]),
    "upload": lambda f, t: upload_problems(f["weekly"], f["dry"]),
}


@pytest.mark.parametrize("label", list(MUTATIONS))
def test_a_broken_copy_is_caught(files, label):
    mutate, check = MUTATIONS[label]
    broken = copy.deepcopy(files)
    mutate(broken)
    text = yaml.safe_dump(broken["dry"], allow_unicode=True)
    assert CHECKS[check](broken, text), f"改壞「{label}」之後 {check} 沒有找到問題"
