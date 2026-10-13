# Data Model: 補政策 digest 的來源

本功能不改資料庫 schema。這裡的「實體」是設定檔與 log 的形狀。

## 來源（既有，不改格式）

`config/sources_traffic.yml` 的一筆：`name`、`type`（rss／ptt／web／youtube）、`url` 或 `board`／`channel_id`、
選用 `enabled`、`lookback_days`、`relevance_exempt`、`max_items`、`min_pushes`。
真身是 GitHub 變數 `SOURCES_TRAFFIC_YML`；`config/sources_traffic.example.yml` 改成它的鏡像（解析後的值相同，註解不算）。

## 來源預設類別（既有，不改格式）

`config/categories_traffic.yml` 的 `source_defaults`：`{來源名稱子字串: 類別}`，只在標題分不出類（`uncategorised`）時生效。
真身是 `CATEGORIES_TRAFFIC_YML`，example 已是鏡像。

## 漏斗（新）

`TrafficCategory.filter()` 每次執行後留下的逐來源計數，同時印成 log（contracts C1）：

| 關 | 對應 `filter()` 裡的 list | 意義 |
|---|---|---|
| 收集 | `raw` | 收集端交進來的篇數 |
| 新鮮度 | `after_freshness` | 過了跨週指紋與過時判定 |
| 過濾 | `candidates`（`filter_and_deduplicate` 之後） | 過了相關性檢查與完全重複去除 |
| 封鎖 | 來源封鎖與內容關鍵字封鎖之後 | |
| 同批去重 | `deduped`（Jaccard 之後） | 同一批裡的近似重複只留一篇 |
| 向量去重 | `_embedding_dedup` 之後 | 本週＋上週未消耗的 buffer 裡已有 |
| 寫入上限 | 回傳值 | 排序後取前 `max_daily_articles` |
| 匯流四類 | 回傳值中 `major_category` ∈ 匯流四類 | 會進 digest 池的候選 |

計數單位是「該關之後、`source` 為此來源的篇數」，所以每一關都 ≤ 前一關（Jaccard 保留較長那篇時，算在留下那篇的來源）。
收集為 0 的來源也要有一行（沉默與「跑了但沒東西」分不出來）。

## 提案設定檔（新，評估工具的輸入）

與 `sources_traffic.yml` 同格式的完整清單（現有＋候選，或改過 query 的現有來源），外加選用的：

```yaml
source_defaults:        # 只放要新增或覆寫的對映，評估時合併進現行 categories 檔的暫存副本
  交通新制: 道安政策
```

不放 `source_defaults` 時，用現行的對映。

## 評估輸出（新）

- 每個來源一行漏斗（同 C1 的格式）。
- 每個來源最終落在匯流四類的標題清單（給人工判讀正題）。
- 本次呼叫 embedding 的篇數（FR-008）。
- 收集耗時（逐來源，供 runtime 估算）。
