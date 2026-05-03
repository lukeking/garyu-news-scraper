"""
analyzer.py
使用 Gemini REST API 對每篇新聞進行摘要 + 深度分析
支援兩種內容類型：traffic（台灣機車交通）和 ffxiv（FFXIV 遊戲資訊）
（直接用 requests，不依賴 google-generativeai SDK，相容 Python 3.8+）
"""

import os
import re
import time
import logging
import random
import requests

logger = logging.getLogger(__name__)

# GitHub Actions 若設定 GEMINI_MODEL_NAME secret 但留空，get 會得到 "" 而非預設值
GEMINI_MODEL = (os.environ.get("GEMINI_MODEL_NAME") or "").strip() or "gemini-2.5-flash"
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

FFXIV_SYSTEM_PROMPT = (
    "你是 FFXIV（最終幻想XIV）資訊分析師，專精遊戲攻略、版本更新與職業機制。"
    "請用繁體中文回應，語氣客觀專業，適合台灣 FFXIV 玩家閱讀。"
    "回應格式務必嚴格按照指示，不要加入任何額外說明或 markdown 符號。"
    "翻譯遊戲術語時，必須以提供的知識庫為準，不得自行發明未收錄的譯名。"
)

DEFAULT_TAGS = [
    "法規", "事故", "停車", "路權", "重機", "電動", "考照",
    "國道", "工程", "Gogoro", "白牌", "紅牌", "黃牌", "取締",
    "新制", "道路設計", "交通安全",
]

FFXIV_DEFAULT_TAGS = [
    "零式", "絕境戰", "職業調整", "新內容", "版本更新",
    "活動", "修正", "地下城", "討伐戰", "同盟突擊",
    "製作採集", "置房", "裝備", "7.x", "蝮蛇師", "繪靈法師",
]

_KB_CACHE: dict | None = None
_KB_KATAKANA = re.compile(r"[ァ-ヺー]{3,}")

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


FFXIV_ANALYSIS_TEMPLATE = """以下是一則 FFXIV 相關資訊：

標題：{title}
來源：{source}
原始摘要：{summary}
連結：{link}

【FFXIV 知識庫 — 請嚴格使用以下對照翻譯，不得自行發明未收錄的譯名】
{knowledge_base}

請依照以下格式回應，每個欄位必須在同一行內完成，不可換行：

摘要：用2到3句話說明這則資訊的核心內容（同一行寫完，句子之間用「。」分隔）
分析：用4到6句話分析對玩家的實際影響、版本/職業/內容的重要性、值得關注的面向（同一行寫完）
重要性：高（或中或低，只填一個字）
重要性原因：一句話說明為何如此評定（同一行寫完）
標籤：從以下選項中選2到4個最相關的標籤，用逗號分隔，也可加入未列出但更精確的標籤（同一行寫完）
可選標籤：{available_tags}

---
重要性評定標準（請嚴格遵守）：

【高】任一條件：
- 重大版本更新（零式或絕境戰新內容上線、職業重大改版、新資料片）
- 全服公告性重要變更（伺服器異動、系統重大調整）

【中】任一條件：
- 職業平衡調整、限時活動開始/結束
- 一般版本修正、新增 QoL 功能、新裝備

【低】：
- 次要修正、一般公告、對遊戲玩法無直接影響的資訊
"""


def load_knowledge_base(path: str = "knowledge-base.md") -> dict:
    """
    解析 knowledge-base.md 的 Markdown 表格。
    回傳 {jp_term: {"tw": str, "en": str, "category": str}} 的對照字典。
    若檔案不存在或沒有資料列，拋出 RuntimeError。
    結果在模組層級快取，同一程序只讀取一次。
    """
    global _KB_CACHE
    if _KB_CACHE is not None:
        return _KB_CACHE

    if not os.path.exists(path):
        raise RuntimeError(
            f"找不到知識庫檔案：{path}。"
            "請在 knowledge-base.md 中加入 FFXIV 術語對照表後再執行 FFXIV 分析。"
        )

    kb: dict = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|") or line.startswith("| JP") or set(line.replace("|", "").replace("-", "").replace(" ", "")) == set():
                continue
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) < 4 or not parts[0]:
                continue
            kb[parts[0]] = {
                "tw": parts[1] if len(parts) > 1 else "",
                "en": parts[2] if len(parts) > 2 else "",
                "category": parts[3] if len(parts) > 3 else "",
            }

    if not kb:
        raise RuntimeError(
            f"knowledge-base.md 中沒有有效的術語資料列。"
            "請至少加入一列術語對照後再執行 FFXIV 分析。"
        )

    logger.info("知識庫載入完成：%d 個術語", len(kb))
    _KB_CACHE = kb
    return kb


