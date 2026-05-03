"""
main.py
台灣機車交通週報主程式入口
執行流程：收集 → 過濾 → AI 分析 → 發布
"""

import logging
import sys
import os

try:
    from dotenv import load_dotenv
    loaded = load_dotenv(override=False)
    if loaded:
        print("[dotenv] 已載入 .env（本機測試模式）", flush=True)
except ImportError:
    pass

from src.collector import collect_all
from src.filter import filter_and_deduplicate
from src.analyzer import analyze_all, get_kb_miss_summary
from src.publisher import publish

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


TRAFFIC_MAX = 20
FFXIV_MAX   = 10


def main():
    logger.info("========== Garyu News Scraper 開始執行 ==========")

    # Step 1：收集新聞（交通 + FFXIV）
    raw_articles = collect_all()
    if not raw_articles:
        logger.warning("未收集到任何文章，結束執行")
        sys.exit(0)

    # Step 2：按 content_type 分流，各自過濾 + 去重複，各自套用篇數上限
    # 分流確保 FFXIV 文章不會被交通文章的數量擠掉
    traffic_raw = [a for a in raw_articles if a.get("content_type", "traffic") == "traffic"]
    ffxiv_raw   = [a for a in raw_articles if a.get("content_type") == "ffxiv"]

    traffic_filtered = filter_and_deduplicate(traffic_raw)
    ffxiv_filtered   = filter_and_deduplicate(ffxiv_raw)

    if len(traffic_filtered) > TRAFFIC_MAX:
        logger.info("交通文章數 %d > %d，截取前 %d 篇", len(traffic_filtered), TRAFFIC_MAX, TRAFFIC_MAX)
        traffic_filtered = traffic_filtered[:TRAFFIC_MAX]
    if len(ffxiv_filtered) > FFXIV_MAX:
        logger.info("FFXIV 文章數 %d > %d，截取前 %d 篇", len(ffxiv_filtered), FFXIV_MAX, FFXIV_MAX)
        ffxiv_filtered = ffxiv_filtered[:FFXIV_MAX]

    filtered = traffic_filtered + ffxiv_filtered
    logger.info("分析篇數：交通 %d + FFXIV %d = %d", len(traffic_filtered), len(ffxiv_filtered), len(filtered))
    if not filtered:
        logger.warning("過濾後無文章，結束執行")
        sys.exit(0)

    # Step 3：AI 分析
    analyzed = analyze_all(filtered)

    # Step 4：發布至 pages/
    publish(analyzed)

    # Step 5：KB MISS 提示 — 若有未知 FFXIV 術語，提醒使用者更新知識庫
    kb_misses = get_kb_miss_summary()
    if kb_misses:
        logger.warning("========== ⚠️  KB MISS 術語待審查 ==========")
        logger.warning("以下術語出現在 FFXIV 分析結果中但未收錄於 knowledge-base.md：")
        for term in kb_misses:
            logger.warning("  • %s", term)
        logger.warning("請更新 knowledge-base.md 後提交 PR，避免下次執行再次出現 [[term]] 標記。")
        logger.warning("==============================================")

    logger.info("========== 執行完成 ==========")



if __name__ == "__main__":
    main()