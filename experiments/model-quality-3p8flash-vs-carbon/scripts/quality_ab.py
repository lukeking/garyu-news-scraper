"""carbon 對 3.8 的品質評比（BACKLOG GNS-20261019-1vk）：018 重播素材的真實輸入，現行指令各自重生成，check_report() 當 Gate，2.5-pro 盲評對調。
子命令 inputs | run | judge | ffxiv_freeze | ffxiv_cost | report | all；只讀 prod（hot_topic_reports、articles、knowledge_base、指紋），只寫本目錄 data/。
做法、判準與費用見同目錄的 README.md。"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
sys.path[:0] = [REPO, os.path.join(REPO, "scripts")]

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(REPO, ".env"), override=True)  # analyzer 在 import 時讀環境，先載入再 import
import logging  # noqa: E402
logging.basicConfig(level=logging.ERROR)
logging.getLogger("src.analyzer").setLevel(logging.WARNING)  # 重試、逾時、MAX_TOKENS 要看得到

import src.analyzer as az  # noqa: E402
import replay_report_review as rr  # noqa: E402

REPORTS = [  # (週次, topic_label)：018 重播 fixture 用過的已發布報告
    ("2026-10-19", "道安政策 · 彙整"), ("2026-10-26", "道安政策 · 彙整"), ("2026-11-02", "道安政策 · 彙整"),
    ("2026-08-03", "機車事故 · 中時"), ("2026-09-07", "機車事故 · TVBS"), ("2026-09-21", "行人事故 · 行人"),
    ("2026-10-26", "機車事故 · 機車"), ("2026-09-14", "道安政策 · 交通安全"), ("2026-10-19", "科技執法 · 新聞"),
]
INCUMBENT, CHALLENGER = RUN_MODELS = ["gemini-3.8-flash", "gemini-4-carbon"]
JUDGE = "gemini-2.5-pro"  # 非參賽；2026-12-01 起 API 轉給 3.8-flash，_check_version 會擋下
N_RUNS = 2
FFXIV_SAMPLE = 5
WEEKLY_CALLS = {"hot_or_digest": 3, "ffxiv_article": 30}  # 熱點＋彙整取近週上界；FFXIV 取 ffxiv.max_selected
WEEKS_PER_MONTH = 4.35
PRICING = {  # USD / 1M tok，output 含 thinking（aistudio.google.com/docs/pricing，2026-11-12 抓取）
    "gemini-3.8-flash": {"now": (0.75, 3.75), "later": (1.50, 7.50)},   # 優惠到 2026-12-31
    "gemini-4-carbon": {"now": (2.00, 10.00), "later": (4.00, 20.00)},  # 優惠到 2026-11-30
    "gemini-2.5-pro": {"now": (1.25, 10.00), "later": (1.25, 10.00)},   # prompt <= 200k
}
CARBON_MAX_OUT = os.environ.get("QAB_CARBON_MAX_OUT")  # 例 65536：carbon 用這個輸出上限重跑、結果另存；未設＝prod 的預設 8192
CARBON_TIMEOUT = 600  # 放寬上限時 carbon 的單次 timeout；prod 的 _call_gemini 寫死 120，這是與 prod 呼叫路徑不同的一處
JUDGE_TIMEOUT = 600   # 裁判是量測工具不是受測路徑；120 秒時長 prompt 會逾時重試，每次被放棄的嘗試照樣計費
JUDGE_MAX_OUT = "65536"  # 2.5-pro 在長的彙整 prompt 上會想到 8192 用完、回應沒有 parts（11-12 sentinel 實測）
SUFFIX = f"_max{CARBON_MAX_OUT}" if CARBON_MAX_OUT else ""
CHECK_NAMES = ("independence_claim", "date_unlabeled", "self_count", "title_only_in_sections",
               "missing_section", "id_out_of_range")

_cap = {}
_budget = {"left": None}  # 子命令後的數字＝這次最多呼叫幾次 API（sentinel 用）；None 不限
_orig_post = az.requests.post


def _spend():
    if _budget["left"] is None:
        return True
    if _budget["left"] <= 0:
        print("LIMIT 這次的呼叫次數用完，停在這裡（重跑會接著做）", flush=True)
        return False
    _budget["left"] -= 1
    return True


def _cap_post(*a, **k):
    if _cap.get("timeout_override"):
        k["timeout"] = _cap["timeout_override"]
    _cap["sent"] = {"maxOutputTokens": ((k.get("json") or {}).get("generationConfig") or {}).get("maxOutputTokens"),
                    "timeout": k.get("timeout")}
    resp = _orig_post(*a, **k)
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
    _cap["usage"] = None
    _cap["modelVersion"] = None
    _cap["finishReason"] = None
    _cap["sent"] = None


def _use(model):
    """切到 model；carbon 在放寬模式下改輸出上限與 timeout，其餘照 prod（不設 GEMINI_MAX_OUTPUT_TOKENS、timeout 120）。"""
    az.GEMINI_MODEL = model
    widen = bool(CARBON_MAX_OUT) and model == CHALLENGER
    if widen or model == JUDGE:
        os.environ["GEMINI_MAX_OUTPUT_TOKENS"] = CARBON_MAX_OUT if widen else JUDGE_MAX_OUT
    else:
        os.environ.pop("GEMINI_MAX_OUTPUT_TOKENS", None)
    _cap["timeout_override"] = CARBON_TIMEOUT if widen else JUDGE_TIMEOUT if model == JUDGE else None


def _check_version(requested):
    got = _cap.get("modelVersion")
    if not got or not got.startswith(requested):
        sys.exit(f"STOP modelVersion mismatch: requested {requested}, response {got!r}")
    return got


def _p(name):
    return os.path.join(OUT, name)


def _load(name):
    with open(_p(name), encoding="utf-8") as f:
        return json.load(f)


def _dump(name, obj):
    os.makedirs(OUT, exist_ok=True)
    with open(_p(name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def _run_name(model):
    return f"q_run_{model.replace('.', '_')}{SUFFIX if model == CHALLENGER else ''}.json"


def inputs():
    frozen = {}
    for week, topic in REPORTS:
        got = rr.load_inputs(week, topic)
        frozen[f"{week}｜{topic}"] = {"week": week, "topic": topic, "template": got["template"],
                                     "report_id": got["report"]["id"], "input": got["input"],
                                     "articles": got["articles"]}
        print(f"INPUT {week} {topic} {got['template']} n={len(got['articles'])} ({got['input']})", flush=True)
    _dump("inputs.json", {"frozen_at": datetime.now(timezone.utc).isoformat(), "reports": frozen})


def run():
    reports = _load("inputs.json")["reports"]
    for model in RUN_MODELS:
        name = _run_name(model)
        out = _load(name) if os.path.exists(_p(name)) else {"model": model, "per_report": {}}
        for key, r in reports.items():
            runs = out["per_report"].setdefault(key, [])
            while len(runs) < N_RUNS:
                if not _spend():
                    return
                _use(model)
                _reset()
                t0 = time.time()
                try:
                    regen, ordered, _ = rr.regenerate(r["template"], r["articles"], r["topic"], r["week"])
                    checks = rr.run_checks(regen["text"], r["template"], ordered, rr.current_chars(r["template"]))
                    rec = {"text": regen["text"], "input_text": regen["input_text"], "sources": regen["sources"],
                           "title_only_ids": regen["title_only_ids"], "counts": checks["counts"], "hits": checks["hits"]}
                except rr.ReplayError as e:
                    rec = {"error": str(e)}
                mv = _cap.get("modelVersion")
                if mv is not None or "error" not in rec:  # 有文字卻沒有 modelVersion 也停：無法確認是哪個模型寫的
                    mv = _check_version(model)
                um = _cap.get("usage") or {}
                rec.update({"seconds": round(time.time() - t0, 1), "usage": um, "modelVersion": mv,
                            "finishReason": _cap.get("finishReason"), "sent": _cap.get("sent")})
                runs.append(rec)
                _dump(name, out)
                print(f"GEN {model} ({mv}) {key} run{len(runs)}/{N_RUNS} finish={rec['finishReason']} "
                      f"{'ERROR ' + rec['error'] if 'error' in rec else str(len(rec['text'])) + 'c'} {rec['seconds']}s "
                      f"in={um.get('promptTokenCount')} out={um.get('candidatesTokenCount')} "
                      f"think={um.get('thoughtsTokenCount')}", flush=True)
                time.sleep(2.0)
        print(f"SAVED {_p(name)}", flush=True)


AXES = {
    "hot": ["格式遵循", "文本依據", "分類與因果解構", "觸發制紀律", "轉譯紀律"],
    "digest": ["格式遵循", "文本依據", "不推論紀律", "彙整完整度"],
}
RUBRIC = {
    "hot": """- 格式遵循：三段標題與各欄位齊全、未合併換行；清單沒有事故報導時，第一段只寫「本批無事故報導，不適用」且不輸出五個欄位；有事故報導時，交織度分布六類加總等於清單篇數。
