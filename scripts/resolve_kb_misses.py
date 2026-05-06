#!/usr/bin/env python3
"""
KB Miss Re-Resolution Job
Triggered by GitHub Actions when knowledge-base.md is pushed to main.

Queries Supabase for FFXIV articles whose analysis JSONB contains [[term]]
placeholders and resolves them via KB string lookup. Emits a KB MISS warning
(identical format to the main pipeline) for terms still absent from the KB.

Exit code is always 0 — partial resolution is not a failure condition.
"""

import json
import logging
import os
import pathlib
import re
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

MARKER_RE = re.compile(r"\[\[([^\]]+)\]\]")
KB_PATH = pathlib.Path(__file__).parent.parent / "knowledge-base.md"


def load_kb(kb_path: pathlib.Path) -> dict:
    """Parse knowledge-base.md markdown tables into {JP Term: TW Term} dict."""
    mapping = {}
    for line in kb_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or "|---" in line:
            continue
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= 2 and cells[0] != "JP Term":
            mapping[cells[0]] = cells[1]
    return mapping


def _get_client():
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (
        (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        or (os.environ.get("SUPABASE_KEY") or "").strip()
    )
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL 或金鑰未設定。"
            "請設定 secrets：SUPABASE_URL 與 SUPABASE_SERVICE_ROLE_KEY。"
        )
    from supabase import create_client
    return create_client(url, key)


def resolve_analysis(analysis: dict, kb: dict) -> tuple:
    """
    Replace all [[term]] markers in analysis JSON with KB TW terms.
    Returns (updated_analysis, resolved_terms, unresolved_terms).
    """
    text = json.dumps(analysis, ensure_ascii=False)
    found = list(dict.fromkeys(MARKER_RE.findall(text)))  # unique, preserve order

    resolved = []
    unresolved = []
    for term in found:
        if term in kb:
            text = text.replace(f"[[{term}]]", kb[term])
            resolved.append(term)
        else:
            unresolved.append(term)

    return json.loads(text), resolved, unresolved


def main() -> None:
    logger.info("========== KB Miss Re-Resolution Job 開始 ==========")

    if not KB_PATH.exists():
        logger.error("knowledge-base.md 不存在：%s", KB_PATH)
        sys.exit(0)

    kb = load_kb(KB_PATH)
    logger.info("載入知識庫：%d 個詞條", len(kb))

    try:
        client = _get_client()
    except Exception as e:
        logger.error("Supabase 連線失敗：%s", e)
        sys.exit(0)

    # Fetch all FFXIV articles; filter for [[term]] markers in Python.
    # The dataset is small (<1000 rows) so a full SELECT is within free-tier limits.
    try:
        resp = (
            client.table("articles")
            .select("id, title, analysis")
            .eq("content_type", "ffxiv")
            .execute()
        )
        all_articles = resp.data or []
    except Exception as e:
        logger.error("Supabase 查詢失敗：%s", e)
        sys.exit(0)

    articles = [
        a for a in all_articles
        if "[[" in json.dumps(a.get("analysis") or {})
    ]

    if not articles:
        logger.info("無文章含有 [[term]] 標記，無需處理。")
        logger.info("========== KB Miss Re-Resolution Job 結束 ==========")
        return

    logger.info("發現 %d 篇文章含有 [[term]] 標記（共 %d 篇 FFXIV 文章）",
                len(articles), len(all_articles))

    all_unresolved = []
    updated_count = 0

    for article in articles:
        article_id = article["id"]
        title = (article.get("title") or "")[:50]
        analysis = article.get("analysis") or {}

        updated_analysis, resolved, unresolved = resolve_analysis(analysis, kb)
        all_unresolved.extend(unresolved)

        if resolved:
            try:
                client.table("articles").update(
                    {"analysis": updated_analysis}
                ).eq("id", article_id).execute()
                logger.info(
                    "✓ 已解析 %d 個詞條（%s）：%s",
                    len(resolved), "、".join(resolved), title,
                )
                updated_count += 1
            except Exception as e:
                logger.error("✗ 更新失敗（id=%s）：%s — %s", article_id, title, e)

        if unresolved:
            logger.info(
                "  ↳ 仍有 %d 個詞條未解析（%s）：%s",
                len(unresolved), "、".join(unresolved), title,
            )

    logger.info("共更新 %d 篇文章", updated_count)

    # Emit KB MISS warning block — identical format to main pipeline (src/main.py)
    unique_unresolved = list(dict.fromkeys(all_unresolved))
    if unique_unresolved:
        logger.warning("========== ⚠️  KB MISS 術語待審查 ==========")
        logger.warning("以下術語出現在 FFXIV 分析結果中但未收錄於 knowledge-base.md：")
        for term in unique_unresolved:
            logger.warning("  • %s", term)
        logger.warning("請更新 knowledge-base.md 後提交 PR，避免下次執行再次出現 [[term]] 標記。")
        logger.warning("==============================================")

    logger.info("========== KB Miss Re-Resolution Job 結束 ==========")


if __name__ == "__main__":
    main()
