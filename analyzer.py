"""
analyzer.py
使用 Gemini REST API 對每篇新聞進行摘要 + 深度分析
（直接用 requests，不依賴 google-generativeai SDK，相容 Python 3.8+）
"""

import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

GEMINI_MODEL = os.environ.get("GEMINI_MODEL_NAME", "gemini-2.5-flash")
logger.debug("使用 Gemini 模型：%s", GEMINI_MODEL)
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={api_key}"
)

SYSTEM_PROMPT = (
    "你是台灣交通新聞分析師，專精機車議題（含白牌普通重型機車、紅黃牌大型重型機車）。"
    "請用繁體中文回應，語氣客觀專業，適合台灣機車騎士閱讀。"
    "回應格式務必嚴格按照指示，不要加入任何額外說明或 markdown 符號。"
)

# 明確要求每個欄位用「標籤：內容」單行格式，避免 Gemini 換行導致解析失敗
ANALYSIS_PROMPT_TEMPLATE = """以下是一則台灣交通相關新聞：

標題：{title}
來源：{source}
原始摘要：{summary}
連結：{link}

請依照以下格式回應，每個欄位必須在同一行內完成，不可換行：

摘要：用2到3句話說明事件核心是什麼、涉及哪些對象（同一行寫完，句子之間用「。」分隔）
分析：用4到6句話分析背景原因、對機車騎士的實際影響、政策趨勢或值得關注的面向（同一行寫完，句子之間用「。」分隔）
重要性：高（或中或低，只填一個字）
重要性原因：一句話說明為何如此評定（同一行寫完）
"""


def _get_api_key():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY 環境變數未設定")
    return key


def _call_gemini(prompt, api_key, retries=3):
    url = GEMINI_API_URL.format(model=GEMINI_MODEL, api_key=api_key)
    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2048,  # 足夠容納 4-6 句中文分析（含 Gemini 思考 token 佔用）
        },
    }

    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                candidate = data["candidates"][0]
                finish_reason = candidate.get("finishReason", "")
                if finish_reason == "MAX_TOKENS":
                    logger.warning("⚠️  輸出被截斷（MAX_TOKENS），考慮降低 max_articles 或提高 maxOutputTokens")
                text = candidate["content"]["parts"][0]["text"]
                return text
            elif resp.status_code == 429:
                wait = 15 * attempt
                logger.warning("Rate limit（429），等待 %d 秒後重試（第 %d 次）", wait, attempt)
                time.sleep(wait)
            else:
                logger.warning("Gemini API 回應 %s: %s", resp.status_code, resp.text[:200])
                time.sleep(3)
        except requests.RequestException as e:
            logger.warning("請求失敗（第 %d 次）：%s", attempt, e)
            time.sleep(5)

    return None


def _parse_response(text):
    """
    解析 Gemini 回傳的固定格式文字。
    支援單行格式（正常）和多行 fallback（Gemini 偶爾換行時）。
    """
    result = {
        "summary": "",
        "analysis": "",
        "importance": "中",
        "importance_reason": "",
    }

    # 先嘗試單行比對
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("摘要："):
            result["summary"] = line[3:].strip()
        elif line.startswith("分析："):
            result["analysis"] = line[3:].strip()
        elif line.startswith("重要性："):
            val = line[4:].strip()
            # 只取第一個字，避免「高（因為...）」這類格式干擾
            if val and val[0] in ("高", "中", "低"):
                result["importance"] = val[0]
        elif line.startswith("重要性原因："):
            result["importance_reason"] = line[6:].strip()

    # fallback：若分析欄位仍為空，嘗試多行合併
    # 找到「分析：」標籤後，把直到下一個已知標籤前的所有行合併
    if not result["analysis"]:
        lines = text.splitlines()
        collecting = False
        buf = []
        known_tags = ("摘要：", "重要性：", "重要性原因：")
        for line in lines:
            line = line.strip()
            if line.startswith("分析："):
                collecting = True
                remainder = line[3:].strip()
                if remainder:
                    buf.append(remainder)
            elif collecting:
                if any(line.startswith(t) for t in known_tags) or not line:
                    break
                buf.append(line)
        if buf:
            result["analysis"] = "".join(buf)

    # 同樣對摘要做多行 fallback
    if not result["summary"]:
        lines = text.splitlines()
        collecting = False
        buf = []
        known_tags = ("分析：", "重要性：", "重要性原因：")
        for line in lines:
            line = line.strip()
            if line.startswith("摘要："):
                collecting = True
                remainder = line[3:].strip()
                if remainder:
                    buf.append(remainder)
            elif collecting:
                if any(line.startswith(t) for t in known_tags) or not line:
                    break
                buf.append(line)
        if buf:
            result["summary"] = "".join(buf)

    # 最終 fallback：直接把整段回應當摘要
    if not result["summary"] and text:
        result["summary"] = text[:300]

    return result


def analyze_article(article, api_key):
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        title=article.get("title", ""),
        source=article.get("source", ""),
        summary=article.get("summary", "（無摘要）"),
        link=article.get("link", ""),
    )

    raw = _call_gemini(prompt, api_key)

    if raw:
        article["analysis"] = _parse_response(raw)
        logger.info("✓ 分析完成：%s...", article["title"][:30])
    else:
        logger.warning("✗ 分析失敗：%s", article["title"][:30])
        article["analysis"] = {
            "summary": "（分析失敗）",
            "analysis": "（分析失敗）",
            "importance": "中",
            "importance_reason": "（無法取得分析）",
        }

    return article


def analyze_all(articles, delay=6):
    """
    依序分析所有文章。
    delay: 每次請求間隔秒數。
      gemini-2.5-flash（預設）:  10 RPM → delay=6s
      gemini-2.5-flash-lite:     15 RPM → delay=4s
      gemini-2.5-pro:             5 RPM → delay=12s
      ⚠️  gemini-2.0-flash/lite: 2026/6/1 停用，請勿使用
    """
    api_key = _get_api_key()
    total = len(articles)
    eta_min = round(total * delay / 60, 1)
    logger.info("=== 開始 AI 分析，共 %d 篇（間隔 %ds，預估 %.1f 分鐘）===",
                total, delay, eta_min)

    results = []
    for i, article in enumerate(articles):
        remaining = total - i - 1
        logger.info("[%d/%d] 分析中（完成後還剩 %d 篇，約 %.0f 秒）：%s",
                    i + 1, total, remaining,
                    remaining * delay,
                    article["title"][:40])
        result = analyze_article(article, api_key)
        results.append(result)
        if i < total - 1:
            time.sleep(delay)

    order = {"高": 0, "中": 1, "低": 2}
    results.sort(key=lambda x: order.get(x.get("analysis", {}).get("importance", "中"), 1))

    logger.info("=== AI 分析完成 ===")
    return results