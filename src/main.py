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

from src import run_mode
from src.analyzer import get_call_counts, get_kb_miss_summary
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
    # 模式先驗：不認得的值在收集之前就丟錯；不能放進下面逐類別的 try，那裡會把例外吞掉
    mode = run_mode.current()
    if run_mode.is_dry_run():
        logger.info(run_mode.start_line())
    start_counts = get_call_counts()
    try:
        _run(mode)
    finally:
        _log_call_counts(start_counts)


def _log_call_counts(start: dict) -> None:
    """不發布時印結尾那一行（這次 main() 送出的請求數）；正式模式什麼都不印。"""
    now = get_call_counts()
    line = run_mode.end_line(now["generative"] - start["generative"], now["embedding"] - start["embedding"])
    if line:
        logger.info(line)


def _run(mode: str) -> None:
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
            if mode == run_mode.DRY_INPUT and cat.llm_stage:
                logger.info(run_mode.stop_line(cat.llm_stage))
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
        logger.warning("以下術語出現在 FFXIV 分析結果中但未收錄於 Supabase knowledge_base 表：")
        for term in kb_misses:
            logger.warning("  • %s", term)
        logger.warning("週報後的 auto-kb job 會收錄有把握的術語；其餘請直接寫進 knowledge_base 表（auto_generated = false），不需要 PR。")
        logger.warning("==============================================")

    logger.info("========== 執行完成，共 %d 篇 ==========", len(all_analyzed))


if __name__ == "__main__":
    main()
