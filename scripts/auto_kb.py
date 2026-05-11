"""
Auto-KB expansion job.

Collects [[term]] markers from Supabase FFXIV articles, resolves unknown terms
via a single Gemini batch call, writes high-confidence results to the
knowledge_base table, and patches the source articles inline.

Always exits 0 — failures are logged and non-blocking.
"""
import json
import logging
import os
import re
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MARKER_RE = re.compile(r"\[\[([^\]]+)\]\]")

SYSTEM_PROMPT = "你是 FFXIV 術語翻譯專家，專精繁體中文（台灣）玩家社群用語。"

USER_PROMPT_TMPL = """\
以下是尚未收錄於知識庫的 FFXIV 術語，請為每個術語提供繁體中文（台灣）翻譯。

規則：
1. 只回傳你有高把握的術語（來源：官方 TW 補丁說明 > TW 維基/社群慣用）
2. 對沒把握或資訊不足的術語，直接省略，不要猜測
3. 回傳嚴格 JSON 陣列格式，每個元素包含：jp_term, tw_term, en_term, category, notes
4. category 必須是以下之一：遊戲、資料片、資料片縮寫、副本、副本縮寫、職能、職業、技能、道具、貨幣、地區、系統、機制、角色
5. 若無任何把握的術語，回傳空陣列 []

待翻譯術語（每行一個）：
{terms_list}

回傳格式範例：
[
  {{"jp_term": "暁月のフィナーレ", "tw_term": "曉月", "en_term": "Endwalker", "category": "資料片", "notes": "6.0（2021）"}}
]
"""


def call_gemini(terms: list[str], api_key: str, model_name: str) -> list[dict]:
    terms_list = "\n".join(terms)
    user_prompt = USER_PROMPT_TMPL.format(terms_list=terms_list)

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}"
        f":generateContent?key={api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
    }

    for attempt in range(3):
        try:
            import requests as req
            resp = req.post(url, json=payload, timeout=60)
            if resp.status_code >= 500:
                logger.warning("Gemini 回應 %d，第 %d 次重試", resp.status_code, attempt + 1)
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            raw = resp.json()
            text = raw["candidates"][0]["content"]["parts"][0]["text"]
            # Strip markdown code fences if present
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
            return json.loads(text)
        except Exception as exc:
            logger.warning("Gemini 呼叫失敗（第 %d 次）：%s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2 ** attempt)

    logger.error("Gemini 所有重試均失敗，跳過本次 KB 擴充")
    return []


def main() -> None:
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()
    gemini_api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    gemini_model = (os.environ.get("GEMINI_MODEL_NAME") or "gemini-2.5-flash").strip()

    if not url or not key:
        logger.error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 未設定，中止")
        sys.exit(0)
    if not gemini_api_key:
        logger.error("GEMINI_API_KEY 未設定，中止")
        sys.exit(0)

    from supabase import create_client
    supabase = create_client(url, key)

    # Step 1 — load existing KB terms
    try:
        kb_result = supabase.table("knowledge_base").select("jp_term, tw_term").execute()
        existing_terms: set[str] = {row["jp_term"] for row in kb_result.data}
        logger.info("知識庫現有術語：%d 個", len(existing_terms))
    except Exception as exc:
        logger.error("無法讀取 knowledge_base 表格：%s", exc)
        sys.exit(0)

    # Step 2 — collect [[term]] misses from FFXIV articles
    try:
        articles_result = (
            supabase.table("articles")
            .select("id, analysis")
            .eq("content_type", "ffxiv")
            .like("analysis::text", "%[[%")
            .execute()
        )
        article_rows = articles_result.data or []
    except Exception as exc:
        logger.error("無法查詢 articles 表格：%s", exc)
        sys.exit(0)

    unknown_terms: set[str] = set()
    for row in article_rows:
        text = json.dumps(row.get("analysis") or {})
        for m in MARKER_RE.finditer(text):
            term = m.group(1).strip()
            if term not in existing_terms:
                unknown_terms.add(term)

    if not unknown_terms:
        logger.info("沒有未知術語需要解析，結束")
        sys.exit(0)

    logger.info("發現未知術語 %d 個：%s", len(unknown_terms), ", ".join(sorted(unknown_terms)))

    # Step 3 — call Gemini
    gemini_entries = call_gemini(list(unknown_terms), gemini_api_key, gemini_model)

    # Step 4 — insert valid entries
    newly_added: dict[str, str] = {}  # jp_term -> tw_term
    for entry in gemini_entries:
        jp = (entry.get("jp_term") or "").strip()
        tw = (entry.get("tw_term") or "").strip()
        if not jp or not tw:
            logger.warning("[KB AUTO-MISS] 跳過無效 Gemini 回應項目：%s", entry)
            continue
        if jp in existing_terms:
            logger.info("術語 %s 已存在，跳過", jp)
            continue
        try:
            supabase.table("knowledge_base").insert({
                "jp_term": jp,
                "tw_term": tw,
                "en_term": entry.get("en_term") or "",
                "category": entry.get("category") or "",
                "notes": entry.get("notes") or "",
                "auto_generated": True,
            }).execute()
            newly_added[jp] = tw
            logger.info("[KB AUTO] 新增術語：%s → %s", jp, tw)
        except Exception as exc:
            logger.warning("無法寫入術語 %s：%s", jp, exc)

    # Step 5 — inline re-resolution
    all_miss_terms: set[str] = set()

    for row in article_rows:
        text = json.dumps(row.get("analysis") or {})
        replaced = False

        def replace_marker(m: re.Match) -> str:
            nonlocal replaced
            term = m.group(1).strip()
            if term in newly_added:
                replaced = True
                return newly_added[term]
            return m.group(0)

        patched_text = MARKER_RE.sub(replace_marker, text)

        if replaced:
            try:
                patched_analysis = json.loads(patched_text)
                supabase.table("articles").update({"analysis": patched_analysis}).eq("id", row["id"]).execute()
                logger.info("文章 %s 已內聯修補術語", row["id"])
            except Exception as exc:
                logger.warning("無法更新文章 %s：%s", row["id"], exc)

        # collect still-unresolved terms in this article
        for m in MARKER_RE.finditer(patched_text):
            all_miss_terms.add(m.group(1).strip())

    if all_miss_terms:
        logger.warning("========== ⚠️  KB AUTO-MISS 術語待審查 ==========")
        logger.warning("以下術語在本次 Gemini 解析中無法確認翻譯：")
        for t in sorted(all_miss_terms):
            logger.warning("  • %s", t)
        logger.warning("術語已顯示於 FFXIV 頁面術語池，等待知識庫收錄。")
        logger.warning("==============================================")

    logger.info("Auto-KB 完成：新增 %d 個術語，%d 個術語仍待審查",
                len(newly_added), len(all_miss_terms))


if __name__ == "__main__":
    main()
