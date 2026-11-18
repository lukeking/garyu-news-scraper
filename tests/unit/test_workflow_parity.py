"""spec 020 FR-001、FR-004～FR-006、FR-010 與 GNS-20261013-4g9「拆 workflow 的契約」：兩支正式週報、不發布週報、auto-kb.yml 互相對住。
每一類檢查是一個回傳問題清單的函式：沒改過的檔要全空，改壞一處的副本要有問題（對照組）。
PyYAML 把 `on` 讀成布林 True。"""
import copy
import json
import os
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _REPO)

from src import run_mode  # noqa: E402

WF = os.path.join(_REPO, ".github", "workflows")
FORMAL = {"traffic": "weekly-traffic.yml", "ffxiv": "weekly-ffxiv.yml"}
CATEGORIES = ["traffic", "ffxiv"]
OTHER = {"traffic": "ffxiv", "ffxiv": "traffic"}
LEVELS = ["dry-input", "dry-full"]
LEVEL_EXPR = "${{ inputs.level }}"
CATEGORY_EXPR = "${{ inputs.category }}"
ALWAYS = "${{ !cancelled() }}"
DRY_FULL_ONLY = "${{ inputs.level == 'dry-full' }}"
TRAFFIC_ONLY = "${{ inputs.category == 'traffic' }}"
AUTO_KB_ONLY = "${{ inputs.level == 'dry-full' && inputs.category == 'ffxiv' }}"
ARTIFACT_VARS = {"TRAFFIC_POOL_DIR", "ANALYSIS_OUTPUT_DIR", "FFXIV_POOL_DUMP"}
MAIN, TRAFFIC, AUTO_KB = "python main.py", "python scripts/traffic_weekly_analysis.py", "python scripts/auto_kb.py"
TAKE, COMPARE = "python scripts/dry_run_counts.py take", "python scripts/dry_run_counts.py compare"
VERIFY, PING = "驗證本週資料可由 Supabase 讀取", "Ping Supabase（防免費 tier 閒置暫停）"
PREP_STEPS = 8
GUARD_ENV = {"LEVEL": LEVEL_EXPR}
CATEGORY_GUARD_ENV = {"CATEGORY": CATEGORY_EXPR}
# 兩個檢查要放行的只有各自那兩個值；None 是環境裡根本沒有那個變數
GUARD_CASES = [("dry-input", True), ("dry-full", True), ("", False), (None, False), ("formal", False), ("dry", False),
               ("DRY-FULL", False), (" dry-full", False), ("dry-full ", False), ("dry-input dry-full", False)]
CATEGORY_CASES = [("traffic", True), ("ffxiv", True), ("", False), (None, False), ("all", False), ("TRAFFIC", False),
                  (" traffic", False), ("ffxiv ", False), ("traffic ffxiv", False), ("traffic,ffxiv", False)]
GUARDS = [("level", GUARD_ENV, GUARD_CASES), ("category", CATEGORY_GUARD_ENV, CATEGORY_CASES)]
# 讀回驗證那一步換上的假 requests：印出查詢的網址，回傳 FAKE_ROWS 的列
FAKE_REQUESTS = """import json, os
class _Resp:
    def raise_for_status(self):
        pass
    def json(self):
        return json.loads(os.environ["FAKE_ROWS"])
def get(url, **kwargs):
    print("GET " + url)
    return _Resp()
"""


