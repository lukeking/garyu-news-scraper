"""
backfill_supabase.py
一次性執行腳本：將 docs/data/ 下既有的週別 JSON 補入 Supabase。

使用方式（本機執行）：
    # 先確認 .env 中有 SUPABASE_URL 和 SUPABASE_KEY
    python backfill_supabase.py

    # 或直接帶環境變數：
    SUPABASE_URL=https://xxxx.supabase.co SUPABASE_KEY=your_key python backfill_supabase.py

    # 指定特定週：
    python backfill_supabase.py --week 2026-W18

    # 乾跑（只顯示會匯入哪些週，不實際寫入）：
    python backfill_supabase.py --dry-run
"""

import json
import glob
import argparse
import sys
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="將既有 JSON 週報資料匯入 Supabase")
    parser.add_argument("--week", help="只匯入指定週，例如 2026-W18")
    parser.add_argument("--dry-run", action="store_true", help="乾跑模式，不實際寫入")
    args = parser.parse_args()

    # 載入 .env（若存在）
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logger.info("已載入 .env")
    except ImportError:
        pass

    # 確認 storage 可用
    try:
        from storage import is_configured, upsert_articles
    except ImportError:
        logger.error("找不到 storage.py，請確認檔案存在於同一目錄")
        sys.exit(1)

    if not is_configured():
        logger.error("SUPABASE_URL 或 SUPABASE_KEY 未設定，請先設定環境變數或 .env")
        sys.exit(1)

    # 找出所有週別 JSON
    data_dir = Path(__file__).parent / "docs" / "data"
    if args.week:
        pattern = str(data_dir / f"{args.week}.json")
    else:
        pattern = str(data_dir / "????-W??.json")

    json_files = sorted(glob.glob(pattern))

    if not json_files:
        logger.warning("找不到符合的 JSON 檔案：%s", pattern)
        sys.exit(0)

    logger.info("找到 %d 個週別 JSON 檔案", len(json_files))

    total_articles = 0
    success_weeks = []
    failed_weeks = []

    for path in json_files:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("讀取 %s 失敗：%s", path, e)
            failed_weeks.append(path)
            continue

        week_id = data.get("week_id", "unknown")
        articles = data.get("articles", [])
        count = len(articles)

        if args.dry_run:
            logger.info("[乾跑] %s：%d 篇（不寫入）", week_id, count)
            success_weeks.append(week_id)
            total_articles += count
            continue

        logger.info("匯入 %s：%d 篇...", week_id, count)
        try:
            written = upsert_articles(articles, week_id)
            logger.info("  ✓ %s 完成，寫入 %d 筆", week_id, written)
            success_weeks.append(week_id)
            total_articles += count
        except Exception as e:
            logger.error("  ✗ %s 失敗：%s", week_id, e)
            failed_weeks.append(week_id)

    # 摘要
    print("\n" + "=" * 50)
    mode = "（乾跑）" if args.dry_run else ""
    print(f"匯入完成{mode}")
    print(f"  成功：{len(success_weeks)} 週，共 {total_articles} 篇文章")
    if failed_weeks:
        print(f"  失敗：{len(failed_weeks)} 週 → {failed_weeks}")
    print("=" * 50)


if __name__ == "__main__":
    main()