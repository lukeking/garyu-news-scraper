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

DEFAULT_TAGS = [
    "法規", "事故", "停車", "路權", "重機", "電動", "考照",
    "國道", "工程", "Gogoro", "白牌", "紅牌", "黃牌", "取締",
    "新制", "道路設計", "交通安全",
]

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
標籤：從以下選項中選2到4個最相關的標籤，用逗號分隔，也可加入未列出但更精確的標籤（同一行寫完）
可選標籤：{available_tags}

---
重要性評定標準（請嚴格遵守，預期分布約：高 30%、中 50%、低 20%）：

【高】滿足以下任一條件：
- 有人員傷亡（死亡或重傷）的交通事故
- 影響全國或多縣市機車族的法規、政策新制（實際上路或立法院通過）
- 重大道路工程設計缺失，直接威脅騎士安全
- 取締專案或重大違規執法（影響範圍廣、罰則重）

【中】滿足以下任一條件：
- 地方性事故（輕傷或財損為主）
- 政策討論、草案、評估階段（尚未定案）
- 道路工程進度更新、爭議討論（無立即安全威脅）
- 新產品/新服務上市對機車族有間接影響
- 違規取締（一般性、地方性）

【低】滿足以下條件：
- 純報導性、無直接影響（如活動、評比、展覽）
- 重複性新聞（同一事件的後續跟進報導、無新資訊）
- 對機車騎士影響極小或高度不確定
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
            "temperature": 0.2,
            "maxOutputTokens": 2048,
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
        "tags": [],
    }

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("摘要："):
            result["summary"] = line[3:].strip()
        elif line.startswith("分析："):
            result["analysis"] = line[3:].strip()
        elif line.startswith("重要性："):
            val = line[4:].strip()
            if val and val[0] in ("高", "中", "低"):
                result["importance"] = val[0]
        elif line.startswith("重要性原因："):
            result["importance_reason"] = line[6:].strip()
        elif line.startswith("標籤："):
            raw_tags = line[3:].strip()
            result["tags"] = [t.strip() for t in raw_tags.replace("、", ",").replace("，", ",").split(",") if t.strip()]

    # fallback：分析欄位多行合併
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

    # fallback：摘要欄位多行合併
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

    if not result["summary"] and text:
        result["summary"] = text[:300]

    return result


def analyze_article(article, api_key):
    user_tags = article.get("user_tags", [])
    all_tags = sorted(set(DEFAULT_TAGS) | set(user_tags))
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        title=article.get("title", ""),
        source=article.get("source", ""),
        summary=article.get("summary", "（無摘要）"),
        link=article.get("link", ""),
        available_tags="、".join(all_tags),
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
            "tags": [],
        }

    return article


def analyze_all(articles, delay=6):
    """
    依序分析所有文章。
    delay: 每次請求間隔秒數。
      gemini-2.5-flash（預設）:  10 RPM → delay=6s
      gemini-2.5-flash-lite:     15 RPM → delay=4s
      gemini-2.5-pro:             5 RPM → delay=12s
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