def load(name):
    with open(os.path.join(WF, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def raw(name):
    with open(os.path.join(WF, name), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def files():
    every = {n: load(n) for n in sorted(os.listdir(WF)) if n.endswith((".yml", ".yaml"))}
    return {"traffic": every[FORMAL["traffic"]], "ffxiv": every[FORMAL["ffxiv"]], "dry": every["weekly-dry-run.yml"],
            "autokb": every["auto-kb.yml"], "all": every}


def the_job(wf):
    jobs = wf.get("jobs") or {}
    assert len(jobs) == 1, f"預期一個 job，實際 {list(jobs)}"
    return next(iter(jobs.values()))


def steps(wf):
    return the_job(wf).get("steps") or []


def run_of(step):
    return (step.get("run") or "").strip()


def guard_step(wf, i=0):
    all_steps = steps(wf)
    return all_steps[PREP_STEPS + i] if len(all_steps) > PREP_STEPS + i else {}


def program_steps(wf):
    """準備步驟與兩個檢查之後，每一個有 run 的步驟都算程式步驟，不看它用什麼指令叫程式。"""
    return [s for s in steps(wf)[PREP_STEPS + len(GUARDS):] if "run" in s]


def find_run(wf, cmd):
    found = [s for s in steps(wf) if run_of(s) == cmd]
    return found[0] if len(found) == 1 else None


def find_named(wf, name):
    found = [s for s in steps(wf) if s.get("name") == name]
    return found[0] if len(found) == 1 else None


def dispatch_inputs(wf):
    return ((wf.get(True) or {}).get("workflow_dispatch") or {}).get("inputs") or {}


def runs_main(step):
    return any(t == "main.py" or t.endswith("/main.py") for t in run_of(step).split())


def main_env(wf):
    return (find_run(wf, MAIN) or {}).get("env") or {}


# ── 各類檢查：回傳問題清單

def _prep_pair(formal, dry, name):
    w = steps(formal)
    names = [s.get("name") for s in w]
    if "安裝相依套件" not in names:
        return [f"{name} 找不到「安裝相依套件」，準備步驟的終點不見了"]
    prep = w[:names.index("安裝相依套件") + 1]
    problems = []
    if len(prep) != 8 or not prep[0].get("uses", "").startswith("actions/checkout@") \
            or sum((s.get("name") or "").startswith("寫入 config/") for s in prep) != 5 \
            or not prep[6].get("uses", "").startswith("actions/setup-python@"):
        problems.append(f"{name} 的準備步驟不是 checkout、五個寫設定檔、設定 Python、安裝相依（比對的範圍要重定）")
    d = steps(dry)[:len(prep)]
    for i, (ws, ds) in enumerate(zip(prep, d)):
        if ws != ds:
            problems.append(f"準備步驟第 {i + 1} 步不同：{name} {ws!r}／weekly-dry-run.yml {ds!r}")
    if len(d) < len(prep):
        problems.append(f"weekly-dry-run.yml 的準備步驟少了：{len(d)} 步，{name} 是 {len(prep)} 步")
    return problems


def prep_problems(f):
    return [p for cat in CATEGORIES for p in _prep_pair(f[cat], f["dry"], FORMAL[cat])]


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


def _choice_problems(inputs, key, options):
    spec = inputs.get(key) or {}
    problems = []
    if spec.get("required") is not True or spec.get("type") != "choice" or spec.get("options") != options:
        problems.append(f"{key} 要是必填的選項、值恰好是 {options}：{spec!r}")
    if set(spec) - {"description", "required", "type", "options"}:
        problems.append(f"{key} 只能有 description、required、type、options（有 default 的話，沒給 {key} 的觸發照預設值跑）：{sorted(spec)}")
    return problems


def level_problems(dry):
    problems = []
    inputs = dispatch_inputs(dry)
    if set(inputs) != {"level", "category"}:
        problems.append(f"輸入只能有 level、category，實際：{sorted(inputs)}")
    problems += _choice_problems(inputs, "level", LEVELS)
    for where, env in (("workflow", dry.get("env")), ("job", the_job(dry).get("env"))):
        if "GARYU_RUN_MODE" in (env or {}):
            problems.append(f"{where} 層不能設 GARYU_RUN_MODE：模式只寫在每個程式步驟上")
    for s in program_steps(dry):
        if (s.get("env") or {}).get("GARYU_RUN_MODE") != LEVEL_EXPR:
            problems.append(f"程式步驟 {s.get('name')!r} 的 GARYU_RUN_MODE 不是 {LEVEL_EXPR}")
    return problems


def category_problems(f):
    """兩支正式的 GARYU_CATEGORY 是檔名那一類的字面值；不發布那一支是必填選項，main 照傳。"""
    problems = _choice_problems(dispatch_inputs(f["dry"]), "category", CATEGORIES)
    for cat in CATEGORIES:
        got = main_env(f[cat]).get("GARYU_CATEGORY")
        if got != cat:
            problems.append(f"{FORMAL[cat]} 的 {MAIN} 要帶寫成字面值的 GARYU_CATEGORY: {cat}，實際 {got!r}")
    got = main_env(f["dry"]).get("GARYU_CATEGORY")
    if got != CATEGORY_EXPR:
        problems.append(f"weekly-dry-run.yml 的 {MAIN} 的 GARYU_CATEGORY 要是 {CATEGORY_EXPR}，實際 {got!r}")
    return problems


def main_problems(every):
    """每一個跑 main.py 的步驟都在自己的 env 指定類別：沒指定時程式兩類都跑。"""
    problems, seen = [], set()
    for name, wf in sorted(every.items()):
        for job in (wf.get("jobs") or {}).values():
            for s in job.get("steps") or []:
                if not runs_main(s):
                    continue
                seen.add(name)
                got = (s.get("env") or {}).get("GARYU_CATEGORY")
                if got not in CATEGORIES + [CATEGORY_EXPR]:
                    problems.append(f"{name} 的 {run_of(s)!r} 沒有指定類別：GARYU_CATEGORY 是 {got!r}")
    missing = sorted((set(FORMAL.values()) | {"weekly-dry-run.yml"}) - seen)
    if missing:
        problems.append(f"這幾支找不到跑 main.py 的步驟，檢查打偏了：{missing}")
    return problems


def gone_problems(every):
    return [f"{n} 還在：已由 {FORMAL['traffic']}、{FORMAL['ffxiv']} 取代" for n in ("weekly.yml", "weekly.yaml") if n in every]


def autokb_problems(f):
    problems = []
    listed = ((f["autokb"].get(True) or {}).get("workflow_run") or {}).get("workflows")
    ffxiv, traffic = f["ffxiv"].get("name") or "", f["traffic"].get("name") or ""
    if not ffxiv or listed != [ffxiv]:
        problems.append(f"auto-kb.yml 的 workflow_run.workflows 要恰好是 FFXIV 週報的 name {ffxiv!r}：{listed!r}")
    if not traffic or any(traffic.startswith(n) or n.startswith(traffic) for n in listed or []):
        problems.append(f"交通週報的 name {traffic!r} 會被 auto-kb.yml 認成 FFXIV 週報：{listed!r}")
    return problems


def run_verify(step, rows):
    with tempfile.TemporaryDirectory() as tmp:
        lib, bin_ = os.path.join(tmp, "lib"), os.path.join(tmp, "bin")
        os.makedirs(lib)
        os.makedirs(bin_)
        with open(os.path.join(lib, "requests.py"), "w", encoding="utf-8") as fh:
            fh.write(FAKE_REQUESTS)
        os.symlink(sys.executable, os.path.join(bin_, "python"))
        env = {"PATH": bin_ + os.pathsep + os.environ.get("PATH", ""), "PYTHONPATH": lib, "PYTHONIOENCODING": "utf-8",
               "SUPABASE_URL": "https://example.invalid", "SUPABASE_SERVICE_ROLE_KEY": "k", "FAKE_ROWS": json.dumps(rows)}
        return subprocess.run(["bash", "-e", "-c", run_of(step)], env=env, cwd=tmp, capture_output=True,
                              encoding="utf-8")


def verify_problems(f):
    """跑兩支的讀回驗證（requests 換成假的）：查詢限本週、只認自己那一類；讀不到時失敗，訊息寫出是哪一類。"""
    problems = []
    for cat in CATEGORIES:
        step = find_named(f[cat], VERIFY)
        if step is None:
            problems.append(f"{FORMAL[cat]} 要恰好一步「{VERIFY}」")
            continue
        empty, ok = run_verify(step, []), run_verify(step, [{"week_id": "x"}])
        urls = [line[4:] for line in empty.stdout.splitlines() if line.startswith("GET ")]
        query = parse_qs(urlsplit(urls[0]).query) if len(urls) == 1 else {}
        if query.get("content_type") != [f"eq.{cat}"] or not query.get("week_id", [""])[0].startswith("eq."):
            problems.append(f"{FORMAL[cat]} 的讀回查詢要限本週 week_id、只認 content_type=eq.{cat}：{urls}")
        last = (empty.stderr.strip().splitlines() or [""])[-1]
        if empty.returncode == 0 or cat not in last or OTHER[cat] in last:
            problems.append(f"{FORMAL[cat]} 讀不到時要失敗、訊息寫出 {cat}：結束碼 {empty.returncode}，{last!r}")
        if ok.returncode != 0:
            problems.append(f"{FORMAL[cat]} 讀得到時要通過：結束碼 {ok.returncode}，{ok.stderr.strip()[-300:]!r}")
    return problems


def _copies_to(step, cat):
    return [line.strip() for line in run_of(step).splitlines()
            if line.strip().startswith("cp pages/shared/") and f" pages/{cat}/" in line]


def own_steps(cat):
    """每一類獨有的步驟：說法 → 判斷某一步是不是它。"""
    marks = {f"複製共用資源到 pages/{cat}": lambda s: bool(_copies_to(s, cat)),
             f"部署 garyu-{cat}-news": lambda s: f"--project-name=garyu-{cat}-news" in run_of(s)}
    if cat == "traffic":
        marks["週交通熱點分析"] = lambda s: run_of(s) == TRAFFIC
    else:
        marks["上傳 ffxiv-pool"] = lambda s: (s.get("with") or {}).get("name") == "ffxiv-pool"
    return marks


def exclusive_problems(f):
    problems = []
    for cat in CATEGORIES:
        for label, is_it in own_steps(cat).items():
            if sum(map(is_it, steps(f[cat]))) != 1:
                problems.append(f"{FORMAL[cat]} 要恰好一步「{label}」")
            if any(map(is_it, steps(f[OTHER[cat]]))):
                problems.append(f"{FORMAL[OTHER[cat]]} 出現 {cat} 獨有的「{label}」")
        copies = [c for s in steps(f[cat]) for c in _copies_to(s, cat)]
        want = [f"cp pages/shared/{x} pages/{cat}/{x}" for x in ("app.js", "shared.css")]
        if sorted(copies) != want:
            problems.append(f"{FORMAL[cat]} 要把 app.js、shared.css 各複製一次到 pages/{cat}：{copies}")
        other_keys = [_step_key(s) for s in steps(f[OTHER[cat]])]
        extra = [_step_key(s) for s in steps(f[cat])
                 if _step_key(s) not in other_keys and not any(is_it(s) for is_it in own_steps(cat).values())]
        if extra:
            problems.append(f"{FORMAL[cat]} 有兩支不共有、也不是 {cat} 獨有的步驟：{extra}")
    return problems


def _step_key(step):
    return step.get("name") or step.get("uses")


def _normalized(step, cat):
    """main 只差 GARYU_CATEGORY、讀回驗證只差類別名：拿掉這兩處之後兩支要逐字相同。"""
    s = copy.deepcopy(step)
    if run_of(s) == MAIN:
        (s.get("env") or {}).pop("GARYU_CATEGORY", None)
    elif s.get("name") == VERIFY:
        s["run"] = s["run"].replace(cat, "<類別>")
    return s


def formal_problems(f):
    t, x = f["traffic"], f["ffxiv"]
    problems = []
    on = t.get(True)
    if not isinstance(on, dict) or set(on) != {"schedule", "workflow_dispatch"} or len(on.get("schedule") or []) != 1:
        problems.append(f"{FORMAL['traffic']} 的觸發要是一個 cron 加 workflow_dispatch：{on!r}")
    if t.get(True) != x.get(True):
        problems.append(f"兩支的觸發不同：{t.get(True)!r}／{x.get(True)!r}")
    if t.get("permissions") != x.get("permissions"):
        problems.append(f"兩支的 permissions 不同：{t.get('permissions')!r}／{x.get('permissions')!r}")
    problems += [f"兩支的 {k} 不同" for k in ("runs-on", "environment") if the_job(t).get(k) != the_job(x).get(k)]
    t_keys, x_keys = [_step_key(s) for s in steps(t)], [_step_key(s) for s in steps(x)]
    shared = [k for k in t_keys if k in x_keys]
    # 讀回驗證在兩支的位置不同，由 verify_place_problems 各自釘住
    order = [k for k in shared if k != VERIFY]
    if order != [k for k in x_keys if k in t_keys and k != VERIFY]:
        problems.append(f"兩支都有的步驟順序不同（讀回驗證除外）：{order}")
    for k in shared:
        a = _normalized(steps(t)[t_keys.index(k)], "traffic")
        b = _normalized(steps(x)[x_keys.index(k)], "ffxiv")
        if a != b:
            problems.append(f"兩支都有的「{k}」內容不同：{a!r}／{b!r}")
    for k in (PING, "執行週報程式（寫入 Supabase）", VERIFY):
        if k not in shared:
            problems.append(f"兩支都要有「{k}」")
    if not any(str(k).startswith("actions/setup-node@") for k in shared):
        problems.append("兩支都要有 actions/setup-node（部署用）")
    return problems


def _verify_neighbours(cat):
    """讀回驗證之前要有的步驟、之後要有的步驟（說法 → 判斷）。"""
    main, own = {MAIN: runs_main}, own_steps(cat)
    if cat == "traffic":
        return {**main, **own}, {}
    return main, {k: own[k] for k in (f"複製共用資源到 pages/{cat}", f"部署 garyu-{cat}-news")}


def verify_place_problems(f):
    """交通的熱點分析讀前六天 daily 的列：讀回驗證排在 main 與交通獨有的步驟全部之後，只標紅、不擋部署。
    FFXIV 的部署靠當次的寫入：讀回驗證排在 main 之後，擋在複製與部署之前。"""
    problems = []
    for cat in CATEGORIES:
        all_steps, v = steps(f[cat]), find_named(f[cat], VERIFY)
        if v is None:
            problems.append(f"{FORMAL[cat]} 要恰好一步「{VERIFY}」，位置比不了")
            continue
        at = all_steps.index(v)
        earlier, later = _verify_neighbours(cat)
        problems += [f"{FORMAL[cat]} 的「{VERIFY}」要排在「{k}」之後" for k, is_it in earlier.items()
                     if not any(map(is_it, all_steps[:at]))]
        problems += [f"{FORMAL[cat]} 的「{VERIFY}」要排在「{k}」之前" for k, is_it in later.items()
                     if not any(map(is_it, all_steps[at + 1:]))]
    return problems


def gate_problems(f):
    """main 起的每一步靠預設的「前面都成功才跑」串起來：讀回驗證失敗要讓 run 變紅，FFXIV 那支還靠它擋下複製與部署。
    所以 job 與這些步驟都不能有 if 或 continue-on-error；例外只有 ffxiv-pool 的上傳（前面失敗時也要傳）。"""
    problems = []
    for cat in CATEGORIES:
        all_steps = steps(f[cat])
        first = next((i for i, s in enumerate(all_steps) if runs_main(s)), None)
        if first is None:
            problems.append(f"{FORMAL[cat]} 找不到跑 main.py 的步驟，檢查打偏了")
            continue
        gated = [("job", the_job(f[cat]))] + [(f"「{_step_key(s)}」", s) for s in all_steps[first:]
                                              if (s.get("with") or {}).get("name") != "ffxiv-pool"]
        problems += [f"{FORMAL[cat]} 的 {what} 不能有 {key}：{it[key]!r}" for what, it in gated
                     for key in ("if", "continue-on-error") if key in it]
    return problems


def guard_problems(dry):
    """空的 level 會被當成正式模式、空的 category 會被當成兩類都跑，所以第一個程式步驟之前依序各擋一次。"""
    problems = []
    for i, (what, want_env, cases) in enumerate(GUARDS):
        g = guard_step(dry, i)
        if g.get("env") != want_env or "if" in g or "run" not in g:
            problems.append(f"準備步驟之後第 {i + 1} 步要是 {what} 的檢查（env 恰好是 {want_env}、沒有 if）：{g!r}")
            continue
        (var,) = want_env
        for value, allowed in cases:
            env = {"PATH": os.environ.get("PATH", "")}
            if value is not None:
                env[var] = value
            done = subprocess.run(["bash", "-e", "-c", run_of(g)], env=env, capture_output=True, text=True)
            if (done.returncode == 0) != allowed:
                problems.append(f"{what} 的檢查對 {value!r} 的結束碼是 {done.returncode}，{'要放行' if allowed else '要失敗'}")
            elif not allowed and what not in done.stdout + done.stderr:
                problems.append(f"{what} 的檢查擋下 {value!r} 時沒有說原因")
    return problems


def _env_pair(ref_step, dry_step, where, skip=()):
    if ref_step is None:
        return [f"{where}：參照的檔裡找不到這一步（比對的依據不見了）"]
    if dry_step is None:
        return [f"{where}：weekly-dry-run.yml 找不到對應的步驟"]
    ref = {k: v for k, v in (ref_step.get("env") or {}).items() if k not in skip}
    got = {k: v for k, v in (dry_step.get("env") or {}).items() if k not in skip}
    problems = [f"{where}：{k} 缺少或值不同（{ref[k]!r} → {got.get(k)!r}）" for k in ref if got.get(k) != ref[k]]
    extra = set(got) - set(ref) - ARTIFACT_VARS - {"GARYU_RUN_MODE"}
    if extra:
        problems.append(f"{where}：多出 {sorted(extra)}，多的只能是 GARYU_RUN_MODE 與產物路徑")
    return problems


def env_problems(f):
    dry, autokb = f["dry"], f["autokb"]
    problems = []
    for cat, cmds in (("traffic", (MAIN, TRAFFIC)), ("ffxiv", (MAIN,))):
        for cmd in cmds:
            skip = ("GARYU_CATEGORY",) if cmd == MAIN else ()
            problems += _env_pair(find_run(f[cat], cmd), find_run(dry, cmd), f"{cmd}（對 {FORMAL[cat]}）", skip)
    problems += _env_pair(find_run(autokb, AUTO_KB), find_run(dry, AUTO_KB), AUTO_KB + "（對 auto-kb.yml）")
    known = {}
    for s in steps(f["traffic"]) + steps(f["ffxiv"]) + steps(autokb):
        for k, v in (s.get("env") or {}).items():
            if k != "GARYU_CATEGORY":
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


def job_problems(f):
    d = the_job(f["dry"])
    problems = []
    for cat in CATEGORIES:
        w = the_job(f[cat])
        problems += [f"{k} 跟 {FORMAL[cat]} 不同：{w.get(k)!r} → {d.get(k)!r}" for k in ("environment", "runs-on")
                     if w.get(k) != d.get(k)]
        if f[cat].get("permissions") != f["dry"].get("permissions"):
            problems.append(f"permissions 跟 {FORMAL[cat]} 不同：{f[cat].get('permissions')!r} → {f['dry'].get('permissions')!r}")
    limits = [the_job(f[cat]).get("timeout-minutes") for cat in CATEGORIES]
    if not all(isinstance(n, int) for n in limits) or d.get("timeout-minutes") != max(limits):
        problems.append(f"timeout-minutes 要是兩支正式的裡較大的那個：{limits} → {d.get('timeout-minutes')!r}")
    return problems


def order_problems(dry):
    progs = program_steps(dry)
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
    if any(p.get("if") for p in progs[:2]):
        problems.append("計數、main 照預設：前面失敗就不跑")
    if progs[2].get("if") != TRAFFIC_ONLY:
        problems.append(f"交通分析只在 traffic 跑：if 要是 {TRAFFIC_ONLY}，實際 {progs[2].get('if')!r}")
    if progs[3].get("if") != AUTO_KB_ONLY:
        problems.append(f"術語收錄只在 ffxiv 的第二級跑：if 要是 {AUTO_KB_ONLY}，實際 {progs[3].get('if')!r}")
    for p in progs[4:]:
        if p.get("if") != ALWAYS:
            problems.append(f"{p.get('name')!r} 要在前面失敗時也跑：if 要是 {ALWAYS}")
    return problems


def upload_problems(f):
    all_steps = steps(f["dry"])
    uploads = [s for s in all_steps if s.get("uses", "").startswith("actions/upload-artifact@")]
    by_name = {(s.get("with") or {}).get("name"): s for s in uploads}
    if sorted(by_name) != ["analysis-output", "ffxiv-pool", "traffic-pool"] or len(uploads) != 3:
        return [f"產物要恰好是 ffxiv-pool、traffic-pool、analysis-output：{sorted(map(str, by_name))}"]
    problems = []
    w_ffxiv = [s for s in steps(f["ffxiv"]) if (s.get("with") or {}).get("name") == "ffxiv-pool"]
    if [by_name["ffxiv-pool"]] != w_ffxiv:
        problems.append(f"ffxiv-pool 的上傳步驟要跟 {FORMAL['ffxiv']} 的相同（沿用現有的）")
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
    last_program = max(i for i, s in enumerate(all_steps) if i > PREP_STEPS and "run" in s)
    if any(all_steps.index(u) < last_program for u in uploads):
        problems.append("上傳要排在最後的計數與比對之後，兩份計數才會在產物裡")
    return problems


# ── 沒改過的檔：全部沒有問題

def test_preparation_steps_are_identical(files):
    assert prep_problems(files) == []


def test_only_manual_trigger_and_not_seen_by_auto_kb(files):
    assert trigger_problems(files["dry"], files["autokb"]) == []


def test_no_deploy_no_read_after_write(files):
    assert forbidden_problems(files["dry"], raw("weekly-dry-run.yml")) == []


def test_level_is_a_required_choice_passed_unchanged(files):
    assert LEVELS == [run_mode.DRY_INPUT, run_mode.DRY_FULL]
    assert level_problems(files["dry"]) == []


def test_categories_match_the_program_and_both_formal_files(files):
    from tests.unit.test_main_dry_run import main_mod
    assert CATEGORIES == [c.name for c in main_mod.CATEGORIES]
    assert category_problems(files) == []


def test_every_workflow_running_main_names_a_category(files):
    assert main_problems(files["all"]) == []


def test_weekly_yml_is_gone(files):
    assert gone_problems(files["all"]) == []


def test_auto_kb_follows_the_ffxiv_workflow_only(files):
    assert autokb_problems(files) == []


def test_read_after_write_checks_its_own_category(files):
    assert verify_problems(files) == []


def test_category_specific_steps_stay_in_their_own_file(files):
    assert exclusive_problems(files) == []


def test_formal_files_agree_with_each_other(files):
    assert formal_problems(files) == []


def test_read_after_write_sits_where_each_file_needs_it(files):
    assert verify_place_problems(files) == []


def test_steps_from_main_on_run_by_default_and_fail_the_run(files):
    assert gate_problems(files) == []


def test_level_and_category_are_checked_before_any_program_runs(files):
    assert guard_problems(files["dry"]) == []


def test_program_step_env_matches_formal_files_and_auto_kb(files):
    assert env_problems(files) == []


def test_job_settings_match_both_formal_files(files):
    assert job_problems(files) == []


def test_step_order_and_conditions(files):
    assert order_problems(files["dry"]) == []


def test_three_artifacts_uploaded_even_after_failure(files):
    assert upload_problems(files) == []


def test_formal_files_still_have_the_steps_the_dry_run_leaves_out(files):
    for cat in CATEGORIES:
        text = raw(FORMAL[cat])
        assert "wrangler" in text and "read-after-write" in text, f"forbidden_problems 找的字樣要在 {FORMAL[cat]} 裡真的存在"
        assert "GARYU_RUN_MODE" not in text, "正式排程的檔不設執行模式"


# ── 對照組：改壞一處的副本要有問題

def _step(wf, pred):
    return next(s for s in steps(wf) if pred(s))


def _set_env(cmd, key, value, wf="dry"):
    def mutate(f):
        env = _step(f[wf], lambda s: run_of(s) == cmd).setdefault("env", {})
        if value is None:
            env.pop(key)
        else:
            env[key] = value
    return mutate


def _edit_prep_char(wf):
    def mutate(f):
        s = steps(f[wf])[1]
        s["run"] = s["run"].replace("sources_traffic.yml", "sources_traffic.ym", 1)
    return mutate


def _formal_gains_var(cat):
    def mutate(f):
        _step(f[cat], lambda s: run_of(s) == MAIN)["env"]["GEMINI_MODEL_DIGEST"] = "${{ vars.GEMINI_MODEL_DIGEST }}"
    return mutate


def _add_deploy(f):
    steps(f["dry"]).append({"name": "Deploy", "run": "npx wrangler@4.144.0 pages deploy .",
                            "env": {"CLOUDFLARE_API_TOKEN": "${{ secrets.CLOUDFLARE_API_TOKEN }}"}})


def _token_on_main(f):
    _set_env(MAIN, "CLOUDFLARE_API_TOKEN", "${{ secrets.CLOUDFLARE_API_TOKEN }}")(f)


def _add_verify(f):
    steps(f["dry"]).append({"name": "驗證本週資料可由 Supabase 讀取", "run": "echo ok"})


def _add_step(cmd):
    def mutate(f):
        steps(f["dry"]).insert(PREP_STEPS + len(GUARDS) + 3, {"name": "另一支程式", "run": cmd})
    return mutate


def _guard_run(old, new, i=0):
    def mutate(f):
        g = guard_step(f["dry"], i)
        assert old in g["run"], f"第 {i + 1} 個檢查裡找不到 {old!r}，對照組要重寫"
        g["run"] = g["run"].replace(old, new)
    return mutate


def _replace_run(wf, pred, old, new):
    def mutate(f):
        s = _step(f[wf], pred)
        assert old in s["run"], f"{wf} 那一步裡找不到 {old!r}，對照組要重寫"
        s["run"] = s["run"].replace(old, new)
    return mutate


def _verify_run(cat, old, new):
    return _replace_run(cat, lambda s: s.get("name") == VERIFY, old, new)


def _with(path, fn):
    def mutate(f):
        fn(f, path)
    return mutate


def _upload(f, name, wf="dry"):
    return _step(f[wf], lambda s: (s.get("with") or {}).get("name") == name)


def _move_step(wf, name, to):
    def mutate(f):
        all_steps, moving = steps(f[wf]), find_named(f[wf], name)
        assert moving is not None, f"{wf} 找不到「{name}」，對照組要重寫"
        all_steps.insert(to, all_steps.pop(all_steps.index(moving)))
    return mutate


def _move_next_to(wf, moving, anchor, offset=0):
    """moving 那一步移到 anchor 那一步的前面（offset 0）或後面（offset 1）。"""
    def mutate(f):
        all_steps = steps(f[wf])
        step = all_steps.pop(all_steps.index(_step(f[wf], moving)))
        all_steps.insert(all_steps.index(_step(f[wf], anchor)) + offset, step)
    return mutate


def _drop_step(wf, pred):
    def mutate(f):
        steps(f[wf]).remove(_step(f[wf], pred))
    return mutate


def _copy_step_into(src, dst, pred):
    def mutate(f):
        steps(f[dst]).append(copy.deepcopy(_step(f[src], pred)))
    return mutate


def _autokb_lists(names):
    def mutate(f):
        f["autokb"][True]["workflow_run"]["workflows"] = [f[n]["name"] if n in FORMAL else n for n in names]
    return mutate


def _category_input(f):
    return f["dry"][True]["workflow_dispatch"]["inputs"]["category"]


def _is_copy(cat):
    return lambda s: bool(_copies_to(s, cat))


def _is_deploy(cat):
    return lambda s: f"--project-name=garyu-{cat}-news" in run_of(s)


def _is_verify(s):
    return s.get("name") == VERIFY


def _is_setup_node(s):
    return s.get("uses", "").startswith("actions/setup-node@")


def _set_key(wfs, pred, key, value):
    def mutate(f):
        for wf in wfs:
            _step(f[wf], pred)[key] = value
    return mutate


def _set_job_key(key, value):
    def mutate(f):
        for cat in CATEGORIES:
            the_job(f[cat])[key] = value
    return mutate


MUTATIONS = {
    "準備步驟改一個字": (_edit_prep_char("dry"), "prep"),
    "FFXIV 那支的準備步驟改一個字": (_edit_prep_char("ffxiv"), "prep"),
    "準備步驟的 Python 版本": (lambda f: steps(f["dry"])[6]["with"].update({"python-version": "3.12"}), "prep"),
    "準備步驟少一步": (lambda f: steps(f["dry"]).pop(3), "prep"),
    "加排程": (lambda f: f["dry"][True].update({"schedule": [{"cron": "0 0 * * 1"}]}), "trigger"),
    "加 workflow_run": (lambda f: f["dry"][True].update({"workflow_run": {"workflows": ["x"]}}), "trigger"),
    "name 跟舊週報相同": (lambda f: f["dry"].update({"name": "Garyu News Scraper 週報"}), "trigger"),
    "name 跟 FFXIV 週報相同": (lambda f: f["dry"].update({"name": f["ffxiv"]["name"]}), "trigger"),
    "name 以 FFXIV 週報的名字開頭": (lambda f: f["dry"].update({"name": f["ffxiv"]["name"] + " 試跑"}), "trigger"),
    "加部署步驟": (_add_deploy, "forbidden"),
    "token 給了 main": (_token_on_main, "forbidden"),
    "加讀回驗證": (_add_verify, "forbidden"),
    "level 多一個值": (lambda f: f["dry"][True]["workflow_dispatch"]["inputs"]["level"]["options"].append("formal"), "level"),
    "level 不必填": (lambda f: f["dry"][True]["workflow_dispatch"]["inputs"]["level"].update({"required": False}), "level"),
    "level 不是選項": (lambda f: f["dry"][True]["workflow_dispatch"]["inputs"]["level"].update({"type": "string"}), "level"),
    "多一個輸入": (lambda f: f["dry"][True]["workflow_dispatch"]["inputs"].update({"x": {"type": "string"}}), "level"),
    "少了 category 輸入": (lambda f: f["dry"][True]["workflow_dispatch"]["inputs"].pop("category"), "level"),
    "交通分析寫死 dry-full": (_set_env(TRAFFIC, "GARYU_RUN_MODE", "dry-full"), "level"),
    "計數步驟沒帶模式": (lambda f: _step(f["dry"], lambda s: run_of(s).startswith(TAKE))["env"].pop("GARYU_RUN_MODE"), "level"),
    "多一個 python3 步驟沒帶模式": (_add_step("python3 scripts/auto_kb.py"), "level"),
    "多一個 bash 步驟沒帶模式": (_add_step("bash run_weekly.sh"), "level"),
    "level 有預設值": (lambda f: f["dry"][True]["workflow_dispatch"]["inputs"]["level"].update({"default": "dry-full"}), "level"),
    "job 層設了空的模式": (lambda f: the_job(f["dry"]).update({"env": {"GARYU_RUN_MODE": ""}}), "level"),
    "workflow 層設了模式": (lambda f: f["dry"].update({"env": {"GARYU_RUN_MODE": "dry-full"}}), "level"),
    "category 多一個值": (lambda f: _category_input(f)["options"].append("all"), "category"),
    "category 少一個值": (lambda f: _category_input(f)["options"].pop(), "category"),
    "category 的值順序跟程式不同": (lambda f: _category_input(f)["options"].reverse(), "category"),
    "category 不必填": (lambda f: _category_input(f).update({"required": False}), "category"),
    "category 不是選項": (lambda f: _category_input(f).update({"type": "string"}), "category"),
    "category 有預設值": (lambda f: _category_input(f).update({"default": "traffic"}), "category"),
    "交通那支沒帶類別": (_set_env(MAIN, "GARYU_CATEGORY", None, "traffic"), "category"),
    "FFXIV 那支帶成 traffic": (_set_env(MAIN, "GARYU_CATEGORY", "traffic", "ffxiv"), "category"),
    "正式的類別讀輸入": (_set_env(MAIN, "GARYU_CATEGORY", CATEGORY_EXPR, "traffic"), "category"),
    "不發布的 main 寫死類別": (_set_env(MAIN, "GARYU_CATEGORY", "ffxiv"), "category"),
    "不發布的 main 沒帶類別": (_set_env(MAIN, "GARYU_CATEGORY", None), "category"),
    "FFXIV 的 main 類別是空的": (_set_env(MAIN, "GARYU_CATEGORY", "", "ffxiv"), "main"),
    "不發布的 main 類別讀錯輸入": (_set_env(MAIN, "GARYU_CATEGORY", "${{ inputs.level }}"), "main"),
    "多一支跑 main.py 沒帶類別的 workflow": (lambda f: f["all"].update(
        {"other.yml": {"jobs": {"x": {"steps": [{"run": "python main.py"}]}}}}), "main"),
    "多一支用 python3 跑 ./main.py": (lambda f: f["all"].update(
        {"other.yml": {"jobs": {"a": {"steps": []}, "b": {"steps": [{"run": "cd x\npython3 ./main.py --y"}]}}}}), "main"),
    "交通那支的 main 換了寫法、檢查打偏": (_replace_run("traffic", lambda s: run_of(s) == MAIN, "main.py", "app.py"), "main"),
    "weekly.yml 還在": (lambda f: f["all"].update({"weekly.yml": copy.deepcopy(f["traffic"])}), "gone"),
    "auto-kb 還認舊的週報名": (_autokb_lists(["Garyu News Scraper 週報"]), "autokb"),
    "auto-kb 兩支都認": (_autokb_lists(["traffic", "ffxiv"]), "autokb"),
    "auto-kb 認交通那支": (_autokb_lists(["traffic"]), "autokb"),
    "auto-kb 多認一支不相干的": (_autokb_lists(["ffxiv", "別的 workflow"]), "autokb"),
    "FFXIV 改名、auto-kb 沒跟上": (lambda f: f["ffxiv"].update({"name": f["ffxiv"]["name"] + " v2"}), "autokb"),
    "交通的 name 跟 FFXIV 相同": (lambda f: f["traffic"].update({"name": f["ffxiv"]["name"]}), "autokb"),
    "交通的 name 是 FFXIV 的開頭": (lambda f: f["traffic"].update({"name": "Garyu News Scraper 週報"}), "autokb"),
    "交通的讀回不分類別": (_verify_run("traffic", "&content_type=eq.traffic", ""), "verify"),
    "FFXIV 的讀回查成交通": (_verify_run("ffxiv", "content_type=eq.ffxiv", "content_type=eq.traffic"), "verify"),
    "交通的讀回兩類都認": (_verify_run("traffic", "content_type=eq.traffic", "content_type=in.(traffic,ffxiv)"), "verify"),
    "讀回不限本週": (_verify_run("ffxiv", "&week_id=eq.{week_id}", ""), "verify"),
    "FFXIV 讀不到時的訊息沒寫類別": (_verify_run("ffxiv", "本週 ffxiv 資料", "本週資料"), "verify"),
    "交通讀不到時的訊息寫成 FFXIV": (_verify_run("traffic", "本週 traffic 資料", "本週 ffxiv 資料"), "verify"),
    "讀不到也通過": (_verify_run("traffic", "if not rows:", "if rows is None:"), "verify"),
    "交通讀不到時的訊息兩類都寫": (_verify_run("traffic", "本週 traffic 資料", "本週 traffic、ffxiv 資料"), "verify"),
    "FFXIV 讀不到時只印訊息、照樣通過": (_verify_run("ffxiv", "raise RuntimeError(f\"Supabase 尚未讀到",
                                           "import sys; sys.stderr.write(f\"Supabase 尚未讀到"), "verify"),
    "讀得到也失敗": (_verify_run("ffxiv", "print(f\"Supabase read-after-write OK", "raise SystemExit(f\"x"), "verify"),
    "交通那支少了讀回驗證": (_drop_step("traffic", lambda s: s.get("name") == VERIFY), "verify"),
    "交通那支多了 ffxiv-pool 上傳": (_copy_step_into("ffxiv", "traffic", lambda s: (s.get("with") or {}).get("name") == "ffxiv-pool"),
                             "exclusive"),
    "FFXIV 那支多了交通分析": (_copy_step_into("traffic", "ffxiv", lambda s: run_of(s) == TRAFFIC), "exclusive"),
    "FFXIV 那支多一步術語收錄": (lambda f: steps(f["ffxiv"]).append({"name": "術語收錄", "run": AUTO_KB}), "exclusive"),
    "交通那支在讀回驗證前多一步": (lambda f: steps(f["traffic"]).insert(PREP_STEPS + 2, {"name": "多的一步", "run": "echo hi"}),
                         "exclusive"),
    "FFXIV 那支部署了交通的站": (_copy_step_into("traffic", "ffxiv", _is_deploy("traffic")), "exclusive"),
    "交通那支還複製到 pages/ffxiv": (lambda f: _step(f["traffic"], _is_copy("traffic")).update(
        {"run": _step(f["traffic"], _is_copy("traffic"))["run"] + "cp pages/shared/app.js pages/ffxiv/app.js\n"}), "exclusive"),
    "FFXIV 那支少了部署": (_drop_step("ffxiv", _is_deploy("ffxiv")), "exclusive"),
    "交通那支少了交通分析": (_drop_step("traffic", lambda s: run_of(s) == TRAFFIC), "exclusive"),
    "交通那支少複製 shared.css": (_replace_run("traffic", _is_copy("traffic"),
                                         "cp pages/shared/shared.css pages/traffic/shared.css", ""), "exclusive"),
    "FFXIV 那支沒有排程": (lambda f: f["ffxiv"][True].pop("schedule"), "formal"),
    "兩支的 cron 不同": (lambda f: f["ffxiv"][True].update({"schedule": [{"cron": "0 1 * * 1"}]}), "formal"),
    "兩支都多一個 cron": (lambda f: [f[c][True]["schedule"].append({"cron": "0 1 * * 1"}) for c in CATEGORIES], "formal"),
    "兩支都拿掉手動觸發": (lambda f: [f[c][True].pop("workflow_dispatch") for c in CATEGORIES], "formal"),
    "兩支的 permissions 不同": (lambda f: f["ffxiv"].update({"permissions": {"contents": "write"}}), "formal"),
    "兩支的 runs-on 不同": (lambda f: the_job(f["ffxiv"]).update({"runs-on": "ubuntu-22.04"}), "formal"),
    "Ping 改了一個字": (_replace_run("traffic", lambda s: s.get("name") == PING, "timeout=10", "timeout=11"), "formal"),
    "FFXIV 少了 Ping": (_drop_step("ffxiv", lambda s: s.get("name") == PING), "formal"),
    "兩支的 main 除了類別還有別的不同": (_set_env(MAIN, "YOUTUBE_API_KEY", None, "ffxiv"), "formal"),
    "讀回驗證除了類別還有別的不同": (_verify_run("traffic", "timeout=15", "timeout=30"), "formal"),
    "兩支都有的步驟順序不同": (_move_step("ffxiv", PING, PREP_STEPS + 2), "formal"),
    "FFXIV 少了 setup-node": (_drop_step("ffxiv", lambda s: s.get("uses", "").startswith("actions/setup-node@")), "formal"),
    "交通的讀回驗證排回熱點分析之前": (_move_next_to("traffic", _is_verify, own_steps("traffic")["週交通熱點分析"]),
                            "verify_place"),
    "交通的讀回驗證排在熱點分析與部署之間": (_move_next_to("traffic", _is_verify, own_steps("traffic")["週交通熱點分析"], 1),
                                "verify_place"),
    "交通的讀回驗證排在部署前一步": (_move_next_to("traffic", _is_verify, _is_deploy("traffic")), "verify_place"),
    "交通那支有兩步讀回驗證": (_copy_step_into("traffic", "traffic", _is_verify), "verify_place"),
    "FFXIV 的讀回驗證排到部署之後": (_move_next_to("ffxiv", _is_verify, _is_deploy("ffxiv"), 1), "verify_place"),
    "FFXIV 的讀回驗證排在複製之後": (_move_next_to("ffxiv", _is_verify, _is_copy("ffxiv"), 1), "verify_place"),
    "FFXIV 的部署排到讀回驗證之前": (_move_next_to("ffxiv", _is_deploy("ffxiv"), _is_verify), "verify_place"),
    "FFXIV 的讀回驗證排在 main 之前": (_move_next_to("ffxiv", _is_verify, runs_main), "verify_place"),
    "交通的熱點分析排到讀回驗證之後": (_move_next_to("traffic", own_steps("traffic")["週交通熱點分析"], _is_verify, 1),
                            "verify_place"),
    "交通的複製排到讀回驗證之後": (_move_next_to("traffic", _is_copy("traffic"), _is_verify, 1), "verify_place"),
    "交通的 main 排到讀回驗證之後": (_move_next_to("traffic", runs_main, _is_verify, 1), "verify_place"),
    "FFXIV 的部署在驗證失敗時也跑": (_set_key(["ffxiv"], _is_deploy("ffxiv"), "if", ALWAYS), "gate"),
    "FFXIV 的複製在驗證失敗時也跑": (_set_key(["ffxiv"], _is_copy("ffxiv"), "if", ALWAYS), "gate"),
    "FFXIV 的部署被關掉": (_set_key(["ffxiv"], _is_deploy("ffxiv"), "if", "${{ false }}"), "gate"),
    "交通的部署被關掉": (_set_key(["traffic"], _is_deploy("traffic"), "if", "${{ false }}"), "gate"),
    "交通的熱點分析被關掉": (_set_key(["traffic"], own_steps("traffic")["週交通熱點分析"], "if", "${{ false }}"), "gate"),
    "兩支的讀回驗證失敗都不算": (_set_key(CATEGORIES, _is_verify, "continue-on-error", True), "gate"),
    "兩支的讀回驗證都被關掉": (_set_key(CATEGORIES, _is_verify, "if", "${{ false }}"), "gate"),
    "兩支的 main 失敗都不算": (_set_key(CATEGORIES, runs_main, "continue-on-error", True), "gate"),
    "兩支的 setup-node 都被關掉": (_set_key(CATEGORIES, _is_setup_node, "if", "${{ false }}"), "gate"),
    "兩支的 job 失敗都不算": (_set_job_key("continue-on-error", True), "gate"),
    "兩支的 job 都被關掉": (_set_job_key("if", "${{ false }}"), "gate"),
    "拿掉 level 的檢查": (lambda f: steps(f["dry"]).pop(PREP_STEPS), "guard"),
    "level 的檢查排在計數後面": (lambda f: steps(f["dry"]).insert(PREP_STEPS + 2, steps(f["dry"]).pop(PREP_STEPS)), "guard"),
    "level 的檢查放行空值": (_guard_run("dry-input|dry-full)", "\"\"|dry-input|dry-full)"), "guard"),
    "level 的檢查不失敗": (_guard_run("exit 1", "exit 0"), "guard"),
    "level 的檢查讀寫死的值": (lambda f: guard_step(f["dry"]).update({"env": {"LEVEL": "dry-full"}}), "guard"),
    "level 的檢查只在失敗後跑": (lambda f: guard_step(f["dry"]).update({"if": "${{ failure() }}"}), "guard"),
    "拿掉 category 的檢查": (lambda f: steps(f["dry"]).pop(PREP_STEPS + 1), "guard"),
    "只剩準備步驟與 level 的檢查": (lambda f: the_job(f["dry"]).update({"steps": steps(f["dry"])[:PREP_STEPS + 1]}), "guard"),
    "兩個檢查對調": (lambda f: steps(f["dry"]).insert(PREP_STEPS, steps(f["dry"]).pop(PREP_STEPS + 1)), "guard"),
    "category 的檢查放行空值": (_guard_run("traffic|ffxiv)", "\"\"|traffic|ffxiv)", 1), "guard"),
    "category 的檢查放行大寫": (_guard_run("traffic|ffxiv)", "traffic|ffxiv|TRAFFIC)", 1), "guard"),
    "category 的檢查不失敗": (_guard_run("exit 1", "exit 0", 1), "guard"),
    "category 的檢查擋下時沒說原因": (_guard_run("echo \"category 的值不認得", "echo \"值不認得", 1), "guard"),
    "category 的檢查讀寫死的值": (lambda f: guard_step(f["dry"], 1).update({"env": {"CATEGORY": "traffic"}}), "guard"),
    "category 的檢查只在失敗後跑": (lambda f: guard_step(f["dry"], 1).update({"if": "${{ failure() }}"}), "guard"),
    "main 少了模型變數": (_set_env(MAIN, "GEMINI_MODEL_NAME", None), "env"),
    "main 的值不同": (_set_env(MAIN, "GEMINI_MODEL_NAME", "${{ vars.GEMINI_MODEL_NAME }}"), "env"),
    "交通分析少了設定路徑": (_set_env(TRAFFIC, "JIEBA_USERDICT_PATH", None), "env"),
    "術語收錄少了 key": (_set_env(AUTO_KB, "GEMINI_API_KEY", None), "env"),
    "多出無關的變數": (_set_env(MAIN, "DEBUG", "1"), "env"),
    "交通那支加了新變數沒跟上": (_formal_gains_var("traffic"), "env"),
    "FFXIV 那支加了新變數沒跟上": (_formal_gains_var("ffxiv"), "env"),
    "交通那支的交通分析變數改了沒跟上": (_set_env(TRAFFIC, "GEMINI_MODEL_DIGEST", "${{ vars.X }}", "traffic"), "env"),
    "不發布的交通分析帶了類別": (_set_env(TRAFFIC, "GARYU_CATEGORY", CATEGORY_EXPR), "env"),
    "計數步驟的 secret 打錯": (lambda f: _step(f["dry"], lambda s: run_of(s).startswith(TAKE))["env"].update(
        {"SUPABASE_URL": "${{ secrets.SUPABASE_URI }}"}), "env"),
    "產物目錄不一致": (_set_env(TRAFFIC, "TRAFFIC_POOL_DIR", "elsewhere"), "env"),
    "術語收錄少了產物目錄": (_set_env(AUTO_KB, "ANALYSIS_OUTPUT_DIR", None), "env"),
    "timeout 不同": (lambda f: the_job(f["dry"]).update({"timeout-minutes": 20}), "job"),
    "timeout 取了較小的": (lambda f: the_job(f["dry"]).update(
        {"timeout-minutes": min(the_job(f[c])["timeout-minutes"] for c in CATEGORIES)}), "job"),
    "FFXIV 的 timeout 變大、不發布沒跟上": (lambda f: the_job(f["ffxiv"]).update(
        {"timeout-minutes": the_job(f["ffxiv"])["timeout-minutes"] + 1}), "job"),
    "environment 不同": (lambda f: the_job(f["dry"]).update({"environment": "staging"}), "job"),
    "交通那支的 environment 不同": (lambda f: the_job(f["traffic"]).update({"environment": "staging"}), "job"),
    "permissions 不同": (lambda f: f["dry"].update({"permissions": {"contents": "write"}}), "job"),
    "術語收錄每級都跑": (lambda f: _step(f["dry"], lambda s: run_of(s) == AUTO_KB).pop("if"), "order"),
    "術語收錄只看級": (lambda f: _step(f["dry"], lambda s: run_of(s) == AUTO_KB).update({"if": DRY_FULL_ONLY}), "order"),
    "術語收錄只看類別": (lambda f: _step(f["dry"], lambda s: run_of(s) == AUTO_KB).update(
        {"if": "${{ inputs.category == 'ffxiv' }}"}), "order"),
    "交通分析每類都跑": (lambda f: _step(f["dry"], lambda s: run_of(s) == TRAFFIC).pop("if"), "order"),
    "交通分析的條件寫成 ffxiv": (lambda f: _step(f["dry"], lambda s: run_of(s) == TRAFFIC).update(
        {"if": "${{ inputs.category == 'ffxiv' }}"}), "order"),
    "比對在失敗後不跑": (lambda f: _step(f["dry"], lambda s: run_of(s).startswith(COMPARE)).pop("if"), "order"),
    "結束的計數在失敗後不跑": (lambda f: [s for s in steps(f["dry"]) if run_of(s).startswith(TAKE)][1].pop("if"), "order"),
    "main 在失敗後也跑": (lambda f: _step(f["dry"], lambda s: run_of(s) == MAIN).update({"if": ALWAYS}), "order"),
    "main 只在 traffic 跑": (lambda f: _step(f["dry"], lambda s: run_of(s) == MAIN).update({"if": TRAFFIC_ONLY}), "order"),
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
    "FFXIV 那支的 ffxiv-pool 改了沒跟上": (_with("ffxiv-pool", lambda f, n: _upload(f, n, "ffxiv")["with"].update(
        {"if-no-files-found": "error"})), "upload"),
    "上傳排在比對前面": (lambda f: steps(f["dry"]).insert(PREP_STEPS + len(GUARDS) + 1, steps(f["dry"]).pop(
        steps(f["dry"]).index(_upload(f, "traffic-pool")))), "upload"),
}

CHECKS = {
    "prep": lambda f, t: prep_problems(f),
    "trigger": lambda f, t: trigger_problems(f["dry"], f["autokb"]),
    "forbidden": lambda f, t: forbidden_problems(f["dry"], t),
    "level": lambda f, t: level_problems(f["dry"]),
    "category": lambda f, t: category_problems(f),
    "main": lambda f, t: main_problems(f["all"]),
    "gone": lambda f, t: gone_problems(f["all"]),
    "autokb": lambda f, t: autokb_problems(f),
    "verify": lambda f, t: verify_problems(f),
    "exclusive": lambda f, t: exclusive_problems(f),
    "formal": lambda f, t: formal_problems(f),
    "verify_place": lambda f, t: verify_place_problems(f),
    "gate": lambda f, t: gate_problems(f),
    "guard": lambda f, t: guard_problems(f["dry"]),
    "env": lambda f, t: env_problems(f),
    "job": lambda f, t: job_problems(f),
    "order": lambda f, t: order_problems(f["dry"]),
    "upload": lambda f, t: upload_problems(f),
}


@pytest.mark.parametrize("label", list(MUTATIONS))
def test_a_broken_copy_is_caught(files, label):
    mutate, check = MUTATIONS[label]
    broken = copy.deepcopy(files)
    mutate(broken)
    text = yaml.safe_dump(broken["dry"], allow_unicode=True)
    assert CHECKS[check](broken, text), f"改壞「{label}」之後 {check} 沒有找到問題"
