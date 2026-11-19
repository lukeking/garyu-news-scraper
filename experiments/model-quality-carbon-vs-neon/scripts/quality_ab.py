"""neon 對 carbon 的三軸評比（BACKLOG GNS-20261019-1vk）：上一輪凍結的 4 份事故類輸入與 carbon@65536 存檔當對照，只生成 neon，2.5-pro 盲評對調。
子命令 baseline | run | judge | report，後面的數字＝這次最多幾次 API 呼叫；不讀資料庫，只寫本目錄 data/（QAB_OUT 可改到別處）。
做法、判準與費用見同目錄的 README.md。"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.environ.get("QAB_OUT") or os.path.join(HERE, "data")
PREV = "experiments/model-quality-3p8flash-vs-carbon/data"
sys.path[:0] = [REPO, os.path.join(REPO, "scripts")]

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(REPO, ".env"), override=True)  # analyzer 在 import 時讀環境，先載入再 import
import logging  # noqa: E402
logging.basicConfig(level=logging.ERROR)
logging.getLogger("src.analyzer").setLevel(logging.WARNING)  # 重試、逾時、MAX_TOKENS 要看得到

import src.analyzer as az  # noqa: E402
import replay_report_review as rr  # noqa: E402

REPORTS = ["2026-08-03｜機車事故 · 中時", "2026-09-07｜機車事故 · TVBS", "2026-09-21｜行人事故 · 行人", "2026-10-26｜機車事故 · 機車"]
BASELINE, CHALLENGER, JUDGE = "gemini-4-carbon", "gemini-4-neon", "gemini-2.5-pro"
BASELINE_RUN = "q_run_gemini-4-carbon_max65536.json"  # 上一輪 11-12 的存檔，這一輪不重生成
CHALLENGER_RUN = "q_run_gemini-4-neon.json"
JUDGE_FILE = "q_judge.json"
N_RUNS = 2
MAX_OUT, TIMEOUT = 65536, 600  # 與 carbon 存檔那批送出的值相同；neon 經三軸路徑自己的環境變數送
MAX_RETRIES = "2"  # prod 預設 8；逾時被放棄的嘗試照樣計費，這裡壓低
USD_CAP = float(os.environ.get("QAB_USD_CAP", "2.5"))  # 記到的花費到這個數就不再呼叫
WEEKS_PER_MONTH = 4.35
PRICING = {  # USD / 1M tok，output 含 thinking（aistudio.google.com/docs/pricing，2026-11-19 抓取）
    "gemini-4-carbon": {"now": (2.00, 10.00), "later": (4.00, 20.00)},  # 優惠到 2026-11-30
    "gemini-4-neon": {"now": (3.00, 15.00), "later": (3.00, 15.00)},    # 定價頁沒有列改價
    "gemini-2.5-pro": {"now": (1.25, 10.00), "later": (1.25, 10.00)},   # prompt <= 200k；2026-12-01 起轉給 3.8-flash
}

_cap = {}
_budget = {"left": None}
_orig_post = az.requests.post


def _cap_post(*a, **k):
    _cap["attempts"] = _cap.get("attempts", 0) + 1
    _cap["sent"] = {"maxOutputTokens": ((k.get("json") or {}).get("generationConfig") or {}).get("maxOutputTokens"),
                    "timeout": k.get("timeout")}
    try:
        resp = _orig_post(*a, **k)
    except Exception:
        _cap["failed"] = _cap.get("failed", 0) + 1  # 逾時或斷線：這次嘗試可能已經計費，usage 拿不到
        raise
    try:
        j = resp.json()
        _cap["usage"] = j.get("usageMetadata") or _cap.get("usage")
        _cap["modelVersion"] = j.get("modelVersion") or _cap.get("modelVersion")
        _cap["finishReason"] = (j.get("candidates") or [{}])[0].get("finishReason") or _cap.get("finishReason")
    except Exception:
        pass
    return resp


az.requests.post = _cap_post


def _reset():
    _cap.update({"usage": None, "modelVersion": None, "finishReason": None, "sent": None, "attempts": 0, "failed": 0})


def _meta(t0):
    return {"seconds": round(time.time() - t0, 1), "usage": _cap.get("usage") or {}, "finishReason": _cap.get("finishReason"),
            "sent": _cap.get("sent"), "attempts": _cap.get("attempts"), "failed_attempts": _cap.get("failed")}


def _check_version(requested):
    got = _cap.get("modelVersion")
    if not got or not got.startswith(requested):
        sys.exit(f"STOP modelVersion mismatch: requested {requested}, response {got!r}")
    return got


def _p(name):
    return os.path.join(OUT, name)


def _load(name, default=None):
    if default is not None and not os.path.exists(_p(name)):
        return default
    with open(_p(name), encoding="utf-8") as f:
        return json.load(f)


def _dump(name, obj):
    os.makedirs(OUT, exist_ok=True)
    with open(_p(name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def _usd(model, usages, phase="now"):
    p_in, p_out = PRICING[model][phase]
    return sum((u.get("promptTokenCount") or 0) / 1e6 * p_in +
               ((u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0)) / 1e6 * p_out
               for u in usages)


def _spent():
    gen = [x.get("usage") or {} for runs in _load(CHALLENGER_RUN, {"per_report": {}})["per_report"].values() for x in runs]
    jud = [x.get("usage") or {} for x in _load(JUDGE_FILE, {"results": []})["results"]]
    return _usd(CHALLENGER, gen) + _usd(JUDGE, jud)


def _spend():
    if _budget["left"] is not None and _budget["left"] <= 0:
        print("LIMIT 這次的呼叫次數用完，停在這裡（重跑會接著做）", flush=True)
        return False
    spent = _spent()
    if spent >= USD_CAP:
        print(f"LIMIT 記到的花費 ${spent:.2f} 到了上限 ${USD_CAP:.2f}，停在這裡", flush=True)
        return False
    if _budget["left"] is not None:
        _budget["left"] -= 1
    return True


def baseline():
    """從上一輪的 data/ 抄出這一輪用的 4 份輸入與 carbon@65536 的存檔；不呼叫 API。"""
    def prev(name):
        with open(os.path.join(REPO, PREV, name), encoding="utf-8") as f:
            return json.load(f)
    p_in, p_run = prev("inputs.json"), prev(BASELINE_RUN)
    _dump("inputs.json", {"frozen_at": p_in["frozen_at"], "copied_from": f"{PREV}/inputs.json",
                          "reports": {k: p_in["reports"][k] for k in REPORTS}})
    _dump(BASELINE_RUN, {"model": p_run["model"], "copied_from": f"{PREV}/{BASELINE_RUN}",
                         "per_report": {k: p_run["per_report"][k] for k in REPORTS}})
    for k in REPORTS:
        runs = p_run["per_report"][k]
        if len(runs) != N_RUNS or any("error" in x or x.get("finishReason") != "STOP" for x in runs):
            sys.exit(f"STOP {k}：carbon 存檔不是 {N_RUNS} 次都成功，不能當對照")
        print(f"BASELINE {k} runs={len(runs)} sent={runs[0].get('sent')} {[x.get('modelVersion') for x in runs]}", flush=True)


def run():
    reports = _load("inputs.json")["reports"]
    base = _load(BASELINE_RUN)["per_report"]
    out = _load(CHALLENGER_RUN, {"model": CHALLENGER, "per_report": {}})
    os.environ.update({"GEMINI_MODEL_HOT_TOPIC": CHALLENGER, "GEMINI_HOT_TOPIC_MAX_OUTPUT_TOKENS": str(MAX_OUT),
                       "GEMINI_HOT_TOPIC_TIMEOUT_SECONDS": str(TIMEOUT), "GEMINI_MAX_RETRIES": MAX_RETRIES})
    for key, r in reports.items():
        runs = out["per_report"].setdefault(key, [])
        while len(runs) < N_RUNS:
            if not _spend():
                return
            _reset()
            t0 = time.time()
            try:
                regen, ordered, _ = rr.regenerate(r["template"], r["articles"], r["topic"], r["week"])
                if regen["input_text"] != base[key][0]["input_text"]:
                    sys.exit(f"STOP {key}：neon 看到的清單與 carbon 存檔的不同")
                checks = rr.run_checks(regen["text"], r["template"], ordered, rr.current_chars(r["template"]))
                rec = {"text": regen["text"], "input_text": regen["input_text"], "sources": regen["sources"],
                       "title_only_ids": regen["title_only_ids"], "counts": checks["counts"], "hits": checks["hits"]}
            except rr.ReplayError as e:
                rec = {"error": str(e)}
            mv = _cap.get("modelVersion")
            if mv is not None or "error" not in rec:  # 有文字卻沒有 modelVersion 也停：無法確認是哪個模型寫的
                mv = _check_version(CHALLENGER)
            rec.update(_meta(t0), modelVersion=mv)
            runs.append(rec)
            _dump(CHALLENGER_RUN, out)
            um = rec["usage"]
            print(f"GEN {CHALLENGER} ({mv}) {key} run{len(runs)}/{N_RUNS} finish={rec['finishReason']} "
                  f"{'ERROR ' + rec['error'] if 'error' in rec else str(len(rec['text'])) + 'c'} {rec['seconds']}s "
                  f"in={um.get('promptTokenCount')} out={um.get('candidatesTokenCount')} think={um.get('thoughtsTokenCount')} "
                  f"attempts={rec['attempts']} failed={rec['failed_attempts']} spent=${_spent():.3f}", flush=True)
            time.sleep(2.0)
    print(f"SAVED {_p(CHALLENGER_RUN)}", flush=True)


AXES = ["格式遵循", "文本依據", "分類與因果解構", "觸發制紀律", "轉譯紀律"]
RUBRIC = """- 格式遵循：三段標題與各欄位齊全、未合併換行；清單沒有事故報導時，第一段只寫「本批無事故報導，不適用」且不輸出五個欄位；有事故報導時，交織度分布六類加總等於清單篇數。
- 文本依據：每項結論標註 Article ID，且與該篇來源相符（非杜撰）；摘要寫「（僅標題）」的報導引用時標「僅標題」，不補寫標題沒有的主詞、範圍或日期；傷亡人數、傷勢與行向照來源寫。
- 分類與因果解構：每篇的六類歸類照判定規則——歸 [工程主導]／[雙因交織] 須寫出來源寫到的工程條件怎麼放大人因動作；說不出放大機制時歸 [人因主導]（有直接證據）或 [工程未見放大]；來源沒寫工程條件歸 [工程資料未載]。人因、工程變數照來源寫，來源沒寫的填「來源未載」，值得查的寫成「待查證：…？」，不斷言「未落實」「缺乏」。
- 觸發制紀律：政經（第二段）、官方論述偏誤（第三段）只在來源有明確文本時啟動，否則正確填不適用；啟動時只列來源明文的制度做法與有發現的偏誤，不寫機關的動機或「迴避」。
- 轉譯紀律：引用外國原則時講機制、用原則本身的變數（速度與質量）、同質性的兩種解法都交代、撞詞切割；結論不得被讀成「車種分流是對的」。"""
JUDGE_SYS = ("你是嚴格中立的交通安全結構性分析報告評審。"
             "只依據提供的來源清單與評分準則，對兩份報告（A、B）逐軸評分。禁止偏袒任何一方，不知道兩份報告由哪個模型產生。"
             "務必只回傳一個 JSON 物件，不要任何其他文字。")
JUDGE_TMPL = """主題：{label}

