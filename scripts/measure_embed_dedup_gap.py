#!/usr/bin/env python3
"""唯讀：量「餘弦相似度已達門檻、卻仍並存在庫裡」的文章對，並歸因原因。

**為什麼需要這支**：STATE.md 從 08-17 起連三週記著「近似重複（`embed_dedup`
threshold 0.88）連同一家媒體的雙 feed 都沒抓到」——那句話把嫌犯指向**門檻**。
2026-09-05 量完發現門檻沒問題：`顏蔚慈交通白皮書` 那組 7 篇的 21 對**全部** ≥ 0.88，
`駕艙機車` 有一對到 0.9813，抓得到，**只是從來沒被比對過**。

真正的成因是**比對窗**（`src/pipeline/traffic.py:111-120`），它只涵蓋兩塊：

  1. `this_week`＝`get_traffic_buffer(max_age_weeks=1)` 再過濾 `week_id == 本週`
     ——而 `get_traffic_buffer` 另外還過濾 `hot_topic_analyzed == False`。
  2. 同一批 candidates 之間。

於是有兩個結構性盲區：**跨週**、以及**已被分析（已消耗）的列**。本腳本量它們各佔多少。

⚠️ **這支不回答「該不該把窗放寬」。** 跨週相似有兩種：同一則新聞的改寫（該去重）
與同一事件的後續進展（不該去重），而餘弦分不出這兩者。放寬窗會連後續進展一起殺掉，
那是要人決定的事，不是這支腳本能決定的。

用法（唯讀，需要 `.env` 裡的 Supabase 設定）：

    .venv/bin/python scripts/measure_embed_dedup_gap.py
    .venv/bin/python scripts/measure_embed_dedup_gap.py --threshold 0.85
"""
import argparse
import math
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

CROSS_WEEK = "跨週（比對範圍外）"
ANALYSED = "同週但至少一篇已分析（比對範圍外）"
REAL_MISS = "同週且兩篇皆未分析（真的漏抓）"


def classify_pair(a: dict, b: dict) -> str:
    """一對已達門檻的文章為什麼還並存？回答的是**比對窗**，不是相似度。

    順序寫死成「先看週別、再看已分析」：跨週的那些即使兩篇都未分析也不會被比對到，
    所以週別是更外層的原因，不能反過來。
    """
    if a.get("week_id") != b.get("week_id"):
        return CROSS_WEEK
    if a.get("hot_topic_analyzed") or b.get("hot_topic_analyzed"):
        return ANALYSED
    return REAL_MISS


def _normalise(vec):
    n = math.sqrt(sum(x * x for x in vec))
    return [x / n for x in vec] if n else None


def _fetch(sb):
    rows, page = [], 0
    while True:
        batch = (
            sb.table("articles")
            .select("id,title,source,week_id,published,hot_topic_analyzed,embedding")
            .eq("content_type", "traffic")
            .range(page * 1000, page * 1000 + 999)
            .execute()
            .data
        ) or []
        rows += batch
        if len(batch) < 1000:
            break
        page += 1
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=None,
                    help="預設讀 pipeline_config 的 embed_dedup.threshold")
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(os.path.join(_REPO, ".env"))
    from supabase import create_client
    from src.analyzer import _parse_embedding

    threshold = args.threshold
    if threshold is None:
        from src.pipeline_config import load_pipeline_config
        threshold = load_pipeline_config().get("embed_dedup", {}).get("threshold", 0.88)

    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"]
    rows = _fetch(create_client(url, key))

    keep = []
    for r in rows:
        e = _parse_embedding(r.get("embedding"))
        if e and len(e) == 768:
            r["_n"] = _normalise(e)
            if r["_n"]:
                keep.append(r)
    print(f"traffic 總數 {len(rows)}，有 768 維嵌入並納入比對 {len(keep)}")

    buckets = {CROSS_WEEK: 0, ANALYSED: 0, REAL_MISS: 0}
    examples: dict[str, list] = {k: [] for k in buckets}
    total = 0
    for i in range(len(keep)):
        a, na = keep[i], keep[i]["_n"]
        for j in range(i + 1, len(keep)):
            cos = sum(x * y for x, y in zip(na, keep[j]["_n"]))
            if cos < threshold:
                continue
            total += 1
            b = keep[j]
            k = classify_pair(a, b)
            buckets[k] += 1
            if len(examples[k]) < 3:
                examples[k].append(
                    f"{cos:.4f} [{a['week_id']}]{(a['title'] or '')[:30]}"
                    f" ↔ [{b['week_id']}]{(b['title'] or '')[:30]}"
                )

    print(f"\n餘弦 ≥ {threshold} 且兩篇都還在庫裡的對數：{total}\n")
    for k in (CROSS_WEEK, ANALYSED, REAL_MISS):
        pct = 100 * buckets[k] / total if total else 0.0
        print(f"  {buckets[k]:5} ({pct:5.1f}%)  {k}")
        for e in examples[k]:
            print(f"           {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
