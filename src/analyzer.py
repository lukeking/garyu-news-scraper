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
GEMINI_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-embedding-2:embedContent?key={api_key}"
)
EMBED_DIMENSIONS = 768  # MRL truncation from 3072; balances accuracy vs storage

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
_KB_HIGHLIGHT = re.compile(r"\[\[([^\]]+)\]\]")
_KB_MISS_ACCUMULATOR: set = set()

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
地區：填入最相關的地理標籤，如「台北市」「新北市」「台中市」「高雄市」「全台」「不明」（只填一個，同一行寫完）

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

【重要規則：未收錄術語的處理方式】
- 若原文中出現以片假名、平假名或日文漢字書寫的術語，且未收錄於上方知識庫，請保留日文原文並以 [[術語]] 格式包覆（例：[[エーテル]]）。
- 英文術語、英文縮寫（如 CF、FC、MSQ、NPC）及繁體中文術語，即使未出現在知識庫，也不需要用 [[]] 包覆，直接使用即可。
- 絕對不可自行翻譯未收錄的日文術語。

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


def load_knowledge_base() -> dict:
    """
    從 Supabase knowledge_base 表格載入術語對照表。
    回傳 {jp_term: {"tw": str, "en": str, "category": str}} 的對照字典。
    若表格為空或連線失敗，拋出 RuntimeError（pipeline 中止）。
    結果在模組層級快取，同一程序只查詢一次。
    """
    global _KB_CACHE
    if _KB_CACHE is not None:
        return _KB_CACHE

    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 未設定")

    from supabase import create_client
    client = create_client(url, key)

    result = client.table("knowledge_base").select("jp_term, tw_term, en_term, category").execute()

    kb = {
        row["jp_term"]: {
            "tw": row["tw_term"],
            "en": row["en_term"],
            "category": row["category"],
        }
        for row in result.data
    }

    if not kb:
        raise RuntimeError(
            "knowledge_base 表格中沒有有效的術語資料。"
            "請先執行 python scripts/migrate_kb.py 或在 Supabase 中加入術語後再執行 FFXIV 分析。"
        )

    logger.info("知識庫載入完成：%d 個術語", len(kb))
    _KB_CACHE = kb
    return kb


def _check_kb_misses(text: str, kb: dict) -> None:
    """
    掃描 Gemini 回應中未被知識庫收錄的術語：
    1. [[term]] 標記 — 模型遵守規則時自行標記的未知術語
    2. 裸出現的片假名序列（3 字以上）— 漏標的備援掃描
    兩類皆累積至 _KB_MISS_ACCUMULATOR 供執行結束時提示使用者。
    """
    # 優先：模型用 [[term]] 明確標記的未知術語
    for match in _KB_HIGHLIGHT.findall(text):
        term = match.strip()
        if term and term not in kb:
            logger.warning("[KB MISS] 未知詞彙：%s", term)
            _KB_MISS_ACCUMULATOR.add(term)

    # 備援：未加標記但出現在回應中的片假名序列
    for match in set(_KB_KATAKANA.findall(text)):
        if match not in kb and match not in _KB_MISS_ACCUMULATOR:
            logger.warning("[KB MISS] 未知詞彙（未標記）：%s", match)
            _KB_MISS_ACCUMULATOR.add(match)


def get_kb_miss_summary() -> list:
    """回傳本次執行中所有 [KB MISS] 術語列表，供主程式在執行結束時提示使用者。"""
    return sorted(_KB_MISS_ACCUMULATOR)


def _get_api_key():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY 環境變數未設定")
    return key


# ── Embedding Dedup (traffic pipeline) ───────────────────────────────────────

def generate_embedding(text: str) -> list | None:
    """
    Call Gemini Embedding 2 to produce a 768-dim vector for the given text.
    Returns None on any API failure so callers can skip similarity checks gracefully.
    """
    api_key = _get_api_key()
    url = GEMINI_EMBED_URL.format(api_key=api_key)
    payload = {
        "content": {"parts": [{"text": f"task: semantic_similarity\n\n{text[:4000]}"}]},
        "outputDimensionality": EMBED_DIMENSIONS,
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]
    except Exception as e:
        logger.warning("[embedding] 生成失敗：%s", e)
        return None


