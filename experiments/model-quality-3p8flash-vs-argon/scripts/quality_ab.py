"""
Quality A/B with blind judge, two pairs on PR #90's frozen snapshot:
  pair 1  gemini-3.7-flash (INCUMBENT, PR #90's saved outputs) vs gemini-3.8-flash
  pair 2  gemini-3.8-flash (INCUMBENT, what prod actually runs) vs gemini-4-argon
3.7 cannot be called any more: since 2026-10-08 the API routes it to 3.8, so a fresh
3.7 run would be 3.8 judged against itself. Its PR #90 outputs stand in;
analyze_hot_topic sends byte-identical prompts on this snapshot at 770ed2a and at
the commit this script was written on (checked 2026-10-19).

Method otherwise identical to PR #90 (route A): same prompt (analyze_hot_topic),
temp 0.2, N runs per model per bucket, gemini-2.5-pro judges BLIND and
POSITION-SWAPPED on the prompt's rubric axes. The cross-family check of pair 2 is
done out of band (Claude in-session), as in PR #90.

Every response's modelVersion is recorded and must start with the requested model
id; a mismatch stops the run (fail closed). Silent routing is how 3.8 replaced 3.7.

ffxiv_freeze / ffxiv_cost measure analyze_article token cost per model on a small
live FFXIV sample: cost only, no quality judging (Luke 2026-10-19).

Reads: PR #90 snapshot and 3.7 runs (files); ffxiv_freeze fetches the FFXIV sources
over HTTP; ffxiv_cost reads the prod knowledge_base table (select only, through
load_knowledge_base). Writes local files only.
Subcommands: run | judge | ffxiv_freeze | ffxiv_cost | report | all

Provenance: adapted from experiments/model-quality-3p6flash-vs-3p7flash (PR #90).
"""
import os, re, sys, json, time
from datetime import datetime, timezone

REPO = "/home/luke/Projects/garyu-news-scraper"
sys.path.insert(0, REPO)
PREV = os.path.join(REPO, "experiments/model-quality-3p6flash-vs-3p7flash/data")
OUT = os.path.join(REPO, "experiments/model-quality-3p8flash-vs-argon/data")
os.makedirs(OUT, exist_ok=True)
SNAP = os.path.join(PREV, "q_snapshot.json")
FFXIV_SNAP = os.path.join(OUT, "ffxiv_sample.json")
FFXIV_COST = os.path.join(OUT, "ffxiv_cost.json")

from dotenv import load_dotenv
load_dotenv(os.path.join(REPO, ".env"), override=True)
import logging; logging.basicConfig(level=logging.ERROR)

import src.analyzer as az
from src.analyzer import analyze_hot_topic

SAVED = {"gemini-3.7-flash": os.path.join(PREV, "q_run_gemini-3_7-flash.json")}  # read-only
RUN_MODELS = ["gemini-3.8-flash", "gemini-4-argon"]
PAIRS = [("gemini-3.7-flash", "gemini-3.8-flash"),   # (incumbent, challenger)
         ("gemini-3.8-flash", "gemini-4-argon")]
JUDGE = "gemini-2.5-pro"    # non-contestant, cross-generation; same judge as PR #90
N_RUNS = 3
FFXIV_SAMPLE = 5
# Generation calls per week, counted in the 2026-09-21..10-19 weekly logs (5 runs) and the
# last 3 auto-kb logs: hot topic 1-2 + digest 1, FFXIV analyze_article 20, auto-KB 0.
WEEKLY_CALLS = {"hot_or_digest": 3, "ffxiv_article": 20}
WEEKS_PER_MONTH = 4.35
# USD / 1M tok, standard paid, output includes thinking (ai.google.dev/gemini-api/docs/pricing,
# fetched 2026-10-19). "now" = introductory rate, "later" = after it ends.
PRICING = {
    "gemini-3.7-flash": {"now": (1.50, 7.50), "later": (1.50, 7.50)},    # PR #90's rate; no longer listed
    "gemini-3.8-flash": {"now": (0.75, 3.75), "later": (1.50, 7.50)},    # intro ends 2026-12-31
    "gemini-4-argon":   {"now": (2.00, 10.00), "later": (4.00, 20.00)},  # intro ends 2026-11-30
    "gemini-2.5-pro":   {"now": (1.25, 10.00), "later": (1.25, 10.00)},  # prompts <= 200k
}
AXES = ["格式遵循", "文本依據", "因果解構深度", "觸發制紀律", "轉譯紀律"]

