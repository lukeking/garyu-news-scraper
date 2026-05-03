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


def main():
    logger.info("========== Garyu News Scraper 開始執行 ==========")

    # Step 1：收集新聞（交通 + FFXIV）
    raw_articles = collect_all()
    if not raw_articles:
        logger.warning("未收集到任何文章，結束執行")
        sys.exit(0)

    # Step 2：過濾 + 去重複（含同主題限流）
    filtered = filter_and_deduplicate(raw_articles)
    if not filtered:
        logger.warning("過濾後無文章，結束執行")
        sys.exit(0)

    # Step 3：限制篇數
    # Gemini 2.5 Flash 免費 RPD=20；若已啟用計費可調高
    # 設為 30 保留緩衝，過濾後若不足 20 篇仍有足夠來源
    MAX_ARTICLES = 30
    if len(filtered) > MAX_ARTICLES:
        logger.info(f"文章數 {len(filtered)} > {MAX_ARTICLES}，截取前 {MAX_ARTICLES} 篇")
        filtered = filtered[:MAX_ARTICLES]

    # Step 4：AI 分析
    analyzed = analyze_all(filtered)

    # Step 5：發布至 pages/
    publish(analyzed)

    # Step 6：KB MISS 提示 — 若有未知 FFXIV 術語，提醒使用者更新知識庫
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