【來源清單（兩份報告的生成輸入，逐字相同；評分時用來查核引證是否屬實）】
{articles}

【評分準則，每軸 0-5 分】
{rubric}

【報告 A】
{A}

【報告 B】
{B}

只回傳 JSON：{{"A":{{{axes}}},"B":{{...}},"winner":"A"|"B"|"tie","reason":"一句話"}}"""


def judge_prompt(label, articles, a_text, b_text):
    axes = ",".join(f'"{ax}":0' for ax in AXES)
    return JUDGE_TMPL.format(label=label, articles=articles, rubric=RUBRIC, A=a_text, B=b_text, axes=axes)


def _parse_json(raw):
    if not raw:
        return None
    s = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", s, re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None


def _valid(parsed):
    if not isinstance(parsed, dict) or parsed.get("winner") not in ("A", "B", "tie"):
        return False
    return all(isinstance(parsed.get(s), dict) and all(isinstance(parsed[s].get(ax), (int, float)) for ax in AXES)
               for s in ("A", "B"))


def judge():
    reports = _load("inputs.json")["reports"]
    runs = {BASELINE: _load(BASELINE_RUN)["per_report"], CHALLENGER: _load(CHALLENGER_RUN)["per_report"]}
    results = _load(JUDGE_FILE, {"results": []})["results"]
    seen = {(x["report"], x["run"], x["order"]) for x in results}
    api_key = az._get_api_key()
    os.environ["GEMINI_MAX_RETRIES"] = MAX_RETRIES
    for key, r in reports.items():
        for k in range(N_RUNS):
            if len(runs[CHALLENGER].get(key, [])) <= k:
                print(f"SKIP {key} run{k + 1}：neon 還沒生成", flush=True)
                continue
            base, chal = runs[BASELINE][key][k], runs[CHALLENGER][key][k]
            if "error" in base or "error" in chal:
                print(f"SKIP {key} run{k + 1}：有一方生成失敗", flush=True)
                continue
            if base["input_text"] != chal["input_text"]:
                sys.exit(f"STOP {key} run{k + 1}：兩個模型看到的清單不同")
            for order in ("base_first", "chal_first"):
                if (key, k + 1, order) in seen:
                    continue
                if not _spend():
                    return
                a_m, b_m = (BASELINE, CHALLENGER) if order == "base_first" else (CHALLENGER, BASELINE)
                prompt = judge_prompt(r["topic"], base["input_text"], runs[a_m][key][k]["text"], runs[b_m][key][k]["text"])
                _reset()
                t0 = time.time()
                raw = az._call_gemini(prompt, api_key, system_prompt=JUDGE_SYS, model=JUDGE, max_output_tokens=MAX_OUT, timeout=TIMEOUT)
                mv = _check_version(JUDGE)
                parsed = _parse_json(raw)
                ok = _valid(parsed)
                rec = {"report": key, "run": k + 1, "order": order, "A_model": a_m, "B_model": b_m, "ok": ok, "raw": raw,
                       "modelVersion": mv, **_meta(t0)}
                if ok:
                    w = parsed["winner"]
                    rec.update({"scores": {a_m: parsed["A"], b_m: parsed["B"]},
                                "winner": a_m if w == "A" else b_m if w == "B" else "tie", "reason": parsed.get("reason", "")})
                results.append(rec)
                _dump(JUDGE_FILE, {"judge_model": JUDGE, "results": results})
                print(f"JUDGE {key} run{k + 1} {order} ok={ok} winner={rec.get('winner')} {rec['seconds']}s "
                      f"finish={rec['finishReason']} attempts={rec['attempts']} failed={rec['failed_attempts']} "
                      f"spent=${_spent():.3f}", flush=True)
                time.sleep(2.0)
    print(f"SAVED {_p(JUDGE_FILE)}", flush=True)


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def _counts(rec):
    """兩個模型都用現在的 check_report() 重算：carbon 存檔裡的計數是 11-12 的檢查算的。"""
    hits = rr.check_report(rec["text"], template="hot", sources=rec["sources"], title_only_ids=rec["title_only_ids"])
    return {name: len(found) for name, found in hits.items()}


def report():
    reports = _load("inputs.json")["reports"]
    runs = {BASELINE: _load(BASELINE_RUN)["per_report"], CHALLENGER: _load(CHALLENGER_RUN, {"per_report": {}})["per_report"]}
    jd = _load(JUDGE_FILE, {"results": []})["results"]
    models = (BASELINE, CHALLENGER)
    counted = {(m, key, i): ({} if "error" in rec else _counts(rec))
               for m in models for key in reports for i, rec in enumerate(runs[m].get(key, []), 1)}
    names = list(dict.fromkeys(name for counts in counted.values() for name in counts))  # 欄名照檢查實際回的，不寫死
    L = [f"# 三軸品質 A/B：`{BASELINE}`（11-12 存檔）對 `{CHALLENGER}`", "",
         f"{len(reports)} 份事故類三軸的凍結輸入 · 現行指令 · temp 0.2 · 每份 {N_RUNS} 次 · 兩邊都是 maxOutputTokens {MAX_OUT}、timeout {TIMEOUT} 秒 · "
         f"judge=`{JUDGE}`（非參賽、盲評、位置對調）", "",
         "## Gate：check_report() 逐次計數（兩邊都用現在的檢查重算；未經逐條判定，`date_unlabeled` 已知誤判多）", "",
         "| 報告 | 模型 | run | " + " | ".join(names) + " | finishReason | 錯誤 |", "|---|---|---|" + "---|" * (len(names) + 2)]
    totals = {m: {c: 0 for c in names} for m in models}
    for key in reports:
        for m in models:
            for i, rec in enumerate(runs[m].get(key, []), 1):
                counts = counted[(m, key, i)]
                for c in names:
                    totals[m][c] += counts.get(c, 0)
                cells = " | ".join("—" if "error" in rec else str(counts.get(c, 0)) for c in names)
                L.append(f"| {key} | {m} | {i} | {cells} | {rec.get('finishReason')} | {rec.get('error', '')} |")
    for m in models:
        L.append(f"| **合計** | {m} | | " + " | ".join(str(totals[m][c]) for c in names) + " | | |")
    rs = [r for r in jd if r.get("ok")]
    wins = {m: sum(1 for r in rs if r["winner"] == m) for m in (*models, "tie")}
    L += ["", "## 盲評", "", f"裁決 {len(jd)} 次，無法解析 {len(jd) - len(rs)} 次。", "", "| 勝方 | 次數 | 佔比 |", "|---|---|---|"]
    L += [f"| {m} | {wins[m]} | {wins[m] / max(1, len(rs)) * 100:.0f}% |" for m in (*models, "tie")]
    by_pair = {}
    for r in rs:
        by_pair.setdefault((r["report"], r["run"]), {})[r["order"]] = r["winner"]
    both = [v for v in by_pair.values() if len(v) == 2]
    L += ["", f"位置一致：兩個位置都有效的 {len(both)} 對裡，{sum(1 for v in both if v['base_first'] == v['chal_first'])} 對判同一個勝方；"
          f"排在 A 的那份勝 {sum(1 for r in rs if r['winner'] == r['A_model'])} 次、排在 B 的勝 {sum(1 for r in rs if r['winner'] == r['B_model'])} 次。",
          "", "| 報告 | carbon 勝 | neon 勝 | 平手 |", "|---|---|---|---|"]
    for key in reports:
        kr = [r for r in rs if r["report"] == key]
        L.append(f"| {key} | " + " | ".join(str(sum(1 for r in kr if r["winner"] == m)) for m in (*models, "tie")) + " |")
    L += ["", f"| 軸 | `{BASELINE}` | `{CHALLENGER}` | 差（neon − carbon） |", "|---|---|---|---|"]
    for ax in AXES:
        mb, mc = (mean([r["scores"][m][ax] for r in rs]) for m in models)
        L.append(f"| {ax} | {mb:.2f} | {mc:.2f} | {mc - mb:+.2f} |")
    L += ["", "## 成本、延遲與長度（實測；carbon 的數字來自 11-12 的存檔）", "",
          "| model | 生成 | 失敗 | MAX_TOKENS | 超過 120 秒 | 最長秒數 | 嘗試／失敗的嘗試 | modelVersion | $/份 現價 | $/份 12-01 起 | thinking 最小～最大 | 輸出＋thinking 最大 | 均秒數 | 均字數 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    per = {}
    for m in models:
        recs = [x for key in reports for x in runs[m].get(key, [])]
        ok = [x for x in recs if "error" not in x]
        us = [x["usage"] for x in ok]
        per[m] = {ph: _usd(m, us, ph) / max(1, len(us)) for ph in ("now", "later")}
        think = [u.get("thoughtsTokenCount") or 0 for u in us]
        total = [(u.get("candidatesTokenCount") or 0) + t for u, t in zip(us, think)]
        tries ="—" if m == BASELINE else f"{sum(x.get('attempts') or 0 for x in recs)}／{sum(x.get('failed_attempts') or 0 for x in recs)}"
        L.append(f"| `{m}` | {len(recs)} | {len(recs) - len(ok)} | {sum(1 for x in recs if x.get('finishReason') == 'MAX_TOKENS')} | "
                 f"{sum(1 for x in recs if x['seconds'] > 120)} | {max([x['seconds'] for x in recs], default=0)} | {tries} | "
                 f"{', '.join(sorted({x.get('modelVersion') or '—' for x in recs}))} | ${per[m]['now']:.4f} | ${per[m]['later']:.4f} | "
                 f"{min(think, default=0)}～{max(think, default=0)} | {max(total, default=0)}（上限的 {max(total, default=0) / MAX_OUT * 100:.0f}%） | "
                 f"{mean([x['seconds'] for x in ok]):.1f} | {mean([len(x['text']) for x in ok]):.0f} |")
    gen_usd = _usd(CHALLENGER, [x.get("usage") or {} for key in reports for x in runs[CHALLENGER].get(key, [])])
    jud_usd = _usd(JUDGE, [r.get("usage") or {} for r in jd])
    L += ["", f"這一輪記到的花費：neon 生成 ${gen_usd:.4f}＋裁判 {len(jd)} 次 ${jud_usd:.4f}＝${gen_usd + jud_usd:.4f}"
          f"（裁判的嘗試 {sum(r.get('attempts') or 0 for r in jd)} 次、失敗 {sum(r.get('failed_attempts') or 0 for r in jd)} 次；失敗的嘗試沒有 usage，不在這個數字裡）。",
          "", "三軸每週 1～2 次時每月的生成成本（12-01 起的價格）：" +
          "；".join(f"`{m}` ${per[m]['later'] * WEEKS_PER_MONTH:.2f}～${per[m]['later'] * 2 * WEEKS_PER_MONTH:.2f}" for m in models) + "。",
          "", "## 逐份並排（各取 run1）＋ judge 理由", ""]
    for key, r in reports.items():
        L += [f"### {key}（{len(r['articles'])} 篇）", ""]
        for m in models:
            rec = (runs[m].get(key) or [{"error": "還沒生成"}])[0]
            L += [f"#### ── {m}（run1）──", "", rec.get("text") or f"（失敗：{rec.get('error')}）", ""]
        L.append("**judge 理由：**")
        L += [f"- run{x['run']} [{x['order']}] 勝：{x['winner']} — {x.get('reason', '')}" for x in rs if x["report"] == key]
        L.append("")
    with open(_p("q_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"REPORT {_p('q_report.md')}", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    _budget["left"] = int(sys.argv[2]) if len(sys.argv) > 2 else None
    steps = {"baseline": baseline, "run": run, "judge": judge, "report": report}
    if cmd not in steps:
        sys.exit(__doc__)
    steps[cmd]()
    print("DONE", flush=True)
