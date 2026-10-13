#!/usr/bin/env python3
"""週報 digest 池內的近似重複：餘弦 ≥ threshold 且發布差 < 24h 的對（GNS-20261005-nwn 驗證點 A）。
池從週報 log 還原（同 `replay_digest_pool.py`），再拉 embedding 兩兩比。唯讀，需要 `gh`。"""
import argparse
import itertools
import os
import sys

_REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.analyzer import _cosine_similarity, _parse_embedding, _published_at  # noqa: E402

MAX_GAP_HOURS = 24.0


def near_dup_pairs(rows: list, threshold: float, max_gap_hours: float = MAX_GAP_HOURS) -> list:
    """回傳 (餘弦, 發布差小時, 列 a, 列 b)，餘弦由高到低。缺向量或時區的列不判（數量見 `unjudgeable`）。"""
    judged = [(r, _parse_embedding(r.get("embedding")), _published_at(r.get("published"))) for r in rows]
    judged = [(r, e, p) for r, e, p in judged if e is not None and p is not None]
    pairs = []
    for (a, ea, pa), (b, eb, pb) in itertools.combinations(judged, 2):
        cos, gap_h = _cosine_similarity(ea, eb), abs((pa - pb).total_seconds()) / 3600
        if cos >= threshold and gap_h < max_gap_hours:
            pairs.append((cos, gap_h, a, b))
    return sorted(pairs, key=lambda p: -p[0])


def unjudgeable(rows: list) -> dict:
    no_emb = sum(1 for r in rows if _parse_embedding(r.get("embedding")) is None)
    no_pub = sum(1 for r in rows
                 if _parse_embedding(r.get("embedding")) is not None and _published_at(r.get("published")) is None)
    return {"缺向量": no_emb, "缺時區或發布時間": no_pub}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_id", help="週報的 GitHub Actions run id")
    ap.add_argument("--category", default="道安政策", help="digest 主類別")
    ap.add_argument("--threshold", type=float, default=None,
                    help="預設讀 pipeline_config 的 embed_dedup.threshold")
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(os.path.join(_REPO, ".env"))
    import replay_digest_pool as rp
    from src.storage import _get_client

    threshold = args.threshold
    if threshold is None:
        from src.pipeline_config import load_pipeline_config
        threshold = load_pipeline_config().get("embed_dedup", {}).get("threshold", 0.88)

    links = rp.links_from_log(args.run_id, rp.DEFAULT_REPO, args.category)
    client = _get_client()
    rows = []
    for i in range(0, len(links), rp.BATCH):
        rows += (
            client.table("articles")
            .select("id,link,title,source,published,embedding")
            .in_("link", links[i:i + rp.BATCH])
            .execute()
        ).data or []

    pairs = near_dup_pairs(rows, threshold)
    skipped = unjudgeable(rows)
    for cos, gap_h, a, b in pairs:
        print(f"  {cos:.4f} 發布差 {gap_h:.1f}h")
        for r in (a, b):
            print(f"     id={r['id']} {(r.get('title') or '')[:50]} [{r.get('source')}]")
    print(f"池內近似重複（餘弦 ≥ {threshold:.2f} 且發布差 < {MAX_GAP_HOURS:.0f}h）：{len(pairs)} 對"
          f"（log 連結 {len(links)}、DB 取回 {len(rows)}；不判：{skipped}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
