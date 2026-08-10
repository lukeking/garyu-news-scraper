# Phase 1 — Data Model: 政策 digest 池匯流

**Feature**: `013-policy-digest-pool-merge` | **Date**: 2026-08-10

⚠️ **本功能不改任何持久化 schema。** 沒有新資料表、沒有新欄位、沒有 migration。
下列「實體」是**執行期的記憶體結構**與**設定結構**。

---

## 1. 設定實體：`category_digest.<類別>`

既有結構（`config/pipeline_config.yml`），**新增最後一列**：

| 欄位 | 型別 | 預設 | 說明 | 本功能 |
|---|---|---|---|---|
| `trigger_count` | 正整數 | 10 | 有效篇數觸發門檻 | 不變 |
| `quality_floor` | float [0,1] | 0.18 | 低於此不計數、不入選材 | 不變 |
| `max_articles` | 正整數 | 15（本 repo 設 25） | 選材上限 | **不變（澄清 Q1 確認維持 25）** |
| `include_categories` | list[str] | **`[]`** | **匯流進本池的其他類別** | **新增** |

**驗證規則**（`src/pipeline_config.py`，與既有三鍵同強度）：

- 非 list → `RuntimeError`
- 元素非字串 → `RuntimeError`
- 元素為分類法中不存在的類別名 → **WARNING**，不中止（R1）
- 缺鍵 → 補 `[]`（沿用 `digest_defaults` 的補齊機制）

**預設 `[]` 是 FR-002 的結構保證**：空清單使有效類別集合退化為 `{主類別}`，
與本功能不存在時逐篇相同。「預設不改變行為」因此不需要任何人記得。

### 本 spec 的初始值

```yaml
category_digest:
  道安政策:
    trigger_count: 10
    quality_floor: 0.18
    max_articles: 25
    include_categories: [路權政策, 科技執法, 交通工程]
```

**`行人事故` 與 `路口安全` 刻意不納入**——它們以事故內容為主
（`停讓行人` feed 的 11 篇落在 `行人事故`，含大量事故簿），
納入會把 digest 從「政策彙整」變成「事故彙整」。可調，但預設保守。

---

## 2. 執行期實體：有效類別集合

```
有效類別集合 = {主類別} ∪ set(include_categories)
```

**性質**（皆為契約，測試須覆蓋）：

- **冪等於自我包含**：清單含主類別自己時不重複計數（集合聯集，非 list 串接）。
- **順序無關**：清單順序不影響任何輸出。
- **不外洩**：此集合只用於**選材時的成員判定**，
  **不寫回文章、不改 `major_category`**（FR-003）。

---

## 3. 執行期實體：digest 池（三層，既有結構）

| 層 | 定義 | 用途 | 匯流的影響 |
|---|---|---|---|
| `pool_all` | 屬於**有效類別集合**、且不在排除清單中的全部文章 | **消耗**（標記已分析，池歸零） | 變大 |
| `effective` | `pool_all` 中 `initial_quality_score ≥ quality_floor` 者 | **觸發判定**（比對 `trigger_count`） | 變大 |
| `selected` | `effective` 依品質降冪取前 `max_articles` 篇 | **選材**（進報告、傳給 LLM） | **長度不變**（上限 25），但**成員改變** |

### ⚠️ 消耗語意（承 spec 的 Clarifications Q1）

**消耗的是 `pool_all` 而非 `selected`**（`traffic_weekly_analysis.py:233`，010 的「池歸零」
設計，避免低分文章永遠累積）。所以匯流會擴大「被消耗但從未發布」的差額：

| | `pool_all` | `selected` | 消耗未發布 |
|---|---|---|---|
| 現行 | 37 | 25 | **12（32%）** |
| 匯流後 | 46 | 25 | **21（46%）** |

**這不傷及本功能要救的內容**（2026-08-10 實測）：兄弟類別 9 篇分數 0.299–0.348，
**全部落在 top 25 之內**（新進榜 9/9），多出的消耗**全部是 `交通安全教育` 的低分填充稿**
（0.193–0.199）。

### 排序的結構性偏斜（SC-002 的成因，非缺陷）

`quality_score = keyword_match_ratio×0.4 + normalised_word_count×0.3 + source_weight×0.3`

- 經 `source_defaults` fallback 進池的文章：標題**本來就沒有分類 token**
  （那正是它們 fallback 進池的原因）→ `keyword_match_ratio` **結構性偏低**。
- 兄弟類別的文章：是**命中 taxonomy 關鍵字**才被分過去的 → 該項**結構性偏高**。

因此匯流文章整批壓過現行墊底文章，擠出數**恆為 9 且與 `max_articles` 無關**
（25／30／35 實測皆擠出 9，因 `effective`(44) 恆大於上限）。
**這是為什麼 SC-002 必須寫成可歸因階梯而非「零擠出」**——後者結構性不可達，
與 012 SC-004 是同一個形狀。

---

## 4. 不變量（實作與測試的共同契約）

| # | 不變量 | 對應 |
|---|---|---|
| INV-1 | `include_categories` 為空 ⇒ 三層輸出與本功能不存在時**逐篇相同** | FR-002 |
| INV-2 | 任何文章的 `major_category` 在選材前後**不變** | FR-003 |
| INV-3 | `excluded_links` 中的 link **絕不**出現在 `pool_all`（匯流不得繞過排除） | FR-004 |
| INV-4 | `selected ⊆ effective ⊆ pool_all` | 既有 |
| INV-5 | `len(selected) ≤ max_articles` | 既有 |
| INV-6 | 同一 link 在 `pool_all` 中**至多出現一次** | R3 |
| INV-7 | 發布成功後，`pool_all` 全體被標記為已消耗（含未發布者） | 既有（010 池歸零） |
