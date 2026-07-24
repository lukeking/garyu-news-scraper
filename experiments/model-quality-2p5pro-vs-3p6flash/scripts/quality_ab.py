"""
Quality A/B with blind judge: gemini-2.5-pro vs gemini-3.6-flash on RICH POLICY
buckets, N runs each, same prompt (analyze_hot_topic). A non-contestant model
(gemini-3.1-pro-preview) judges pairs BLIND and POSITION-SWAPPED on the prompt's
own rubric axes, so a real quality gap can be told apart from temp-0.2 noise.

Read-only against prod. temp 0.2. Subcommands: freeze | run | judge | report | all
"""
import os, re, sys, glob, json, time, random
from datetime import datetime, timezone, timedelta

REPO = "/home/luke/Projects/garyu-news-scraper"
sys.path.insert(0, REPO)
OUT = "/tmp/claude-1000/-home-luke-Projects-garyu-news-scraper/c00ae814-8f00-41ff-90a1-6dbe416a984a/scratchpad"
SNAP = os.path.join(OUT, "q_snapshot.json")

from dotenv import load_dotenv
load_dotenv(os.path.join(REPO, ".env"), override=True)
import logging; logging.basicConfig(level=logging.ERROR)

import src.analyzer as az
from src.pipeline_config import load_pipeline_config
from src.storage import get_traffic_buffer
from src.analyzer import cluster_traffic_articles, score_topic_buckets, analyze_hot_topic

MODELS = ["gemini-2.5-pro", "gemini-3.6-flash"]
JUDGE = "gemini-3.1-pro-preview"      # non-contestant, reduces self-preference bias
N_RUNS = 3
PRICING = {  # USD / 1M tok, standard paid <=200k prompt (fetched 2026-07-24)
    "gemini-2.5-pro":   {"in": 1.25, "out": 10.00},
    "gemini-3.6-flash": {"in": 1.50, "out": 7.50},
}
AXES = ["格式遵循", "文本依據", "因果解構深度", "觸發制紀律", "轉譯紀律"]

_orig_call = az._call_gemini
_cap = {}
def _capturing_call(prompt, api_key, retries=None, system_prompt=None):
    _cap["prompt"] = prompt
    return _orig_call(prompt, api_key, retries=retries, system_prompt=system_prompt)
az._call_gemini = _capturing_call

_orig_post = az.requests.post
def _cap_post(*a, **k):
    resp = _orig_post(*a, **k)
    try:
        um = resp.json().get("usageMetadata")
        if um:
            _cap["usage"] = um
    except Exception:
        pass
    return resp
az.requests.post = _cap_post


