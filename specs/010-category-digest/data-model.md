# Data Model — 低頻類別聚合式深度分析（010）

**本 feature 零 schema 變更、無 migration。** 所有實體都是既有資料表的用法約定或設定實體。

## 1. 類別聚合池（category pool）— 查詢視角，非新實體

既有 `articles` 表（traffic buffer）的一個過濾視角：

| 條件 | 值 |
|---|---|
| `content_type` | `'traffic'` |
| `hot_topic_analyzed` | `FALSE` |
| `buffer_expires_at` | `> NOW()` |
| `major_category` | = 啟用 digest 的類別 |

即 `get_traffic_buffer()` 回傳集合按 `major_category` 的子集——**不新增查詢函式**，runner 在既有一次撈取的結果上以 Python 過濾。

衍生屬性（執行期計算，不落庫）：
- **有效文章**：`initial_quality_score ≥ quality_floor` 者。
- **有效篇數**：觸發判斷的度量（≥ `trigger_count` → 觸發）。
- **排除名單**：本週已入選一般 bucket 的同類文章 link 集合（FR-006）。

狀態轉移：`池內（未分析）→ 已消耗（hot_topic_analyzed=TRUE）`，僅在 digest 成功持久化後發生（FR-005）；沿用既有欄位與既有標記機制，無新狀態。

## 2. digest 報告列 — 既有 `hot_topic_reports` 的用法約定

| 欄位 | digest 列的值／語意 | 與一般熱點列的差異 |
|---|---|---|
| `week_start_date` | 發布週的週一（既有 `_week_start_date()`） | 同 |
| `topic_label` | `"<類別> · 彙整"`（「彙整」為常數詞） | 一般列第二段是代表詞 |
| `report_text` | 多事件彙整（digest prompt 產出） | 敘事結構不同，欄位語意同 |
| `source_article_count` | 選材篇數（≤ max_articles） | 同語意 |
| `source_article_links` | 選材的 ordered links（`[n]` 引用對應） | 同語意 |
| `cumulative_score` | 選材 quality 總和（記錄用） | 一般列是 bucket 動能分數；digest 列不參與任何比較（見簽章） |
| `distinct_sources` / `distinct_days` | 按選材計算 | 同語意 |
| `topic_token_signature` | **`[]`（空）** — 使 digest 永不成為 novelty prior basis（research D2） | 一般列存 top-8 代表詞 |
| `latest_source_date` | 選材中最新 `published` 日期 | 同語意 |

唯一性：既有 conflict key `(week_start_date, topic_label)` → 每類別每週至多一筆 digest，重跑冪等。

## 3. 聚合設定（digest config）— 設定實體

位置：`PIPELINE_CONFIG_YML`（prod）／`config/pipeline_config.yml`（本機），頂層鍵 `category_digest`。

```yaml
category_digest:            # 空或缺 → feature off，行為與現狀零差異
  <major_category>:         # 例：道安政策
    trigger_count: 10       # 正整數；有效篇數觸發門檻（預設 10）
    quality_floor: 0.18     # [0,1]；有效文章品質下限（預設 0.18）
    max_articles: 15        # 正整數；選材上限 K（預設 15）
```

驗證規則（`pipeline_config._validate_pipeline_config` 增補，違反即 raise）：
- `trigger_count`、`max_articles`：正整數。
- `quality_floor`：數值且 ∈ [0, 1]。
- 子鍵皆可省略 → 套用預設值。

## 關係圖（概念）

```text
articles(buffer) ──按 major_category 過濾──▶ 類別聚合池
                                              │ 有效篇數 ≥ trigger_count（config）
                                              ▼
                                     analyze_category_digest（Gemini）
                                              │ 成功
                                              ▼
                                  hot_topic_reports（digest 列，空簽章）
                                              │ upsert 成功後
                                              ▼
                              池內全部文章 hot_topic_analyzed=TRUE（消耗）
```
