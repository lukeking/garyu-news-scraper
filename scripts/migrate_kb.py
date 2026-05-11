"""
One-time migration: parse knowledge-base.md and upsert all rows into the
Supabase `knowledge_base` table.

Usage:
    python scripts/migrate_kb.py

Requires:
    SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables.
    knowledge-base.md present in the repository root.

Idempotent: safe to re-run; upsert on jp_term skips existing rows.
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    loaded = load_dotenv(override=False)
    if loaded:
        print("[dotenv] 已載入 .env（本機測試模式）", flush=True)
except ImportError:
    pass


def parse_kb_md(path: str) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|"):
                continue
            # Skip header row (starts with "| JP") and separator rows
            inner = line.strip("|")
            if inner.replace("-", "").replace("|", "").replace(" ", "") == "":
                continue
            parts = [p.strip() for p in inner.split("|")]
            if len(parts) < 4 or not parts[0] or parts[0].startswith("JP"):
                continue
            rows.append({
                "jp_term": parts[0],
                "tw_term": parts[1] if len(parts) > 1 else "",
                "en_term": parts[2] if len(parts) > 2 else "",
                "category": parts[3] if len(parts) > 3 else "",
                "notes": parts[4] if len(parts) > 4 else "",
                "auto_generated": False,
            })
    return rows


def main() -> None:
    kb_path = os.path.join(os.path.dirname(__file__), "..", "knowledge-base.md")
    kb_path = os.path.normpath(kb_path)

    if not os.path.exists(kb_path):
        logger.error("找不到 knowledge-base.md：%s", kb_path)
        sys.exit(1)

    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()
    if not url or not key:
        logger.error("請設定 SUPABASE_URL 和 SUPABASE_SERVICE_ROLE_KEY 環境變數")
        sys.exit(1)

    rows = parse_kb_md(kb_path)
    if not rows:
        logger.error("knowledge-base.md 中沒有可解析的術語資料列")
        sys.exit(1)

    logger.info("解析完成：%d 個術語", len(rows))

    from supabase import create_client
    client = create_client(url, key)

    result = client.table("knowledge_base").upsert(rows, on_conflict="jp_term").execute()
    upserted = len(result.data) if result.data else 0
    logger.info("遷移完成：%d 個術語已寫入 Supabase knowledge_base 表格", upserted)


if __name__ == "__main__":
    main()
