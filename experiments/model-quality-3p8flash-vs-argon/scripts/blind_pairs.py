"""
Blind the 3.8-flash vs argon pair for the cross-family check (Claude in-session).
Writes data/spot_blind.md (sources + two reports per bucket labelled X / Y in random
order) and data/spot_key.json (which label is which model). The checker reads only the
.md, writes its verdicts to data/spot_claude.md, and only then opens the key and q_report.md.
PR #90's check was label-visible; this one is not.
Usage: blind_pairs.py [run index, default 1]
"""
import json, os, secrets, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
PREV = os.path.join(os.path.dirname(HERE), "model-quality-3p6flash-vs-3p7flash/data")
MODELS = ["gemini-3.8-flash", "gemini-4-argon"]

run = int(sys.argv[1]) if len(sys.argv) > 1 else 1
snap = json.load(open(os.path.join(PREV, "q_snapshot.json")))
runs = {m: json.load(open(os.path.join(DATA, f"q_run_{m.replace('.', '_')}.json")))["per_bucket"] for m in MODELS}
key, L = {}, [f"# 盲評：每桶兩份報告（run{run}），X／Y 隨機對應模型", ""]
for b in snap["buckets"]:
    order = MODELS[:] if secrets.randbelow(2) == 0 else MODELS[::-1]
    key[b["key"]] = {"X": order[0], "Y": order[1]}
    L += [f"## {b['key']} — {b['label']}", "", "**來源（查核文本依據）**", ""]
    L += [f"[{i}] {a['title']}｜{a['summary']}" for i, a in enumerate(b["inputs"], 1)]
    for label, m in (("X", order[0]), ("Y", order[1])):
        L += ["", f"### 報告 {label}", "", runs[m][b["key"]][run - 1]["report"] or "(空)"]
    L.append("")
open(os.path.join(DATA, "spot_blind.md"), "w").write("\n".join(L))
json.dump({"run": run, "key": key}, open(os.path.join(DATA, "spot_key.json"), "w"), ensure_ascii=False, indent=2)
print("WROTE spot_blind.md and spot_key.json (do not open the key before writing verdicts)")