def _cosine_similarity(a: list, b: list) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def embed_dedup(candidates: list, buffer_articles: list, threshold: float = 0.88) -> list:
    """
    Deduplicate candidates by cosine similarity of Gemini embeddings.
    Checks each candidate against: (1) buffer articles already in the weekly DB,
    (2) other candidates in the same batch.
    Attaches the embedding to each article dict so publish() can store it.
    Falls back to returning all candidates if embeddings cannot be generated.
    """
    if not candidates:
        return candidates

    # Generate embeddings for all candidates
    for a in candidates:
        if "embedding" not in a:
            text = (a.get("title") or "") + "\n" + (a.get("summary") or "")[:300]
            a["embedding"] = generate_embedding(text)

    has_embed = [a for a in candidates if a.get("embedding") is not None]
    no_embed = [a for a in candidates if a.get("embedding") is None]

    if not has_embed:
        logger.warning("[embed_dedup] 所有候選嵌入生成失敗，保留所有")
        return candidates

    buffer_with_embed = [a for a in buffer_articles if a.get("embedding")]

    # Step 1: drop candidates already covered by the week's buffer
    after_buffer: list = []
    for a in has_embed:
        matched = next(
            (b for b in buffer_with_embed
             if _cosine_similarity(a["embedding"], b["embedding"]) >= threshold),
            None,
        )
        if matched:
            logger.info(
                "[embed_dedup] 已在緩衝區，略過（相似度≥%.2f）：%s",
                threshold, a.get("title", ""),
            )
        else:
            after_buffer.append(a)

    # Step 2: pairwise dedup within the batch; keep the article with more summary content
    deduped: list = []
    for a in after_buffer:
        dup_idx = next(
            (j for j, kept in enumerate(deduped)
             if _cosine_similarity(a["embedding"], kept["embedding"]) >= threshold),
            None,
        )
        if dup_idx is None:
            deduped.append(a)
        else:
            kept_len = len(deduped[dup_idx].get("summary") or "")
            cand_len = len(a.get("summary") or "")
            if cand_len > kept_len:
                logger.info("[embed_dedup] 批次去重，保留較詳細版本：%s", a.get("title", ""))
                deduped[dup_idx] = a
            else:
                logger.info("[embed_dedup] 批次去重，略過：%s", a.get("title", ""))

    result = deduped + no_embed
    skipped = len(candidates) - len(result)
    logger.info("[embed_dedup] 結果：%d → %d 篇（略過 %d）", len(candidates), len(result), skipped)
    return result


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
        "location": "",
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
        elif line.startswith("地區："):
            result["location"] = line[3:].strip()

    # fallback：分析欄位多行合併
    if not result["analysis"]:
        lines = text.splitlines()
        collecting = False
        buf = []
        known_tags = ("摘要：", "重要性：", "重要性原因：", "地區：")
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
        known_tags = ("分析：", "重要性：", "重要性原因：", "地區：")
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


HOT_TOPIC_SYSTEM_PROMPT = (
    "你是台灣交通安全深度分析師，專精機車與道路安全議題。"
    "請用繁體中文回應，融合台灣民眾觀點與國際道路安全標準，語氣客觀且具建設性。"
    "分析應點出問題根源、社會背景與可行改善方向，避免重複資訊或泛泛而論。"
    "回應格式務必嚴格按照指示，不要加入任何額外說明或 markdown 符號。"
)

HOT_TOPIC_PROMPT_TEMPLATE = """以下是本週「{topic_label}」類別的熱點交通新聞（共 {article_count} 篇）：

{article_list}

請針對以上新聞群，依照以下格式回應，每個欄位必須在同一行內完成，不可換行：

現象摘要：用2到3句話描述本週該議題的整體現象與規模（同一行，句子之間用「。」分隔）
根源分析：用3到5句話分析造成此現象的結構性原因、道路設計、法規落差或駕駛行為因素（同一行，句子之間用「。」分隔）
影響評估：用2到3句話評估此議題對台灣機車騎士與整體道路安全的實際影響（同一行，句子之間用「。」分隔）
改善建議：用2到3句話提出具體可行的改善方向，可參考國際案例（同一行，句子之間用「。」分隔）
"""


def analyze_hot_topic(bucket_articles: list, topic_label: str, week_start_date: str) -> str:
    """
    Generate a deep-analysis report for a hot topic bucket using Gemini.
    Selects top 10 articles by initial_quality_score for the prompt.
    Returns the report text string, or empty string on failure.
    Caller is responsible for respecting rate limits (existing 2.5s delay convention).
    """
    api_key = _get_api_key()

    top_articles = sorted(
        bucket_articles,
        key=lambda a: float(a.get("initial_quality_score") or 0),
        reverse=True,
    )[:10]

    lines = []
    for i, a in enumerate(top_articles, 1):
        title = a.get("title", "（無標題）")
        body = (a.get("summary", "") or a.get("content", "") or "")[:200]
        lines.append(f"{i}. 標題：{title}\n   摘要：{body}")

    article_list = "\n\n".join(lines)
    prompt = HOT_TOPIC_PROMPT_TEMPLATE.format(
        topic_label=topic_label,
        article_count=len(top_articles),
        article_list=article_list,
    )

    raw = _call_gemini(prompt, api_key, system_prompt=HOT_TOPIC_SYSTEM_PROMPT)
    if raw:
        logger.info("✓ 熱點分析完成：%s (%s)", topic_label, week_start_date)
        return raw.strip()

    logger.warning("✗ 熱點分析失敗：%s (%s)", topic_label, week_start_date)
    return ""


