"""
Route-A model A/B, snapshot-based so a delayed baseline still compares against
IDENTICAL input (the live buffer only mutates at the daily 00:00 UTC run, and a
free-tier reset lands after that — so we freeze).

Usage:
  model_ab.py freeze                      # fetch live buffer, freeze top-3 buckets
  model_ab.py run <model> [<model> ...]   # run model(s) against the frozen snapshot
  model_ab.py report                      # build markdown from whatever runs exist

Read-only against prod (get_traffic_buffer). Zero DB writes. temp 0.2, single run.
"""
import os
import re
import sys
import glob
import time
import json
from datetime import datetime, timezone, timedelta

REPO = "/home/luke/Projects/garyu-news-scraper"
sys.path.insert(0, REPO)
OUT = "/tmp/claude-1000/-home-luke-Projects-garyu-news-scraper/c00ae814-8f00-41ff-90a1-6dbe416a984a/scratchpad"
SNAP = os.path.join(OUT, "snapshot.json")

from dotenv import load_dotenv
load_dotenv(os.path.join(REPO, ".env"), override=True)

import logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

import src.analyzer as az
from src.pipeline_config import load_pipeline_config
from src.storage import get_traffic_buffer
from src.analyzer import (
    cluster_traffic_articles, score_topic_buckets, analyze_hot_topic, topic_token_signature,
)

TOP_K = 3

# USD per 1M tokens, standard paid tier, prompts <=200k (fetched 2026-07-24 from
# ai.google.dev/gemini-api/docs/pricing). Thinking tokens bill at the output rate.
PRICING = {
    "gemini-2.5-pro":   {"in": 1.25, "out": 10.00},
    "gemini-3.6-flash": {"in": 1.50, "out": 7.50},
}

# capture the exact prompt each call sends -> prove models saw identical input
_orig_call = az._call_gemini
_cap = {}
def _capturing_call(prompt, api_key, retries=None, system_prompt=None):
    _cap["prompt"] = prompt
    return _orig_call(prompt, api_key, retries=retries, system_prompt=system_prompt)
az._call_gemini = _capturing_call

# capture real usageMetadata (prompt/output/thinking tokens) from the 200 response
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
    tw = timezone(timedelta(hours=8))
    now = datetime.now(tw)
    return (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")


def freeze():
    config = load_pipeline_config()
    max_age_weeks = config.get("buffer", {}).get("max_age_weeks", 8)
    articles = get_traffic_buffer(max_age_weeks)
    buckets = cluster_traffic_articles(articles, config)
    scores = score_topic_buckets(buckets, config)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:TOP_K]

    snap = {"week_start": _week_start(), "buffer_size": len(articles),
            "n_buckets": len(buckets), "frozen_at": datetime.now(timezone.utc).isoformat(),
            "buckets": []}
    for rank, (bid, sc) in enumerate(ranked, 1):
        arts = buckets[bid]
        major = arts[0].get("major_category", bid) if arts else bid
        sig = topic_token_signature(arts)
        label = f"{major} · {sig[0]}" if sig else major
        top10 = sorted(arts, key=lambda a: float(a.get("initial_quality_score") or 0),
                       reverse=True)[:10]
        snap["buckets"].append({
            "rank": rank, "bid": bid, "label": label, "score": sc,
            "n_articles": len(arts),
            "articles": arts,   # full dicts -> exact re-run later
            "inputs": [{"title": a.get("title", ""), "link": a.get("link", ""),
                        "source": a.get("source", ""),
                        "score": float(a.get("initial_quality_score") or 0)} for a in top10],
        })
    with open(SNAP, "w") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    print(f"frozen: buffer={snap['buffer_size']} buckets={snap['n_buckets']} -> top {len(snap['buckets'])}")
    for b in snap["buckets"]:
        print(f"  {b['rank']}. {b['label']}  score={b['score']:.3f}  {b['n_articles']} 篇")


def run(models):
    snap = json.load(open(SNAP))
    ws = snap["week_start"]
    for model in models:
        az.GEMINI_MODEL = model
        out = {"model": model, "ran_at": datetime.now(timezone.utc).isoformat(), "per_bucket": []}
        for b in snap["buckets"]:
            print(f"[{model}] bucket {b['rank']} {b['label']} …", end="", flush=True)
            _cap["usage"] = None
            t0 = time.time()
            report, _links = analyze_hot_topic(b["articles"], b["label"], ws)
            dt = round(time.time() - t0, 1)
            um = _cap.get("usage") or {}
            out["per_bucket"].append({
                "bid": b["bid"], "report": report, "seconds": dt,
                "prompt_len": len(_cap.get("prompt", "")),
                "usage": um,
                "checks": mech_checks(report) if report else None,
            })
            think = um.get("thoughtsTokenCount", 0)
            print(f" {len(report)} chars, {dt}s, tok in={um.get('promptTokenCount')} "
                  f"out={um.get('candidatesTokenCount')} think={think}")
            time.sleep(2.5)
        path = os.path.join(OUT, f"run_{model.replace('.', '_')}.json")
        json.dump(out, open(path, "w"), ensure_ascii=False, indent=2)
        print(f"  saved {path}")


