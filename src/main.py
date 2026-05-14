"""
main.py
Garyu News Scraper 主程式入口
執行流程：各 Category 模組依序執行 collect → filter → analyze → publish
"""

import logging
import sys

try:
    from dotenv import load_dotenv
    loaded = load_dotenv(override=False)
    if loaded:
        print("[dotenv] 已載入 .env（本機測試模式）", flush=True)
except ImportError:
    pass

from src.analyzer import get_kb_miss_summary
from src.pipeline.traffic import TrafficCategory
from src.pipeline.ffxiv import FFXIVCategory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

CATEGORIES = [TrafficCategory(), FFXIVCategory()]


def main():
    logger.info("========== Garyu News Scraper 開始執行 ==========")

    all_analyzed = []
    for cat in CATEGORIES:
        try:
            logger.info("--- [%s] 開始處理 ---", cat.name)
            raw      = cat.collect()
            filtered = cat.filter(raw)
            if not filtered:
                logger.info("[%s] 過濾後無文章，跳過", cat.name)
                continue
            analyzed = cat.analyze(filtered)
            cat.publish(analyzed)
            all_analyzed.extend(analyzed)
            logger.info("--- [%s] 完成：%d 篇 ---", cat.name, len(analyzed))
        except Exception as e:
            logger.error("[%s] 處理失敗：%s", cat.name, e)

    if not all_analyzed:
        logger.warning("所有 category 均無文章，結束執行")
        sys.exit(0)

    # KB MISS 提示 — 若有未知 FFXIV 術語，提醒使用者更新知識庫
    kb_misses = get_kb_miss_summary()
    if kb_misses:
        logger.warning("========== ⚠️  KB MISS 術語待審查 ==========")
        logger.warning("以下術語出現在 FFXIV 分析結果中但未收錄於 knowledge-base.md：")
        for term in kb_misses:
            logger.warning("  • %s", term)
        logger.warning("請更新 knowledge-base.md 後提交 PR，避免下次執行再次出現 [[term]] 標記。")
        logger.warning("==============================================")

    logger.info("========== 執行完成，共 %d 篇 ==========", len(all_analyzed))


if __name__ == "__main__":
    main()