_DEDUP_SYSTEM_PROMPT = (
    "你是新聞去重複助手。你的任務是找出描述「完全相同事件」的重複報導。\n"
    "重複的判斷標準：同一地點＋同一事件類型＋同一政府機關或當事人出現，即視為同一事件，"
    "即使措辭不同（如「騎士」vs「網紅」、「函警」vs「報警舉發」）。\n"
    "不算重複的情形：主題相似但事件明顯不同（不同起事故、不同地點、不同當事人）。\n"
    "候選間互為重複時，只保留摘要最詳細的一篇。\n"
    "只回覆 JSON，不加任何說明或 markdown 符號。"
)


def dedup_same_event(candidates: list, buffer_articles: list) -> list:
    """
    Use Gemini to drop candidates that describe the same event as each other
    or as articles already in the weekly buffer.
    Jaccard dedup should run first; this handles the grey zone that token overlap misses.
    Falls back to returning all candidates on any error.
    """
    if not candidates:
        return candidates

    import json

    api_key = _get_api_key()

    buffer_lines = []
    for i, a in enumerate(buffer_articles[-30:], 1):
        excerpt = (a.get("summary") or "")[:120].replace("\n", " ")
        buffer_lines.append(f"[B{i}] {a.get('title', '')}\n摘要：{excerpt}")
    buffer_section = "\n\n".join(buffer_lines) or "（本週尚無已收錄文章）"

    candidate_lines = []
    for i, a in enumerate(candidates, 1):
        excerpt = (a.get("summary") or "")[:120].replace("\n", " ")
        candidate_lines.append(f"[N{i}] {a.get('title', '')}\n摘要：{excerpt}")
    candidates_section = "\n\n".join(candidate_lines)

    prompt = (
        f"本週緩衝區（已收錄）：\n\n{buffer_section}\n\n"
        f"今日候選（待決定）：\n\n{candidates_section}\n\n"
        "請找出今日候選中，與緩衝區或其他候選描述「完全相同事件」的重複報導。\n"
        "排除條件：同一地點＋同一事件類型＋同一政府機關或當事人出現，即可排除，措辭不同亦算重複。\n"
        "保留條件：不同起事故（不同當事人、不同地點、不同日期）一律保留。\n"
        "候選間互為重複時，保留摘要最詳細的一篇。\n\n"
        '回覆 JSON，必須包含 exclude（排除的 N 編號）與 reasons（排除原因）：\n'
        '{"exclude": ["N3"], "reasons": {"N3": "與 N1 描述同一天同一地點的事故"}, "keep": ["N1", "N2"]}'
    )

    logger.info(
        "[dedup_same_event] 送出：%d 候選，%d 緩衝區文章",
        len(candidates), len(buffer_articles),
    )
    logger.debug("[dedup_same_event] prompt:\n%s", prompt)

    try:
        raw = _call_gemini(prompt, api_key, system_prompt=_DEDUP_SYSTEM_PROMPT)
        logger.debug("[dedup_same_event] 原始回覆：%s", raw)
        if not raw:
            logger.warning("[dedup_same_event] Gemini 回傳空回覆，保留所有候選")
            return candidates

        # Find the outermost JSON object using brace counting (handles nested objects)
        start = raw.find('{')
        if start == -1:
            logger.warning("[dedup_same_event] 無法解析回覆（找不到 JSON），保留所有候選\n原始回覆：%s", raw)
            return candidates
        depth, end = 0, -1
        for i, ch in enumerate(raw[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            logger.warning("[dedup_same_event] JSON 括號不匹配，保留所有候選\n原始回覆：%s", raw)
            return candidates

        result = json.loads(raw[start:end + 1])
        exclude_ids = {s for s in result.get("exclude", []) if isinstance(s, str)}
        reasons = result.get("reasons", {})
        for nid, reason in reasons.items():
            if nid in exclude_ids:
                logger.info("[dedup_same_event] 排除 %s：%s", nid, reason)

        filtered = [a for i, a in enumerate(candidates, 1) if f"N{i}" not in exclude_ids]
        skipped = len(candidates) - len(filtered)
        logger.info("[dedup_same_event] 結果：%d → %d 篇（略過 %d）", len(candidates), len(filtered), skipped)
        return filtered

    except Exception as e:
        logger.warning("[dedup_same_event] LLM 去重複失敗，保留所有候選：%s", e)
        return candidates


# ── Traffic Pipeline: Clustering + Scoring (US3) ─────────────────────────────

def _article_word_count(article: dict) -> int:
    body = article.get("summary", "") or article.get("content", "") or ""
    return len((article.get("title", "") + body).replace(" ", ""))


def _date_part(published: str) -> str:
    return published[:10] if published else ""


def cluster_traffic_articles(articles: list, config: dict) -> dict:
    """
    Group traffic articles into topic buckets by Jaccard similarity within each
    major_category.

    - Jaccard > merge_threshold: near-duplicate pair — keep higher word-count article (FR-013)
    - Jaccard in [cluster_lower, merge_threshold]: same topic bucket (FR-014)
    - Otherwise: new independent bucket

    Returns {bucket_id: [article_dicts]}.
    """
    from src.filter import normalise_title, compute_jaccard

    merge_threshold = config.get("jaccard", {}).get("merge_threshold", 0.45)
    cluster_lower = config.get("jaccard", {}).get("cluster_lower", 0.20)

    # Group by major_category
    by_category: dict = {}
    for article in articles:
        cat = article.get("major_category", "uncategorised")
        by_category.setdefault(cat, []).append(article)

    all_buckets: dict = {}
    bucket_counter = 0

    for cat_articles in by_category.values():
        token_sets = {id(a): normalise_title(a.get("title", "")) for a in cat_articles}

        # 1. Deduplicate: sort by word count desc; retain article only if no
        #    already-retained article has Jaccard > merge_threshold with it.
        sorted_articles = sorted(cat_articles, key=_article_word_count, reverse=True)
        deduplicated: list = []
        for article in sorted_articles:
            ts_a = token_sets[id(article)]
            is_dup = any(
                compute_jaccard(ts_a, token_sets[id(r)]) > merge_threshold
                for r in deduplicated
            )
            if not is_dup:
                deduplicated.append(article)

        # 2. Cluster: assign to an existing bucket if any member scores in
        #    [cluster_lower, merge_threshold]; start a new bucket otherwise.
        cat_buckets: dict = {}
        for article in deduplicated:
            ts_a = token_sets[id(article)]
            assigned = False
            for bid, bucket_articles in cat_buckets.items():
                for b_article in bucket_articles:
                    score = compute_jaccard(ts_a, token_sets[id(b_article)])
                    if cluster_lower <= score <= merge_threshold:
                        bucket_articles.append(article)
                        assigned = True
                        break
                if assigned:
                    break
            if not assigned:
                bid = f"bucket_{bucket_counter}"
                bucket_counter += 1
                cat_buckets[bid] = [article]

        all_buckets.update(cat_buckets)

    return all_buckets


def score_topic_buckets(buckets: dict, config: dict) -> dict:
    """
    Compute the cumulative momentum score for each bucket:
    score = Σ(quality_scores) × log(distinct_sources + 1) × log(distinct_days + 1)

    Returns {bucket_id: score}.
    """
    import math

    scores: dict = {}
    for bid, bucket_articles in buckets.items():
        quality_sum = sum(
            float(a.get("initial_quality_score") or 0) for a in bucket_articles
        )
        distinct_sources = len({a.get("source", "") for a in bucket_articles})
        distinct_days = len({
            _date_part(a.get("published", ""))
            for a in bucket_articles
            if a.get("published")
        })
        score = (
            quality_sum
            * math.log(distinct_sources + 1)
            * math.log(max(distinct_days, 1) + 1)
        )
        scores[bid] = score

    return scores


def select_hot_topics(bucket_scores: dict, config: dict) -> list:
    """
    Return at most max_hot_topics bucket_ids with score >= min_threshold,
    sorted by score descending.
    """
    topic_cfg = config.get("topic_scoring", {})
    min_threshold = float(topic_cfg.get("min_threshold", 1.5))
    max_hot_topics = int(topic_cfg.get("max_hot_topics", 3))

    qualified = [
        (bid, score) for bid, score in bucket_scores.items()
        if score >= min_threshold
    ]
    qualified.sort(key=lambda x: x[1], reverse=True)
    return [bid for bid, _ in qualified[:max_hot_topics]]