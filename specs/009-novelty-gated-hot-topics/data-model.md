# Phase 1 Data Model: 節奏觸發式深度分析 + 深度來源分類補進

## 實體

### 1. `hot_topic_reports`（既有表，本 feature 增欄）

既有欄位（migration 002）：`id, week_start_date, topic_label, report_text, source_article_count, source_article_links(JSONB), cumulative_score, distinct_sources, distinct_days, created_at`；唯一鍵 `(week_start_date, topic_label)`。

**新增欄位（migration 004）**：

| 欄位 | 型別 | 說明 | 來源 |
|---|---|---|---|
| `topic_token_signature` | `JSONB` (預設 `'[]'`) | 該報告話題的代表詞集合（前 K 個高頻 token），供 hybrid 跨週身分比對（research D2） | 由 bucket 文章 `normalise_title` token 聯集取前 K |
| `latest_source_date` | `DATE` (nullable) | 該報告來源文章中最新的 `published` 日期，供「時間延伸」novelty 條件（research D1(b)） | `max(published[:10])` of source articles |

> `cumulative_score`、`distinct_days` 已存在，直接作為 novelty 基準的一部分。

**語意/驗證**：
- novelty 基準 = `{cumulative_score, distinct_days, topic_token_signature, latest_source_date}`。
- 比對時讀「同 `major_category`、且 Jaccard(signature, 本週 bucket 簽章) ≥ `similarity_threshold`、且 `week_start_date != 本週`」中**最近**一筆作為基準（research D2/D5）。

**topic_label 變更**：由純 `major_category` 改為「`major_category` + 代表詞」可辨識字串（如 `機車事故 · 區間測速`），避免同類別多 bucket 在 `(week, topic_label)` 唯一鍵下互蓋（research D2）。前端 008 以 `week_start_date` 過濾、以 `topic_label` 顯示，仍相容（字串較長但結構不變）。

### 2. `articles`（既有 buffer 欄位，本 feature 不改 schema）

`major_category` 欄（migration 002）值的**來源新增一條路徑**：標題 token 命中為主、source-default fallback 為輔（FR-009/010）。無 schema 變更。

### 3. Source-default category map（設定實體，非 DB）

位置：`categories_traffic.yml`（GitHub Variable `CATEGORIES_TRAFFIC_YML`）新增頂層鍵：

```yaml
source_defaults:        # 來源名子字串 → major_category（僅 uncategorised 時 fallback）
  報導者: 道安政策
  天下: 道安政策
  道安統計: 道安政策
  行人地獄: 行人事故
  區間測速: 科技執法
```

驗證：值必須是 `categories` 既有類別之一（載入時可警告未知類別，不致命）。缺 `source_defaults` 鍵 → 視為空 map，功能優雅關閉。

### 4. Novelty 參數（設定實體，非 DB）

位置：`pipeline_config.yml`（GitHub Variable `PIPELINE_CONFIG_YML`）：

```yaml
topic_scoring:
  min_threshold: 1.5       # 既有
  max_hot_topics: 3        # 既有
  novelty_growth_pct: 0.5  # 新增：score ≥ last × (1 + p)
topic_identity:            # 新增區塊
  similarity_threshold: 0.3
```

預設值（沿用 `_DEFAULTS` 風格）：`novelty_growth_pct=0.5`、`topic_identity.similarity_threshold=0.3`。

## Migration 004（草案，套用方式同既有：Supabase SQL Editor）

```sql
-- Migration 004: Hot-topic novelty gate basis
ALTER TABLE hot_topic_reports
  ADD COLUMN IF NOT EXISTS topic_token_signature JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS latest_source_date    DATE;
```

> 既有列 `topic_token_signature` 預設 `'[]'`、`latest_source_date` 為 NULL；novelty 比對對「無基準或基準殘缺」的話題一律放行（FR-003 首次觸發 / fail-open 精神），故回填非必要。

## 狀態流（單一話題跨週）

```
未報告(無基準) ──達門檻──▶ 觸發+報告 ──寫基準(score/sig/latest_date)──▶ 已報告
   ▲                                                          │
   │              本週新 bucket：同 category 且 sig 相似        │
   └──── 抑制（未過 novelty）◀── 比對基準 ◀── 達門檻且通過 gate ─┘
                                          │
                                          └─通過(突增+時間延伸)─▶ 再次觸發+更新基準
```