_cap = {}
_orig_post = az.requests.post
def _cap_post(*a, **k):
    resp = _orig_post(*a, **k)
    try:
        j = resp.json()
        if j.get("usageMetadata"):
            _cap["usage"] = j["usageMetadata"]
        if j.get("modelVersion"):
            _cap["modelVersion"] = j["modelVersion"]
    except Exception:
        pass
    return resp
az.requests.post = _cap_post


def _reset():
    _cap["usage"] = None; _cap["modelVersion"] = None

def _check_version(requested):
    got = _cap.get("modelVersion")
    if not got or not got.startswith(requested):
        sys.exit(f"STOP modelVersion mismatch: requested {requested}, response {got!r}")
    return got


def _run_path(model):
    return SAVED.get(model) or os.path.join(OUT, f"q_run_{model.replace('.', '_')}.json")

def _load_runs(model):
    return json.load(open(_run_path(model)))["per_bucket"]


REQ_HEAD = ["### 一、", "### 二、", "### 三、"]
REQ_FIELD = ["交織度分布", "代表個案", "人因變數", "工程變數", "交織說明", "觸發條件", "審查結果"]
def mech(t):
    return {"headers": sum(1 for h in REQ_HEAD if h in t), "fields": sum(1 for f in REQ_FIELD if f in t),
            "citations": len(re.findall(r"\[\d+\]", t)), "car": len(re.findall(r"車種分流", t)),
            "na": len(re.findall(r"不適用", t)), "chars": len(t)}


def run():
    snap = json.load(open(SNAP)); ws = snap["week_start"]
    for model in RUN_MODELS:
        path = _run_path(model)
        out = {"model": model, "per_bucket": {}}
        for b in snap["buckets"]:
            runs = out["per_bucket"].setdefault(b["key"], [])
            for k in range(N_RUNS):
                az.GEMINI_MODEL = model; _reset()
                t0 = time.time()
                rep, _ = analyze_hot_topic(b["articles"], b["label"], ws)
                mv = _check_version(model)
                um = _cap.get("usage") or {}
                runs.append({"report": rep, "seconds": round(time.time() - t0, 1), "usage": um,
                             "modelVersion": mv, "checks": mech(rep) if rep else None})
                json.dump(out, open(path, "w"), ensure_ascii=False, indent=2)
                print(f"GEN {model} ({mv}) {b['key']} run{k+1}/{N_RUNS} "
                      f"{len(rep)}c {round(time.time()-t0,1)}s in={um.get('promptTokenCount')} "
                      f"out={um.get('candidatesTokenCount')} think={um.get('thoughtsTokenCount')}", flush=True)
                time.sleep(2.0)
        print(f"SAVED {path}", flush=True)


JUDGE_SYS = ("你是嚴格中立的交通分析報告評審。只依據提供的來源文章與評分準則，對兩份報告"
             "（A、B）逐軸評分。禁止偏袒任何一方，不知道兩份報告由哪個模型產生。"
             "務必只回傳一個 JSON 物件，不要任何其他文字。")
JUDGE_TMPL = """主題：{label}

【來源文章（評分時用來查核「文本依據」是否屬實）】
{articles}

【評分準則，每軸 0-5 分】
- 格式遵循：三段結構與各欄位是否齊全、未合併換行。
- 文本依據：每項結論是否標註 Article ID [n]，且該引證與來源文章相符（非杜撰）。
- 因果解構深度：工程/人因/交織分析是否具體（對照日本30/荷蘭同質性等），有無反事實推理，非空泛。
- 觸發制紀律：政經(§二)、官方統計偏誤(§三)是否「嚴格觸發」——有明確文本才啟動，否則正確填不適用；不可過度觸發或臆測。
- 轉譯紀律：引用外國原則時是否講機制/用原則本身變數/多解法交代/撞詞切割，結論不得被讀成「車種分流是對的」。

【報告 A】
{A}

【報告 B】
{B}

只回傳 JSON：{{"A":{{"格式遵循":0,"文本依據":0,"因果解構深度":0,"觸發制紀律":0,"轉譯紀律":0}},"B":{{...}},"winner":"A"|"B"|"tie","reason":"一句話"}}"""

