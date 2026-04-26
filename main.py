"""
main.py
台灣機車交通週報主程式入口
執行流程：收集 → 過濾 → AI 分析 → 寄送
"""

import logging
import sys
import os

# load_dotenv 必須在所有其他 import 之前執行，
# 這樣 collector / analyzer / mailer 讀取 os.environ 時環境變數已就緒。
#
# override=False（預設值）：已存在的環境變數不會被 .env 覆蓋。
# 效果：
#   本機測試 → 系統環境變數為空，.env 的值生效
#   GitHub Actions → secrets 已注入為環境變數，.env 不存在，完全不影響
try:
    from dotenv import load_dotenv
    loaded = load_dotenv(override=False)
    if loaded:
        print("[dotenv] 已載入 .env（本機測試模式）", flush=True)
except ImportError:
    pass  # production 環境不需要安裝 python-dotenv 也能正常運作

from collector import collect_all
from filter import filter_and_deduplicate
from analyzer import analyze_all
from mailer import build_html, send_email

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

    # Step 2：過濾 + 去重複
    filtered = filter_and_deduplicate(raw_articles)
    if not filtered:
        logger.warning("過濾後無文章，結束執行")
        sys.exit(0)

    # Step 3：限制最多 30 篇（避免 API 用量過多）
    if len(filtered) > 30:
        logger.info(f"文章數 {len(filtered)} > 30，截取前 30 篇")
        filtered = filtered[:30]

    # Step 4：AI 分析
    analyzed = analyze_all(filtered)

    # Step 5：組裝 HTML + 寄送
    html = build_html(analyzed)
    send_email(html, len(analyzed))

    logger.info("========== 執行完成 ==========")


if __name__ == "__main__":
    main()