- 文本依據：每項結論標註 Article ID，且與該篇來源相符（非杜撰）；摘要寫「（僅標題）」的報導引用時標「僅標題」，不補寫標題沒有的主詞、範圍或日期；傷亡人數、傷勢與行向照來源寫。
- 分類與因果解構：每篇的六類歸類照判定規則——歸 [工程主導]／[雙因交織] 須寫出來源寫到的工程條件怎麼放大人因動作；說不出放大機制時歸 [人因主導]（有直接證據）或 [工程未見放大]；來源沒寫工程條件歸 [工程資料未載]。人因、工程變數照來源寫，來源沒寫的填「來源未載」，值得查的寫成「待查證：…？」，不斷言「未落實」「缺乏」。
- 觸發制紀律：政經（第二段）、官方論述偏誤（第三段）只在來源有明確文本時啟動，否則正確填不適用；啟動時只列來源明文的制度做法與有發現的偏誤，不寫機關的動機或「迴避」。
- 轉譯紀律：引用外國原則時講機制、用原則本身的變數（速度與質量）、同質性的兩種解法都交代、撞詞切割；結論不得被讀成「車種分流是對的」。""",
    "digest": """- 格式遵循：三段標題（本期概覽／分節彙整／待追蹤）齊全；概覽 2-3 句、不寫篇數或事件數；分節每段結尾標 Article ID；待追蹤無則填「本期無」。