def _articles_block(inputs):
    return "\n".join(f"[{i}] {a['title']}｜{a['summary']}" for i, a in enumerate(inputs, 1))

def _parse_json(raw):
    if not raw: return None
    s = raw.strip()
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", s, re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None

def judge():
    snap = json.load(open(SNAP))
    runs = {m: _load_runs(m) for p in PAIRS for m in p}
    api_key = az._get_api_key(); az.GEMINI_MODEL = JUDGE
    path = os.path.join(OUT, "q_judge.json")
    results = []
    for m_inc, m_chal in PAIRS:
        pair = f"{m_inc} vs {m_chal}"
        for b in snap["buckets"]:
            arts_block = _articles_block(b["inputs"])
            for k in range(N_RUNS):
                r_inc = runs[m_inc][b["key"]][k]["report"]
                r_chal = runs[m_chal][b["key"]][k]["report"]
                if not r_inc or not r_chal:
                    continue
                for order in ("inc_first", "chal_first"):
                    if order == "inc_first":
                        A_model, B_model, A_txt, B_txt = m_inc, m_chal, r_inc, r_chal
                    else:
                        A_model, B_model, A_txt, B_txt = m_chal, m_inc, r_chal, r_inc
                    prompt = JUDGE_TMPL.format(label=b["label"], articles=arts_block, A=A_txt, B=B_txt)
                    _reset()
                    raw = az._call_gemini(prompt, api_key, system_prompt=JUDGE_SYS)
                    mv = _check_version(JUDGE)
                    parsed = _parse_json(raw)
                    ok = bool(parsed and "A" in parsed and "B" in parsed)
                    # de-swap: map A/B back to model
                    rec = {"pair": pair, "bucket": b["key"], "run": k + 1, "order": order,
                           "A_model": A_model, "B_model": B_model, "ok": ok, "raw": raw,
                           "modelVersion": mv, "usage": _cap.get("usage") or {}}
                    if ok:
                        w = parsed.get("winner", "tie")
                        rec.update({"scores": {A_model: parsed["A"], B_model: parsed["B"]},
                                    "winner": A_model if w == "A" else B_model if w == "B" else "tie",
                                    "reason": parsed.get("reason", "")})
                    results.append(rec)
                    json.dump({"judge_model": JUDGE, "results": results},
                              open(path, "w"), ensure_ascii=False, indent=2)
                    print(f"JUDGE [{pair}] {b['key']} run{k+1} {order} ok={ok} "
                          f"winner={rec.get('winner')}", flush=True)
                    time.sleep(2.0)
    print(f"SAVED {path}", flush=True)


def ffxiv_freeze():
    from src.collector import load_ffxiv_sources, collect_sources
    from src.filter import freshness_filter, filter_and_deduplicate, game_deduplicate
    from src.pipeline_config import load_pipeline_config
    raw = collect_sources(load_ffxiv_sources())
    # FFXIVCategory.filter's chain minus the Supabase fingerprint read; an empty set is
    # that function's own Supabase-failure path.
    picked = game_deduplicate(filter_and_deduplicate(freshness_filter(raw, set())),
                              load_pipeline_config())
    snap = {"frozen_at": datetime.now(timezone.utc).isoformat(), "n_collected": len(raw),
            "n_selected": len(picked), "articles": picked[:FFXIV_SAMPLE]}
    json.dump(snap, open(FFXIV_SNAP, "w"), ensure_ascii=False, indent=2, default=str)
    for a in snap["articles"]:
        print(f"frozen {a.get('source')}: {a.get('title', '')[:60]}")


def ffxiv_cost():
    s = json.load(open(FFXIV_SNAP)); api_key = az._get_api_key()
    out = {}
    for model in RUN_MODELS:
        rows = out.setdefault(model, [])
        for a in s["articles"]:
            az.GEMINI_MODEL = model; _reset()
            t0 = time.time()
            res = az.analyze_article(dict(a), api_key)
            mv = _check_version(model)
            um = _cap.get("usage") or {}
            ok = (res.get("analysis") or {}).get("summary") != "（分析失敗）"
            rows.append({"title": a.get("title", "")[:80], "seconds": round(time.time() - t0, 1),
                         "ok": ok, "modelVersion": mv, "usage": um})
            json.dump(out, open(FFXIV_COST, "w"), ensure_ascii=False, indent=2)
            print(f"FFXIV {model} ({mv}) ok={ok} in={um.get('promptTokenCount')} "
                  f"out={um.get('candidatesTokenCount')} think={um.get('thoughtsTokenCount')}", flush=True)
            time.sleep(2.0)
    print(f"SAVED {FFXIV_COST}", flush=True)