REQUIRED_HEADERS = ["### 一、", "### 二、", "### 三、"]
REQUIRED_FIELDS = ["交織度分布", "代表個案", "人因變數", "工程變數", "交織說明",
                   "觸發條件", "審查結果"]

def mech_checks(text):
    return {
        "headers": f"{sum(1 for h in REQUIRED_HEADERS if h in text)}/3",
        "fields": f"{sum(1 for f in REQUIRED_FIELDS if f in text)}/{len(REQUIRED_FIELDS)}",
        "citations": len(re.findall(r'\[\d+\]', text)),
        "車種分流": len(re.findall(r'車種分流', text)),
        "不適用": len(re.findall(r'不適用', text)),
        "chars": len(text),
    }


def report():
    snap = json.load(open(SNAP))
    runs = {}
    for p in sorted(glob.glob(os.path.join(OUT, "run_*.json"))):
        r = json.load(open(p))
        runs[r["model"]] = {pb["bid"]: pb for pb in r["per_bucket"]}
    models = list(runs.keys())

    L = [f"# 模型比較實驗：{' vs '.join(f'`{m}`' for m in models) or '(尚無 run)'}", "",
         f"route A · 凍結快照（同輸入）· 同 prompt · temp 0.2 · 單次 run  ",
         f"週次 {snap['week_start']} ｜ buffer {snap['buffer_size']} 篇 ｜ 分群 {snap['n_buckets']} "
         f"bucket ｜ top {len(snap['buckets'])} ｜ frozen {snap['frozen_at'][:16]}Z", ""]

    if models:
        L += ["## 機械檢核總表（E1，程式量測）", "",
              "| bucket | model | 三段齊全 | 欄位齊全 | 引證[n] | 車種分流 | 不適用 | 字數 | 秒 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for b in snap["buckets"]:
            for m in models:
                pb = runs[m].get(b["bid"])
                c = pb and pb["checks"]
                if c:
                    L.append(f"| {b['rank']}. {b['label']} | `{m}` | {c['headers']} | {c['fields']} "
                             f"| {c['citations']} | {c['車種分流']} | {c['不適用']} | {c['chars']} | {pb['seconds']} |")
                else:
                    L.append(f"| {b['rank']}. {b['label']} | `{m}` | (空/失敗/未跑) | | | | | | |")
        L += ["", "> 引證[n]＝`[數字]` Article ID 次數（文本依據密度代理）。車種分流＝prompt 禁止讀者倒推的框架，>0 需人工判讀。不適用＝觸發制正確留空次數。", ""]

        L += ["## 成本（E1，實測 usageMetadata × 定價）", "",
              "| bucket | model | in tok | out tok | think tok | 計費out | 成本 USD | 秒 |",
              "|---|---|---|---|---|---|---|---|"]
        totals = {m: 0.0 for m in models}
        for b in snap["buckets"]:
            for m in models:
                pb = runs[m].get(b["bid"])
                if not pb:
                    continue
                um = pb.get("usage") or {}
                pin = um.get("promptTokenCount", 0)
                pout = um.get("candidatesTokenCount", 0)
                pth = um.get("thoughtsTokenCount", 0)
                billed = pout + pth
                pr = PRICING.get(m)
                cost = (pin / 1e6 * pr["in"] + billed / 1e6 * pr["out"]) if pr else 0.0
                totals[m] += cost
                L.append(f"| {b['rank']}. {b['label']} | `{m}` | {pin} | {pout} | {pth} | "
                         f"{billed} | ${cost:.5f} | {pb['seconds']} |")
        L.append("")
        n = max(1, len(snap["buckets"]))
        for m in models:
            L.append(f"- **{m}** 三桶合計 **${totals[m]:.5f}**（單桶均 ${totals[m]/n:.5f}）")
        L += ["", "> 計費out＝candidates＋thinking（Gemini 思考 token 以 output 費率計）。"
              "定價 ≤200k prompt：2.5-pro in$1.25/out$10；3.6-flash in$1.50/out$7.50（2026-07-24）。", ""]

    for b in snap["buckets"]:
        L += [f"## Bucket {b['rank']} — {b['label']}",
              f"score={b['score']:.3f} ｜ {b['n_articles']} 篇", "",
              "**輸入 top-10（by initial_quality_score）**", ""]
        for i, a in enumerate(b["inputs"], 1):
            L.append(f"{i}. {a['title']}  ·  {a['source']}  ·  score={a['score']:.2f}")
        L.append("")
        for m in models:
            pb = runs[m].get(b["bid"])
            L += [f"### ── {m} ──", "", (pb and pb["report"]) or "(未跑/空)", ""]
    open(os.path.join(OUT, "model_ab_report.md"), "w").write("\n".join(L))
    print(f"report -> {OUT}/model_ab_report.md  (models: {models or 'none'})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "freeze":
        freeze()
    elif cmd == "run":
        run(sys.argv[2:])
    elif cmd == "report":
        report()
    else:
        sys.exit(f"unknown cmd: {cmd}")