- 文本依據：每段的時間、行為者、決策或訴求與所標 Article ID 的來源相符（非杜撰）；寫到時間時標明是報導日，除非來源明文寫出事件發生日；數字照來源寫範圍、期間與基準。
- 不推論紀律：不自行推論事件之間的因果、趨勢或「顯示…風向」的關聯；來源明文寫出的關聯照寫並標出寫它的 Article ID。
- 彙整完整度：多篇報導同一事件時合併為一段並列出全部 Article ID；分組依主題相近度合理；清單中有實質內容的事件沒有被漏掉。""",
}
JUDGE_SYS = {
    "hot": "你是嚴格中立的交通安全結構性分析報告評審。",
    "digest": "你是嚴格中立的交通政策動態彙整評審。",
}
JUDGE_SYS_TAIL = ("只依據提供的來源清單與評分準則，對兩份報告（A、B）逐軸評分。禁止偏袒任何一方，不知道兩份報告由哪個模型產生。"
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


def judge_prompt(template, label, articles, a_text, b_text):
    axes = ",".join(f'"{ax}":0' for ax in AXES[template])
    return JUDGE_TMPL.format(label=label, articles=articles, rubric=RUBRIC[template], A=a_text, B=b_text, axes=axes)


def _parse_json(raw):
    if not raw:
        return None
    s = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", s, re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None


def _valid(parsed, template):
    if not isinstance(parsed, dict) or parsed.get("winner") not in ("A", "B", "tie"):
        return False
    return all(isinstance(parsed.get(s), dict) and all(isinstance(parsed[s].get(ax), (int, float)) for ax in AXES[template])
               for s in ("A", "B"))


def judge():
    reports = _load("inputs.json")["reports"]
    runs = {m: _load(_run_name(m))["per_report"] for m in RUN_MODELS}
    jname = f"q_judge{SUFFIX}.json"
    results = _load(jname)["results"] if os.path.exists(_p(jname)) else []
    seen = {(x["report"], x["run"], x["order"]) for x in results}
    api_key = az._get_api_key()
    for key, r in reports.items():
        for k in range(N_RUNS):
            inc, chal = runs[INCUMBENT][key][k], runs[CHALLENGER][key][k]
            if "error" in inc or "error" in chal:
                print(f"SKIP {key} run{k + 1}：有一方生成失敗", flush=True)
                continue
            if inc["input_text"] != chal["input_text"]:
                sys.exit(f"STOP {key} run{k + 1}：兩個模型看到的清單不同")
            for order in ("inc_first", "chal_first"):
                if (key, k + 1, order) in seen:
                    continue
                if not _spend():
                    return
                a_m, b_m = (INCUMBENT, CHALLENGER) if order == "inc_first" else (CHALLENGER, INCUMBENT)
                prompt = judge_prompt(r["template"], r["topic"], inc["input_text"],
                                      runs[a_m][key][k]["text"], runs[b_m][key][k]["text"])
                _use(JUDGE)
                _reset()
                t0 = time.time()
                raw = az._call_gemini(prompt, api_key, system_prompt=JUDGE_SYS[r["template"]] + JUDGE_SYS_TAIL)
                mv = _check_version(JUDGE)
                parsed = _parse_json(raw)
                ok = _valid(parsed, r["template"])
                rec = {"report": key, "template": r["template"], "run": k + 1, "order": order, "A_model": a_m,
                       "B_model": b_m, "ok": ok, "raw": raw, "modelVersion": mv, "usage": _cap.get("usage") or {},
                       "finishReason": _cap.get("finishReason"), "sent": _cap.get("sent"), "seconds": round(time.time() - t0, 1)}
                if ok:
                    w = parsed["winner"]
                    rec.update({"scores": {a_m: parsed["A"], b_m: parsed["B"]},
                                "winner": a_m if w == "A" else b_m if w == "B" else "tie",
                                "reason": parsed.get("reason", "")})
                results.append(rec)
                _dump(jname, {"judge_model": JUDGE, "results": results})
                print(f"JUDGE {key} run{k + 1} {order} ok={ok} winner={rec.get('winner')} {rec['seconds']}s "
                      f"finish={rec['finishReason']}", flush=True)
                time.sleep(2.0)
    print(f"SAVED {_p(jname)}", flush=True)


def ffxiv_freeze():
    from src.pipeline.ffxiv import FFXIVCategory
    cat = FFXIVCategory()
    raw = cat.collect()
    picked = cat.filter(raw)
    _dump("ffxiv_sample.json", {"frozen_at": datetime.now(timezone.utc).isoformat(), "n_collected": len(raw),
                                "n_selected": len(picked), "articles": picked[:FFXIV_SAMPLE]})
    for a in picked[:FFXIV_SAMPLE]:
        print(f"frozen {a.get('source')}: {a.get('title', '')[:60]}", flush=True)


def ffxiv_cost():
    s = _load("ffxiv_sample.json")
    api_key = az._get_api_key()
    cname = f"ffxiv_cost{SUFFIX}.json"
    out = _load(cname) if os.path.exists(_p(cname)) else {}
    for model in RUN_MODELS:
        rows = out.setdefault(model, [])
        for a in s["articles"][len(rows):]:
            if not _spend():
                return
            _use(model)
            _reset()
            t0 = time.time()
            res = az.analyze_article(dict(a), api_key)
            mv = _check_version(model)
            um = _cap.get("usage") or {}
            ok = (res.get("analysis") or {}).get("summary") != "（分析失敗）"
            rows.append({"title": a.get("title", "")[:80], "seconds": round(time.time() - t0, 1),
                         "ok": ok, "modelVersion": mv, "usage": um, "finishReason": _cap.get("finishReason"),
                         "sent": _cap.get("sent")})
            _dump(cname, out)
            print(f"FFXIV {model} ({mv}) ok={ok} in={um.get('promptTokenCount')} "
                  f"out={um.get('candidatesTokenCount')} think={um.get('thoughtsTokenCount')}", flush=True)
            time.sleep(2.0)
    print(f"SAVED {_p(cname)}", flush=True)


def _usd(model, usages, phase):
    p_in, p_out = PRICING[model][phase]
    return sum((u.get("promptTokenCount") or 0) / 1e6 * p_in +
               ((u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0)) / 1e6 * p_out
               for u in usages)


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def _judge_section(results, template):
    rs = [r for r in results if r.get("ok") and (template is None or r["template"] == template)]
    title = {"hot": "三軸", "digest": "彙整", None: "全部"}[template]
    wins = {INCUMBENT: 0, CHALLENGER: 0, "tie": 0}
    for r in rs:
        wins[r["winner"]] += 1
    lines = [f"### {title}：有效裁決 {len(rs)} 次", "", "| 勝方 | 次數 | 佔比 |", "|---|---|---|"]
    lines += [f"| {m} | {wins[m]} | {wins[m] / max(1, len(rs)) * 100:.0f}% |" for m in (INCUMBENT, CHALLENGER, "tie")]
    by_pair = {}
    for r in rs:
        by_pair.setdefault((r["report"], r["run"]), {})[r["order"]] = r["winner"]
    both = [v for v in by_pair.values() if len(v) == 2]
    first = sum(1 for r in rs if r["winner"] == r["A_model"])
    lines += ["", f"位置一致：兩個位置都有效的 {len(both)} 對裡，{sum(1 for v in both if v['inc_first'] == v['chal_first'])} 對判同一個勝方；"
              f"排在 A 的那份勝 {first} 次、排在 B 的勝 {sum(1 for r in rs if r['winner'] == r['B_model'])} 次。"]
    if template is not None:
        lines += ["", f"| 軸 | `{INCUMBENT}` | `{CHALLENGER}` | 差（carbon − 3.8） |", "|---|---|---|---|"]
        for ax in AXES[template]:
            mi = mean([r["scores"][INCUMBENT][ax] for r in rs])
            mc = mean([r["scores"][CHALLENGER][ax] for r in rs])
            lines.append(f"| {ax} | {mi:.2f} | {mc:.2f} | {mc - mi:+.2f} |")
    return lines + [""]


def report():
    reports = _load("inputs.json")["reports"]
    runs = {m: _load(_run_name(m))["per_report"] for m in RUN_MODELS}
    jname = f"q_judge{SUFFIX}.json"
    jd = _load(jname)["results"] if os.path.exists(_p(jname)) else []
    cfg = (f"carbon 的輸出上限 {CARBON_MAX_OUT}、timeout {CARBON_TIMEOUT} 秒（prod 是 8192、120 秒）；3.8 照 prod"
           if CARBON_MAX_OUT else "兩個模型都照 prod 的呼叫設定（輸出上限 8192、timeout 120 秒）")
    L = [f"# 品質 A/B：`{INCUMBENT}` 對 `{CHALLENGER}`（018 重播素材）", "",
         f"{len(reports)} 份已發布報告的重建輸入 · 現行指令 · temp 0.2 · 每模型每份 {N_RUNS} 次 · "
         f"judge=`{JUDGE}`（非參賽、盲評、位置對調）", "", f"呼叫設定：{cfg}。", "",
         "## Gate：check_report() 逐次計數（未經逐條判定；`date_unlabeled` 已知誤判多，見 README）", "",
         "| 報告 | 模型 | run | " + " | ".join(CHECK_NAMES) + " | 錯誤 |", "|---|---|---|" + "---|" * (len(CHECK_NAMES) + 1)]
    totals = {m: {c: 0 for c in CHECK_NAMES} for m in RUN_MODELS}
    for key in reports:
        for m in RUN_MODELS:
            for i, rec in enumerate(runs[m][key], 1):
                counts = rec.get("counts") or {}
                for c in CHECK_NAMES:
                    totals[m][c] += counts.get(c, 0)
                cells = " | ".join("—" if "error" in rec else str(counts.get(c, 0)) for c in CHECK_NAMES)
                L.append(f"| {key} | {m} | {i} | {cells} | {rec.get('error', '')} |")
    for m in RUN_MODELS:
        L.append(f"| **合計** | {m} | | " + " | ".join(str(totals[m][c]) for c in CHECK_NAMES) + " | |")
    L += ["", "## 盲評", ""]
    invalid = sum(1 for r in jd if not r.get("ok"))
    L += [f"裁決 {len(jd)} 次，無法解析 {invalid} 次。", ""]
    for t in ("hot", "digest", None):
        L += _judge_section(jd, t)
    L += ["## 成本、延遲與長度（實測）", "",
          "| model | 模板 | 生成 | 失敗 | MAX_TOKENS | 超過 120 秒 | modelVersion | $/報告 now | $/報告 later | 均 thinking | 均秒數 | 均字數 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    per_report = {}
    for m in RUN_MODELS:
        for t in ("hot", "digest"):
            recs = [x for key, r in reports.items() if r["template"] == t for x in runs[m][key]]
            ok = [x for x in recs if "error" not in x]
            us = [x["usage"] for x in ok]
            per_report[(m, t)] = {ph: _usd(m, us, ph) / max(1, len(us)) for ph in ("now", "later")}
            mvs = sorted({x.get("modelVersion") or "—" for x in recs})
            cut = sum(1 for x in recs if x.get("finishReason") == "MAX_TOKENS")
            slow = sum(1 for x in recs if x["seconds"] > 120)
            L.append(f"| `{m}` | {t} | {len(recs)} | {len(recs) - len(ok)} | {cut} | {slow} | {', '.join(mvs)} | "
                     f"${per_report[(m, t)]['now']:.4f} | ${per_report[(m, t)]['later']:.4f} | "
                     f"{mean([u.get('thoughtsTokenCount') or 0 for u in us]):.0f} | "
                     f"{mean([x['seconds'] for x in ok]):.1f} | {mean([len(x['text']) for x in ok]):.0f} |")
    j_us = [r.get("usage") or {} for r in jd]
    L += ["", f"裁判 {len(jd)} 次呼叫成本：${_usd(JUDGE, j_us, 'now'):.4f}（`{JUDGE}`）", ""]
    if os.path.exists(_p(f"ffxiv_cost{SUFFIX}.json")):
        fc, fs = _load(f"ffxiv_cost{SUFFIX}.json"), _load("ffxiv_sample.json")
        L += ["## FFXIV analyze_article 的成本（實測小樣本，不評品質）", "",
              f"樣本：{fs['frozen_at'][:16]}Z 即時抓取，篩選後 {fs['n_selected']} 篇取前 {len(fs['articles'])} 篇。", "",
              "| model | 呼叫 | 失敗 | 均 in | 均 out+thinking | 均秒數 | $/篇 now | $/篇 later |", "|---|---|---|---|---|---|---|---|"]
        per_article = {}
        for m in RUN_MODELS:
            rows = fc.get(m, [])
            us = [x["usage"] for x in rows]
            per_article[m] = {ph: _usd(m, us, ph) / max(1, len(us)) for ph in ("now", "later")}
            L.append(f"| `{m}` | {len(rows)} | {sum(1 for x in rows if not x['ok'])} | "
                     f"{mean([u.get('promptTokenCount') or 0 for u in us]):.0f} | "
                     f"{mean([(u.get('candidatesTokenCount') or 0) + (u.get('thoughtsTokenCount') or 0) for u in us]):.0f} | "
                     f"{mean([x['seconds'] for x in rows]):.1f} | "
                     f"${per_article[m]['now']:.4f} | ${per_article[m]['later']:.4f} |")
        L += ["", "## 換模型後每月的生成成本（全部呼叫端，上界）", "",
              f"每週呼叫次數：熱點＋彙整 {WEEKLY_CALLS['hot_or_digest']}（近週上界）、FFXIV {WEEKLY_CALLS['ffxiv_article']}"
              "（`ffxiv.max_selected`）；熱點與彙整的單次成本取兩種模板的平均；auto-KB 沒量。", "",
              "| model | 月成本 now | 月成本 later |", "|---|---|---|"]
        for m in RUN_MODELS:
            row = []
            for ph in ("now", "later"):
                hd = mean([per_report[(m, t)][ph] for t in ("hot", "digest")])
                wk = hd * WEEKLY_CALLS["hot_or_digest"] + per_article[m][ph] * WEEKLY_CALLS["ffxiv_article"]
                row.append(f"${wk * WEEKS_PER_MONTH:.3f}")
            L.append(f"| `{m}` | {row[0]} | {row[1]} |")
        L.append("")
    L += ["## 逐份並排（各取 run1）＋ judge 理由", ""]
    for key, r in reports.items():
        L += [f"### {key}（{r['template']}，{len(r['articles'])} 篇）", ""]
        for m in RUN_MODELS:
            rec = runs[m][key][0]
            L += [f"#### ── {m}（run1）──", "", rec.get("text") or f"（失敗：{rec.get('error')}）", ""]
        L.append("**judge 理由：**")
        L += [f"- run{x['run']} [{x['order']}] 勝：{x['winner']} — {x.get('reason', '')}"
              for x in jd if x["report"] == key and x.get("ok")]
        L.append("")
    with open(_p(f"q_report{SUFFIX}.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"REPORT {_p(f'q_report{SUFFIX}.md')}", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    _budget["left"] = int(sys.argv[2]) if len(sys.argv) > 2 else None
    steps = {"inputs": inputs, "run": run, "judge": judge, "ffxiv_freeze": ffxiv_freeze,
             "ffxiv_cost": ffxiv_cost, "report": report}
    for f in (steps.values() if cmd == "all" else [steps[cmd]]):
        f()
    print("DONE", flush=True)
