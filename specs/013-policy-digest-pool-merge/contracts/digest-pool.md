# Contract — digest 池組成

**Feature**: `013-policy-digest-pool-merge` | **Date**: 2026-08-10

本專案無對外 HTTP API 需要變更。本功能暴露的介面有兩個：**設定契約**（使用者可見）
與**內部函數契約**（實作與測試的共同基準）。

---

## C1. 設定契約（對外，使用者可改）

**位置**: `config/pipeline_config.yml` → `category_digest.<類別>.include_categories`
**真身**: GitHub Environment Variable `PIPELINE_CONFIG_YML`（production）
**git 內副本**: `config/pipeline_config.example.yml`（唯一進版控者，MUST 同步）

```yaml
category_digest:
  道安政策:
    trigger_count: 10
    quality_floor: 0.18
    max_articles: 25
    include_categories: [路權政策, 科技執法, 交通工程]   # ← 本功能新增
```

### 契約條款

| # | 條款 |
|---|---|
| C1-1 | 缺鍵 ⇒ 視為 `[]` ⇒ **行為與本功能不存在時相同** |
| C1-2 | 值非 list ⇒ 載入時 `RuntimeError`，訊息含類別名與設定檔路徑 |
| C1-3 | 元素非字串 ⇒ 載入時 `RuntimeError`，訊息同上 |
| C1-4 | 元素為分類法中不存在的類別 ⇒ **WARNING**（列出該名稱），**不中止** |
| C1-5 | 清單含主類別自己 ⇒ 去重，不重複計數 |
| C1-6 | 清單順序 ⇒ 不影響任何輸出 |

**錯誤訊息形式**沿用既有風格（`pipeline_config.py`）：
`[pipeline_config] category_digest['道安政策'].include_categories 必須為 list，目前為 ...（路徑：...）`

---

## C2. 選材函數契約（內部）

**位置**: `src/analyzer.py::select_digest_pool`

```
select_digest_pool(articles, category, digest_cfg, excluded_links)
    -> (selected, pool_all, effective_count)
```

**簽章不變**——匯流清單經由既有的 `digest_cfg` 傳入，不新增參數。
這讓呼叫端（`scripts/traffic_weekly_analysis.py:120`）**無須修改即可獲得新行為**。

### 行為契約

| # | 條款 | 不變量 |
|---|---|---|
| C2-1 | 池的成員判定改為「`major_category` ∈ 有效類別集合」 | — |
| C2-2 | 有效類別集合 = `{category} ∪ set(digest_cfg.get("include_categories") or [])` | INV-6 |
| C2-3 | 純函數：無 I/O、無網路、無 AI、不改動輸入物件 | INV-2 |
| C2-4 | 排除清單先於類別判定生效 | INV-3 |
| C2-5 | `quality_floor`／`max_articles`／排序規則**完全不變** | INV-4、INV-5 |
| C2-6 | 空清單 ⇒ 輸出與改動前**逐篇相同**（含順序） | INV-1 |

**C2-3 的「不改動輸入物件」值得單獨測**：012 的 `partition_by_relevance` 會在文章上原地
附加 `_relevance_reason`，本功能**不得**沿用該做法——匯流不需要在文章上留欄位，
而 INV-2 要求分類標記不變。

---

## C3. 可觀測性契約（FR-007）

匯流是否有效**必須能從 log 判讀，不必查資料庫**。既有 log 只有總量：

```
digest[道安政策] pool=37 effective=35 threshold=10 → TRIGGER
```

新增**逐類別貢獻**（位置：`scripts/traffic_weekly_analysis.py` 的 digest 迴圈）：

```
digest[道安政策] 池組成：道安政策 37 ＋ 路權政策 4 ＋ 科技執法 4 ＋ 交通工程 1 = 46
digest[道安政策] pool=46 effective=44 threshold=10 → TRIGGER
```

### 契約條款

| # | 條款 |
|---|---|
| C3-1 | 每個來源類別**各印一項**，含篇數；零篇的類別**也要印**（`交通工程 0`） |
| C3-2 | 匯流清單為空時**不印**這行（維持現有 log 形狀，避免無意義噪音） |
| C3-3 | 這行 MUST 在觸發判定**之前**印出，使「沒觸發」時仍看得到池組成 |

**C3-1 的「零篇也要印」是刻意的**：沉默與「跑了但沒事可做」無法區分。
`交通工程` 三週僅 5 篇、本週僅 1 篇，正是會出現零篇的類別——若它悄悄消失，
沒有人會發現匯流少了一塊。這與 `traffic_buffer.py` 每天印「略過 og 充實」是同一個做法：
**讓刻意的省略發出聲音**。