def _check_kb_misses(text: str, kb: dict) -> None:
    """掃描 Gemini 回應中未被知識庫收錄的日文片假名術語，記錄警告供後續 KB 補充。"""
    matches = _KB_KATAKANA.findall(text)
    for match in set(matches):
        if match not in kb:
            logger.warning("[KB MISS] 未知詞彙：%s", match)


def _get_api_key():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY 環境變數未設定")
    return key


def _retry_after_seconds(resp, attempt, status_code):
    """
    503/UNAVAILABLE 常持續數小時至數日（Google 端容量問題），需較長指數退避。
    參考：https://ai.google.dev/gemini-api/docs/troubleshooting
    """
    if resp is not None:
        ra = resp.headers.get("Retry-After")
        if ra:
            try:
                return min(max(int(ra), 1), 120)
            except ValueError:
                pass
    if status_code == 429:
        return min(10 * (2 ** (attempt - 1)), 120)
    if status_code in (500, 502, 503, 504):
        # 第 1 次約 10s，之後 20、40、80… 上限 120s，略加抖動避免同步重試
        base = min(10 * (2 ** (attempt - 1)), 120)
        return base + random.uniform(0, 4)
    return min(5 * attempt, 30)


def _call_gemini(prompt, api_key, retries=None, system_prompt=None):
    if retries is None:
        retries = int(os.environ.get("GEMINI_MAX_RETRIES", "8"))
    if system_prompt is None:
        system_prompt = SYSTEM_PROMPT
    url = GEMINI_API_URL.format(model=GEMINI_MODEL, api_key=api_key)
    try:
        maxOutputTokens = int(os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", "8192"))
    except ValueError:
        maxOutputTokens = 8192
    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": maxOutputTokens,
        },
    }

    last_status = None
    for attempt in range(1, retries + 1):
        resp = None
        try:
            resp = requests.post(url, json=payload, timeout=120)
            last_status = resp.status_code
            if resp.status_code == 200:
                data = resp.json()
                candidate = data["candidates"][0]
                finish_reason = candidate.get("finishReason", "")
                if finish_reason == "MAX_TOKENS":
                    logger.warning(
                        "⚠️  輸出被截斷（MAX_TOKENS），已用 maxOutputTokens=%s；可再提高環境變數 GEMINI_MAX_OUTPUT_TOKENS 或降低 max_articles",
                        maxOutputTokens,
                    )
                text = candidate["content"]["parts"][0]["text"]
                return text
            wait = _retry_after_seconds(resp, attempt, resp.status_code)
            logger.warning(
                "Gemini API 回應 %s（第 %d/%d 次），%.0f 秒後重試：%s",
                resp.status_code,
                attempt,
                retries,
                wait,
                resp.text[:200].replace("\n", " "),
            )
            time.sleep(wait)
        except requests.RequestException as e:
            logger.warning("請求失敗（第 %d/%d 次）：%s", attempt, retries, e)
            wait = _retry_after_seconds(resp, attempt, 0)
            time.sleep(wait)

    if last_status is not None:
        logger.error("Gemini 在 %d 次重試後仍失敗（最後 HTTP %s）", retries, last_status)
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
    content_type = article.get("content_type", "traffic")
    user_tags = article.get("user_tags", [])

    if content_type == "ffxiv":
        kb = load_knowledge_base()
        kb_lines = [
            f"| {jp} | {v['tw']} | {v['en']} | {v['category']} |"
            for jp, v in kb.items()
        ]
        kb_block = "| JP | 繁中 | EN | 類別 |\n|----|----|----|----||\n" + "\n".join(kb_lines)
        all_tags = sorted(set(FFXIV_DEFAULT_TAGS) | set(user_tags))
        prompt = FFXIV_ANALYSIS_TEMPLATE.format(
            title=article.get("title", ""),
            source=article.get("source", ""),
            summary=article.get("summary", "（無摘要）"),
            link=article.get("link", ""),
            knowledge_base=kb_block,
            available_tags="、".join(all_tags),
        )
        raw = _call_gemini(prompt, api_key, system_prompt=FFXIV_SYSTEM_PROMPT)
        if raw:
            _check_kb_misses(raw, kb)
    else:
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
    try:
        mot_log = int(os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", "8192"))
    except ValueError:
        mot_log = 8192
    # 完整模型 id 若在 GitHub Secrets 與日誌相同字串會被遮罩；尾段通常足供除錯且不易觸發遮罩
    model_hint = GEMINI_MODEL.rpartition("-")[-1] if GEMINI_MODEL else "default"
    logger.info(
        "=== 開始 AI 分析，模型尾段=%s，maxOutputTokens=%s，共 %d 篇（間隔 %ds，預估 %.1f 分鐘）===",
        model_hint,
        mot_log,
        total,
        delay,
        eta_min,
    )

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