#!/usr/bin/env bash
# CI gating L1：把 tests.yml 的 `unit` check 加進 main 的 ruleset 作為 required status check。
#
# 為什麼要腳本而不是一行 gh api：rulesets 的更新是「整份取代」，手打 JSON 很容易
# 把既有的 deletion / non_fast_forward / pull_request 三條規則連同 conditions 一起蓋掉。
# 這支腳本先讀回現況、只「加」一條規則、再寫回去，並印出前後 diff 讓人確認。
#
# 冪等：重複執行不會加出第二條 required_status_checks。
#
# 用法： bash scripts/enable_ci_gate.sh          # 預覽，不寫入
#        bash scripts/enable_ci_gate.sh --apply  # 實際寫入
set -euo pipefail

REPO="lukeking/garyu-news-scraper"
RULESET_ID=16977362
CONTEXT="unit"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

gh api "repos/$REPO/rulesets/$RULESET_ID" > "$TMP/before.json"

python3 - "$TMP/before.json" "$TMP/payload.json" "$CONTEXT" <<'PY'
import json, sys

src, dst, context = sys.argv[1], sys.argv[2], sys.argv[3]
rs = json.load(open(src))

rules = rs["rules"]
existing = [r for r in rules if r["type"] == "required_status_checks"]
if existing:
    checks = existing[0].setdefault("parameters", {}).setdefault("required_status_checks", [])
    if any(c.get("context") == context for c in checks):
        print(f"SKIP: `{context}` 已經是 required status check，無需變更")
        sys.exit(3)
    checks.append({"context": context})
else:
    rules.append({
        "type": "required_status_checks",
        "parameters": {
            # false = 不要求分支必須是最新的 main 才能 merge。
            # 這個 repo 是 solo，強制 up-to-date 只會製造無謂的 rebase 迴圈。
            "strict_required_status_checks_policy": False,
            "required_status_checks": [{"context": context}],
        },
    })

# rulesets 的更新是整份取代，但只接受這幾個可寫欄位
payload = {
    "name": rs["name"],
    "target": rs["target"],
    "enforcement": rs["enforcement"],
    "conditions": rs["conditions"],
    "bypass_actors": rs.get("bypass_actors", []),
    "rules": rules,
}
json.dump(payload, open(dst, "w"), ensure_ascii=False, indent=2)
print("變更後的規則清單：", ", ".join(r["type"] for r in rules))
PY

if [ "${1:-}" != "--apply" ]; then
    echo
    echo "（預覽模式，未寫入。確認無誤後加上 --apply 重跑。）"
    echo "將送出的 payload："
    cat "$TMP/payload.json"
    exit 0
fi

gh api --method PUT "repos/$REPO/rulesets/$RULESET_ID" --input "$TMP/payload.json" > "$TMP/after.json"

echo
echo "寫入完成。現況："
python3 -c "
import json,sys
d=json.load(open('$TMP/after.json'))
for r in d['rules']:
    if r['type']=='required_status_checks':
        p=r.get('parameters',{})
        print('  required_status_checks:', [c['context'] for c in p.get('required_status_checks',[])])
        print('  strict policy:', p.get('strict_required_status_checks_policy'))
    else:
        print(' ', r['type'])
"
