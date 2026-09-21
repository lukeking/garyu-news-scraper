#!/usr/bin/env python3
"""一次性：替 embedding 為 null 的 traffic 文章補向量（GNS-013 回填）。預設乾跑，--apply 才寫正式庫。
向量走 attach_embeddings（與 daily 同文字組成、模型、維度）；寫入帶 embedding IS NULL 條件，重跑安全。"""
import argparse
import os
import sys
from urllib.parse import urlparse

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

from src.analyzer import EMBED_DIMENSIONS, attach_embeddings  # noqa: E402


def fetch_missing(sb) -> list:
    rows, page = [], 0
    while True:
        batch = (
            sb.table("articles")
            .select("id,title,summary")
            .eq("content_type", "traffic")
            .is_("embedding", "null")
            .order("id")
            .range(page * 1000, page * 1000 + 999)
            .execute()
            .data
        ) or []
        rows += batch
        if len(batch) < 1000:
            return rows
        page += 1


def backfill(sb, apply: bool, embed=attach_embeddings) -> dict:
    rows = fetch_missing(sb)
    out = {"missing": len(rows), "written": 0, "failed": 0, "skipped_filled": 0}
    print(f"[backfill] embedding 為 null 的 traffic 文章：{len(rows)} 篇")
    if not apply:
        print("[backfill] 乾跑：未呼叫 embedding、未寫入；加 --apply 才執行")
        return out
    # 不帶 embedding 鍵：attach_embeddings 只替缺鍵的 dict 生成，帶著 None 進去會一次都不呼叫。
    candidates = [{"title": r.get("title"), "summary": r.get("summary")} for r in rows]
    embed(candidates)
    for r, c in zip(rows, candidates):
        vec = c.get("embedding")
        if not vec or len(vec) != EMBED_DIMENSIONS:
            out["failed"] += 1
            print(f"[backfill] 略過 id={r['id']}：無有效向量（長度 {len(vec) if vec else 0}）")
            continue
        resp = (
            sb.table("articles").update({"embedding": vec})
            .eq("id", r["id"]).is_("embedding", "null").execute()
        )
        if resp.data:
            out["written"] += 1
        else:
            out["skipped_filled"] += 1
            print(f"[backfill] 未覆寫 id={r['id']}：寫入時已有向量")
    print(f"[backfill] 結果：寫入 {out['written']}／生成失敗 {out['failed']}／"
          f"已有向量未覆寫 {out['skipped_filled']}／共 {out['missing']}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="真的呼叫 embedding 並寫入正式庫")
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(os.path.join(_REPO, ".env"))
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    if args.apply and not (urlparse(url).hostname or "").endswith(".supabase.co"):
        print("[backfill] 拒絕寫入：--apply 只對正式庫（*.supabase.co），.env 指向的不是")
        return 2
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"]
    out = backfill(create_client(url, key), apply=args.apply)
    return 1 if out["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