def _usd(model, usages, phase):
    p_in, p_out = PRICING[model][phase]
    return sum(u.get("promptTokenCount", 0) / 1e6 * p_in +
               (u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)) / 1e6 * p_out
               for u in usages)

def mean(xs): return sum(xs) / len(xs) if xs else float("nan")

def report():
    snap = json.load(open(SNAP))
    models = ["gemini-3.7-flash"] + RUN_MODELS
    runs = {m: _load_runs(m) for m in models}
    jd = json.load(open(os.path.join(OUT, "q_judge.json")))["results"]
    ws, n_b = snap["week_start"], len(snap["buckets"])

    L = [f"# 品質 A/B（含 blind judge）：`gemini-3.7-flash`（PR #90 存檔）→ `gemini-3.8-flash` → `gemini-4-argon`", "",
         f"route A · PR #90 凍結快照（週次 {ws}，buffer {snap['buffer_size']}）· 同 prompt(analyze_hot_topic) · "
         f"temp 0.2 · 每模型每桶 {N_RUNS} 次 · judge=`{JUDGE}`（非參賽、盲評、位置對調）", ""]

    for m_inc, m_chal in PAIRS:
        pair = f"{m_inc} vs {m_chal}"
        rs = [r for r in jd if r["pair"] == pair and r.get("ok")]
        wins = {m_inc: 0, m_chal: 0, "tie": 0}
        axis = {m: {ax: [] for ax in AXES} for m in (m_inc, m_chal)}
        for r in rs:
            wins[r["winner"]] = wins.get(r["winner"], 0) + 1
            for m in (m_inc, m_chal):
                for ax in AXES:
                    v = r["scores"].get(m, {}).get(ax)
                    if isinstance(v, (int, float)): axis[m][ax].append(v)
        L += [f"## {pair}", "",
              f"有效裁決 **{len(rs)}** 次（= {n_b} 桶 × {N_RUNS} run × 2 位置）：", "",
              "| 勝方 | 次數 | 佔比 |", "|---|---|---|"]
        for m in (m_inc, m_chal, "tie"):
            L.append(f"| {m} | {wins.get(m, 0)} | {wins.get(m, 0) / max(1, len(rs)) * 100:.0f}% |")
        L += ["", f"| 軸 | `{m_inc}` | `{m_chal}` | 差(挑戰−現行) |", "|---|---|---|---|"]
        for ax in AXES:
            mi, mc = mean(axis[m_inc][ax]), mean(axis[m_chal][ax])
            L.append(f"| {ax} | {mi:.2f} | {mc:.2f} | {mc - mi:+.2f} |")
        ai = [v for ax in AXES for v in axis[m_inc][ax]]; ac = [v for ax in AXES for v in axis[m_chal][ax]]
        L += [f"| **總平均** | **{mean(ai):.2f}** | **{mean(ac):.2f}** | **{mean(ac) - mean(ai):+.2f}** |", ""]

    L += ["## 熱點分析的成本與機械檢核（實測）", "",
          "| model | modelVersion | 生成次數 | $/報告 now | $/報告 later | 均 thinking | 均秒數 | 均字數 | 均引證[n] |",
          "|---|---|---|---|---|---|---|---|---|"]
    per_report = {}
    for m in models:
        allruns = [r for b in snap["buckets"] for r in runs[m][b["key"]]]
        us = [r.get("usage") or {} for r in allruns]
        per_report[m] = {ph: _usd(m, us, ph) / max(1, len(us)) for ph in ("now", "later")}
        mvs = sorted({r.get("modelVersion") or "（PR #90 未記錄）" for r in allruns})
        chk = [r["checks"] for r in allruns if r.get("checks")]
        L.append(f"| `{m}` | {', '.join(mvs)} | {len(allruns)} | ${per_report[m]['now']:.4f} | "
                 f"${per_report[m]['later']:.4f} | {mean([u.get('thoughtsTokenCount', 0) for u in us]):.0f} | "
                 f"{mean([r['seconds'] for r in allruns]):.1f} | {mean([c['chars'] for c in chk]):.0f} | "
                 f"{mean([c['citations'] for c in chk]):.1f} |")
    j_us = [r.get("usage") or {} for r in jd]
    L += ["", f"裁判 {len(jd)} 次呼叫成本：${_usd(JUDGE, j_us, 'now'):.4f}（`{JUDGE}`）", ""]

    if os.path.exists(FFXIV_COST):
        fc = json.load(open(FFXIV_COST)); fs = json.load(open(FFXIV_SNAP))
        L += ["## FFXIV analyze_article 的成本（實測小樣本，不評品質）", "",
              f"樣本：{fs['frozen_at'][:16]}Z 即時抓取，篩選後 {fs['n_selected']} 篇取前 {len(fs['articles'])} 篇。", "",
              "| model | 呼叫 | 失敗 | 均 in | 均 out+thinking | $/篇 now | $/篇 later |", "|---|---|---|---|---|---|---|"]
        per_article = {}
        for m in RUN_MODELS:
            rows = fc.get(m, []); us = [r["usage"] for r in rows]
            per_article[m] = {ph: _usd(m, us, ph) / max(1, len(us)) for ph in ("now", "later")}
            L.append(f"| `{m}` | {len(rows)} | {sum(1 for r in rows if not r['ok'])} | "
                     f"{mean([u.get('promptTokenCount', 0) for u in us]):.0f} | "
                     f"{mean([u.get('candidatesTokenCount', 0) + u.get('thoughtsTokenCount', 0) for u in us]):.0f} | "
                     f"${per_article[m]['now']:.4f} | ${per_article[m]['later']:.4f} |")
        L += ["", "## 換模型後每月的生成成本（全部呼叫端）", "",
              f"每週呼叫次數（實測，週報 log）：熱點＋彙整 {WEEKLY_CALLS['hot_or_digest']}、"
              f"FFXIV {WEEKLY_CALLS['ffxiv_article']}、auto-KB 0（近 3 週都沒有未知術語）。"
              "彙整的單次成本用熱點代替（推論：彙整的輸入較多，會低估）。", "",
              "| model | 月成本 now | 月成本 later |", "|---|---|---|"]
        for m in RUN_MODELS:
            row = []
            for ph in ("now", "later"):
                wk = (per_report[m][ph] * WEEKLY_CALLS["hot_or_digest"] +
                      per_article[m][ph] * WEEKLY_CALLS["ffxiv_article"])
                row.append(f"${wk * WEEKS_PER_MONTH:.3f}")
            L.append(f"| `{m}` | {row[0]} | {row[1]} |")
        L.append("")

    L += ["## 逐桶並排（各取 run1）＋ judge 理由", ""]
    for b in snap["buckets"]:
        L += [f"### {b['key']} — {b['label']}", f"_{b['kind']}_", "", "**輸入 top（判分依據）**", ""]
        for i, a in enumerate(b["inputs"], 1):
            L.append(f"{i}. {a['title']}｜{a['source']}")
        L.append("")
        for m in models:
            L += [f"#### ── {m}（run1）──", "", runs[m][b["key"]][0]["report"] or "(空)", ""]
        for m_inc, m_chal in PAIRS:
            pair = f"{m_inc} vs {m_chal}"
            L.append(f"**judge 理由（{pair}）：**")
            for r in jd:
                if r["pair"] == pair and r["bucket"] == b["key"] and r.get("ok"):
                    L.append(f"- run{r['run']} [{r['order']}] 勝：{r['winner']} — {r.get('reason', '')}")
            L.append("")
    open(os.path.join(OUT, "q_report.md"), "w").write("\n".join(L))
    print("REPORT q_report.md", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    steps = {"run": run, "judge": judge, "ffxiv_freeze": ffxiv_freeze, "ffxiv_cost": ffxiv_cost,
             "report": report}
    if cmd == "all":
        for f in (run, judge, ffxiv_freeze, ffxiv_cost, report):
            f()
    else:
        steps[cmd]()
    print("DONE", flush=True)
