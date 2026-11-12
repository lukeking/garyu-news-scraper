"""跨家族抽查用：把 3.8 對 carbon（輸出上限 65536）的指定報告隨機標成 X／Y，寫 data/spot_blind.md 與 data/spot_key.json。
抽查者只讀 .md、先把判定寫進 data/spot_claude.md，之後才打開 key 與 q_report_max65536.md。
用法：blind_pairs.py <run 序號> <報告 key> [<報告 key> ...]（報告 key 照 data/inputs.json，例「2026-08-03｜機車事故 · 中時」）"""
import json
import os
import secrets
import sys

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
FILES = {"gemini-3.8-flash": "q_run_gemini-3_8-flash.json", "gemini-4-carbon": "q_run_gemini-4-carbon_max65536.json"}

run, keys = int(sys.argv[1]), sys.argv[2:]
runs = {m: json.load(open(os.path.join(DATA, f), encoding="utf-8"))["per_report"] for m, f in FILES.items()}
models = list(FILES)
key, L = {}, [f"# 盲評：每份兩篇報告（run{run}），X／Y 隨機對應模型", ""]
for k in keys:
    order = models[:] if secrets.randbelow(2) == 0 else models[::-1]
    key[k] = {"X": order[0], "Y": order[1]}
    recs = [runs[m][k][run - 1] for m in order]
    if recs[0]["input_text"] != recs[1]["input_text"]:
        sys.exit(f"STOP {k}：兩份的生成輸入不同")
    L += [f"## {k}", "", "**來源（兩份報告的生成輸入，逐字相同）**", "", recs[0]["input_text"]]
    for label, rec in zip(("X", "Y"), recs):
        L += ["", f"### 報告 {label}", "", rec.get("text") or "(空)"]
    L.append("")
with open(os.path.join(DATA, "spot_blind.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(L))
with open(os.path.join(DATA, "spot_key.json"), "w", encoding="utf-8") as f:
    json.dump({"run": run, "key": key}, f, ensure_ascii=False, indent=2)
print("WROTE spot_blind.md and spot_key.json（判定寫完之前不要打開 key）")