def _week_start():
    tw = timezone(timedelta(hours=8)); now = datetime.now(tw)
    return (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")


def build_buckets():
    cfg = load_pipeline_config()
    arts = get_traffic_buffer(cfg.get("buffer", {}).get("max_age_weeks", 8))
    buckets = cluster_traffic_articles(arts, cfg)
    scores = score_topic_buckets(buckets, cfg)

    # B1: natural cluster containing the 機車直接左轉 policy debate
    natural = None
    for bid, b in buckets.items():
        if any("直接左轉" in (a.get("title") or "") for a in b):
            natural = (bid, b); break
    out = []
    if natural:
        out.append({"key": "B1_機車左轉政策", "label": "機車左轉政策 · 直接左轉/免待轉",
                    "kind": f"natural cluster {natural[0]} (n={len(natural[1])})",
                    "articles": natural[1]})
    # B2/B3: category pools (digest-sized, top by score)
    for cat, key in [("路權政策", "B2_路權政策"), ("道安政策", "B3_道安政策")]:
        pool = [a for a in arts if (a.get("major_category") or "") == cat]
        pool = sorted(pool, key=lambda a: float(a.get("initial_quality_score") or 0), reverse=True)
        out.append({"key": key, "label": f"{cat} · 政策彙整",
                    "kind": f"category pool (n={len(pool)}, top-10 fed)", "articles": pool})
    return out, len(arts), len(buckets)


def freeze():
    bks, nbuf, nb = build_buckets()
    snap = {"week_start": _week_start(), "buffer_size": nbuf, "n_buckets": nb,
            "frozen_at": datetime.now(timezone.utc).isoformat(), "buckets": []}
    for b in bks:
        top10 = sorted(b["articles"], key=lambda a: float(a.get("initial_quality_score") or 0),
                       reverse=True)[:10]
        snap["buckets"].append({**b, "inputs": [
            {"title": a.get("title", ""), "source": a.get("source", ""),
             "summary": (a.get("summary") or a.get("content") or "")[:200],
             "score": float(a.get("initial_quality_score") or 0)} for a in top10]})
    json.dump(snap, open(SNAP, "w"), ensure_ascii=False, indent=2)
    for b in snap["buckets"]:
        print(f"frozen {b['key']}: {b['kind']}")


REQ_HEAD = ["### 一、", "### 二、", "### 三、"]
REQ_FIELD = ["交織度分布", "代表個案", "人因變數", "工程變數", "交織說明", "觸發條件", "審查結果"]
def mech(t):
    return {"headers": sum(1 for h in REQ_HEAD if h in t), "fields": sum(1 for f in REQ_FIELD if f in t),
            "citations": len(re.findall(r"\[\d+\]", t)), "car": len(re.findall(r"車種分流", t)),
            "na": len(re.findall(r"不適用", t)), "chars": len(t)}


def run():
    snap = json.load(open(SNAP)); ws = snap["week_start"]
    for model in MODELS:
        path = os.path.join(OUT, f"q_run_{model.replace('.', '_')}.json")
        out = {"model": model, "per_bucket": {}}
        for b in snap["buckets"]:
            runs = []
            for k in range(N_RUNS):
                az.GEMINI_MODEL = model; _cap["usage"] = None
                t0 = time.time()
                rep, _ = analyze_hot_topic(b["articles"], b["label"], ws)
                um = _cap.get("usage") or {}
                runs.append({"report": rep, "seconds": round(time.time() - t0, 1),
                             "usage": um, "checks": mech(rep) if rep else None})
                print(f"GEN {model} {b['key']} run{k+1}/{N_RUNS} "
                      f"{len(rep)}c {round(time.time()-t0,1)}s in={um.get('promptTokenCount')} "
                      f"out={um.get('candidatesTokenCount')} think={um.get('thoughtsTokenCount')}", flush=True)
                time.sleep(2.0)
            out["per_bucket"][b["key"]] = runs
        json.dump(out, open(path, "w"), ensure_ascii=False, indent=2)
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
    runs = {m: json.load(open(os.path.join(OUT, f"q_run_{m.replace('.', '_')}.json")))["per_bucket"]
            for m in MODELS}
    api_key = az._get_api_key(); az.GEMINI_MODEL = JUDGE
    pro, flash = MODELS  # pro=A-slot candidate name only
    results = []
    for b in snap["buckets"]:
        arts_block = _articles_block(b["inputs"])
        for k in range(N_RUNS):
            rp = runs[pro][b["key"]][k]["report"]
            rf = runs[flash][b["key"]][k]["report"]
            if not rp or not rf:
                continue
            for order in ("pro_first", "flash_first"):
                if order == "pro_first":
                    A_model, B_model, A_txt, B_txt = pro, flash, rp, rf
                else:
                    A_model, B_model, A_txt, B_txt = flash, pro, rf, rp
                prompt = JUDGE_TMPL.format(label=b["label"], articles=arts_block, A=A_txt, B=B_txt)
                _cap["usage"] = None
                raw = az._call_gemini(prompt, api_key, system_prompt=JUDGE_SYS)
                parsed = _parse_json(raw)
                ok = bool(parsed and "A" in parsed and "B" in parsed)
                # de-swap: map A/B back to model
                rec = {"bucket": b["key"], "run": k + 1, "order": order,
                       "A_model": A_model, "B_model": B_model, "ok": ok, "raw": raw}
                if ok:
                    scores = {A_model: parsed["A"], B_model: parsed["B"]}
                    w = parsed.get("winner", "tie")
                    win_model = A_model if w == "A" else B_model if w == "B" else "tie"
                    rec.update({"scores": scores, "winner": win_model,
                                "reason": parsed.get("reason", "")})
                results.append(rec)
                print(f"JUDGE {b['key']} run{k+1} {order} ok={ok} "
                      f"winner={rec.get('winner')}", flush=True)
                time.sleep(2.0)
    json.dump({"judge_model": JUDGE, "results": results},
              open(os.path.join(OUT, "q_judge.json"), "w"), ensure_ascii=False, indent=2)
    print("SAVED q_judge.json", flush=True)


def _cost(model, runs_list):
    tot = 0.0
    for r in runs_list:
        um = r.get("usage") or {}; pr = PRICING.get(model)
        if pr:
            tot += um.get("promptTokenCount", 0)/1e6*pr["in"] + \
                   (um.get("candidatesTokenCount", 0)+um.get("thoughtsTokenCount", 0))/1e6*pr["out"]
    return tot

def report():
    snap = json.load(open(SNAP))
    runs = {m: json.load(open(os.path.join(OUT, f"q_run_{m.replace('.', '_')}.json")))["per_bucket"]
            for m in MODELS}
    jd = json.load(open(os.path.join(OUT, "q_judge.json")))["results"]
    pro, flash = MODELS

    # aggregate judge: per-axis mean per model, win counts
    axis_scores = {m: {ax: [] for ax in AXES} for m in MODELS}
    wins = {pro: 0, flash: 0, "tie": 0}
    for r in jd:
        if not r.get("ok"): continue
        wins[r["winner"]] = wins.get(r["winner"], 0) + 1
        for m in MODELS:
            for ax in AXES:
                v = r["scores"].get(m, {}).get(ax)
                if isinstance(v, (int, float)): axis_scores[m][ax].append(v)
    def mean(xs): return sum(xs)/len(xs) if xs else float("nan")

    L = [f"# 品質 A/B（含 blind judge）：`{pro}` vs `{flash}`", "",
         f"route A · 凍結快照 · 同 prompt(analyze_hot_topic) · temp 0.2 · 每模型每桶 {N_RUNS} 次 · "
         f"judge=`{JUDGE}`（非參賽、盲評、位置對調）  ",
         f"週次 {snap['week_start']} ｜ buffer {snap['buffer_size']} ｜ frozen {snap['frozen_at'][:16]}Z", "",
         "## 選用的政策桶", ""]
    for b in snap["buckets"]:
        L.append(f"- **{b['key']}** — {b['label']}（{b['kind']}）")
    n_ok = sum(1 for r in jd if r.get("ok"))
    L += ["", "## 盲評結果（judge 勝負，位置對調後）", "",
          f"有效裁決 **{n_ok}** 次（= {len(snap['buckets'])} 桶 × {N_RUNS} run × 2 位置）：", "",
          f"| 勝方 | 次數 | 佔比 |", "|---|---|---|"]
    for m in [pro, flash, "tie"]:
        L.append(f"| {m} | {wins.get(m,0)} | {wins.get(m,0)/max(1,n_ok)*100:.0f}% |")
    L += ["", "## 盲評逐軸平均分（0-5）", "",
          "| 軸 | " + " | ".join(f"`{m}`" for m in MODELS) + " | 差 |",
          "|---|" + "---|"*(len(MODELS)+1)]
    for ax in AXES:
        mp, mf = mean(axis_scores[pro][ax]), mean(axis_scores[flash][ax])
        L.append(f"| {ax} | {mp:.2f} | {mf:.2f} | {mp-mf:+.2f} |")
    # overall mean
    allp = [v for ax in AXES for v in axis_scores[pro][ax]]
    allf = [v for ax in AXES for v in axis_scores[flash][ax]]
    L.append(f"| **總平均** | **{mean(allp):.2f}** | **{mean(allf):.2f}** | **{mean(allp)-mean(allf):+.2f}** |")

    # cost + mech summary
    L += ["", "## 成本與機械檢核（E1，實測）", "",
          "| model | 生成次數 | 總成本 USD | 均字數 | 均引證[n] |", "|---|---|---|---|---|"]
    for m in MODELS:
        allruns = [r for b in snap["buckets"] for r in runs[m][b["key"]]]
        cost = _cost(m, allruns)
        chars = [r["checks"]["chars"] for r in allruns if r.get("checks")]
        cites = [r["checks"]["citations"] for r in allruns if r.get("checks")]
        L.append(f"| `{m}` | {len(allruns)} | ${cost:.4f} | {sum(chars)//max(1,len(chars))} "
                 f"| {sum(cites)/max(1,len(cites)):.1f} |")

    # per-bucket side-by-side (run 1 only, to keep readable) + judge reasons
    L += ["", "## 逐桶並排（各取 run1）＋ judge 理由", ""]
    for b in snap["buckets"]:
        L += [f"### {b['key']} — {b['label']}", f"_{b['kind']}_", "",
              "**輸入 top（判分依據）**", ""]
        for i, a in enumerate(b["inputs"], 1):
            L.append(f"{i}. {a['title']}｜{a['source']}")
        L.append("")
        for m in MODELS:
            L += [f"#### ── {m}（run1）──", "", runs[m][b["key"]][0]["report"] or "(空)", ""]
        L.append("**judge 理由（本桶所有裁決）：**")
        for r in jd:
            if r["bucket"] == b["key"] and r.get("ok"):
                L.append(f"- run{r['run']} [{r['order']}] 勝：{r['winner']} — {r.get('reason','')}")
        L.append("")
    open(os.path.join(OUT, "q_report.md"), "w").write("\n".join(L))
    print(f"REPORT q_report.md  wins={wins}  ovr={mean(allp):.2f} vs {mean(allf):.2f}", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "all":
        freeze(); run(); judge(); report()
    else:
        {"freeze": freeze, "run": run, "judge": judge, "report": report}[cmd]()
    print("DONE", flush=True)
