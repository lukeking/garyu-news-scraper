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

from collector import collect_all
from filter import filter_and_deduplicate
from analyzer import analyze_all
from publisher import publish

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
    logger.info("========== 台灣機車交通週報開始執行 ==========")

    # Step 1：收集新聞
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

    # Step 5：發布至 docs/
    publish(analyzed)

    logger.info("========== 執行完成 ==========")


if __name__ == "__main__":
    main()