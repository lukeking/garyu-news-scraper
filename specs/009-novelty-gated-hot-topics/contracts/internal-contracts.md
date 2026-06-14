# Phase 1 Contracts: 內部管線函式與設定契約

本 feature 無對外 API；契約為內部函式簽章與設定鍵。前端 008 對 `hot_topic_reports` 的讀取契約不變（仍以 `week_start_date` 過濾、`topic_label`/`report_text` 顯示）。

---

## C1. 設定鍵契約

### `categories_traffic.yml`（`CATEGORIES_TRAFFIC_YML`）
- 新增頂層鍵 `source_defaults: { <來源名子字串>: <major_category> }`，可選；缺則空 map。
- `major_category` 值應為 `categories` 既有類別；未知值載入時記 warning、略過該條。

### `pipeline_config.yml`（`PIPELINE_CONFIG_YML`）
- `topic_scoring.novelty_growth_pct: float`，預設 `0.5`，範圍 `≥ 0`。
- `topic_identity.similarity_threshold: float`，預設 `0.3`，範圍 `[0, 1]`。
- 納入 `pipeline_config.py` 的 `_DEFAULTS` 與 `_validate_pipeline_config`（範圍檢查）。

---

## C2. `src/pipeline_config.py`

```python
def load_source_default_categories(path: str | None = None) -> dict:
    """回 {來源名子字串: major_category}。讀 categories_traffic.yml 的 source_defaults 鍵；
    缺鍵或檔缺 → {}。與 load_category_taxonomy 同快取風格；reset_caches() 一併清除。"""
```
- 新增模組級快取 `_source_defaults_cache`；`reset_caches()` 需重置。

## C3. `src/pipeline/traffic.py`（分類迴圈，約 line 76-83）

行為變更（非簽章）：分類後若 `cat == "uncategorised"`，依 source-default map 以 `article["source"]` 子字串比對補上 fallback；命中即覆寫 `cat`，否則維持 `uncategorised`。

```
tokens = normalise_title(title)
cat = assign_category(tokens, taxonomy)
if cat == "uncategorised":
    cat = resolve_source_default(article.get("source",""), source_defaults)  # 第一個子字串命中者勝；無則回 "uncategorised"
article["major_category"] = cat
```
- `assign_category`（`filter.py:340`）**簽章與行為不變**；fallback 僅在呼叫端套用（FR-010 僅 fallback、不覆蓋命中）。
- `resolve_source_default(source, mapping) -> str`：小工具（可置 `filter.py` 或 `traffic.py` 區域），第一個 `key in source` 命中回對應類別，否則 `"uncategorised"`。

## C4. `src/analyzer.py` — novelty gate（gate-then-cap）

```python
def topic_token_signature(bucket_articles: list, top_k: int = 8) -> list[str]:
    """bucket 內各文章 normalise_title token 聯集，取頻次前 top_k。"""

def passes_novelty(bucket_score: float, bucket_signature: list[str],
                   bucket_latest_date: str, prior_basis: dict | None,
                   config: dict) -> bool:
    """prior_basis 為 None（無基準）→ True（FR-003）。否則需同時：
       (a) bucket_score >= prior_basis['cumulative_score'] * (1 + novelty_growth_pct)
       (b) bucket_latest_date > prior_basis['latest_source_date']（嚴格晚於）。"""

def select_hot_topics_with_novelty(buckets: dict, bucket_scores: dict,
                                   prior_reports: list, config: dict) -> list:
    """gate-then-cap：
       1. 取所有 score >= min_threshold 的 bucket；
       2. 對每個 bucket 以 (major_category 相同 且 Jaccard(sig, prior.signature) >= similarity_threshold)
          在 prior_reports 中找最近一筆作 prior_basis（research D2/D5）；
       3. 通過 passes_novelty 者保留；
       4. 存活者依分數排序取前 max_hot_topics，回傳 bucket_ids。"""
```
- `select_hot_topics`（`analyzer.py:952`）保留（仍供無基準/測試使用）；`select_hot_topics_with_novelty` 為週分析的新入口，內部沿用既有 `min_threshold`/`max_hot_topics` 設定鍵。
- 比對用 `compute_jaccard(frozenset(sig_a), frozenset(sig_b))`（沿用 `filter.py:331`）。

## C5. `src/storage.py`

```python
def get_recent_hot_topic_reports(max_age_weeks: int = 8,
                                 exclude_week: str | None = None) -> list:
    """回最近 max_age_weeks 週的 hot_topic_reports（含 topic_label, cumulative_score,
       distinct_days, topic_token_signature, latest_source_date）。exclude_week 排除當週
       （idempotency，research D5）。讀取例外 → 由呼叫端 fail-open 處理。"""
```
- `upsert_hot_topic_report`（`storage.py:373`）：`row` 增 `topic_token_signature`、`latest_source_date` 兩鍵；其餘不變（仍 on_conflict `week_start_date,topic_label`，仍標記 source 文章 `hot_topic_analyzed=TRUE`）。

## C6. `scripts/traffic_weekly_analysis.py`（串接）

於 `cluster → score` 後：
```
prior = []                      # fail-open 預設
try:
    prior = get_recent_hot_topic_reports(max_age_weeks, exclude_week=week_start)
except Exception as e:
    logger.warning("讀取 prior reports 失敗，novelty 退化為全部視為新：%s", e)
hot_topic_ids = select_hot_topics_with_novelty(buckets, bucket_scores, prior, config)
```
- 每個候選 bucket 記一行 INFO 決策日誌（category / score / matched prior / growth / 新日 / pass|suppress）。
- 組 `report` dict 時加入 `topic_token_signature`、`latest_source_date`，並把 `topic_label` 改為「`major_category` · 代表詞」。
- 其餘（Gemini 呼叫、2.5s delay、publish）不變。

---

## 不變的契約（回歸防線）
- 前端 008 / `publisher.publish_hot_topic_reports` 對 `hot_topic_reports` 既有欄位的讀取與顯示。
- daily buffer（`traffic_buffer.py`）維持零 AI；source-default 為純查表。
- `assign_category` 對「標題已命中」案例的結果（FR-010 / SC-005 無回歸）。
- Gemini 呼叫上限 `max_hot_topics` 與 2.5s delay。
