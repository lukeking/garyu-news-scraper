# Phase 1 Data Model: 相關性選材閘

**無資料庫 schema 變更。** 不新增 `articles`/buffer 欄位、不動 migration。以下「實體」多為
**config 結構**與**記憶體中的中間值**，唯一落地的檔案是 config YAML 與（測試用）標記基準集。

---

## 1. Per-Category Relevance Rule（config，新增）

住 `config/categories_traffic.yml`，與既有 `categories:` / `source_defaults:` 並列。
per-category，只需為會離題的類別填（先填 `機車事故`）。

```yaml
# 相關性閘規則（feature 012）。key = major_category；缺 key 的類別 = 不套閘（全通過）。
relevance_rules:
  機車事故:
    require_any:            # 正面事故 token 白名單：命中任一才算 on-topic
      [撞, 追撞, 自撞, 擦撞, 車禍, 事故, 肇事, 送醫, 不治, 傷, 亡, 翻車, 失控, 死]
    exclude_any:            # 刑案／市場 token 黑名單：命中任一即 off-topic（除非同時命中 require_any）
      [竊, 偷, 竊盜, 羈押, 求償, 外遇, 潑糞, 通緝, 毒品, 毒駕, 油耗, 市佔, 市占, 銷量, 戰報, 掛牌數, 規格]
```

**判定語意（AND-NOT，見 research D2）**：
```
on_topic(article, rule) :=
    hit(require_any)  AND  NOT ( hit(exclude_any) AND NOT hit(require_any) )
  ≡ hit(require_any) AND NOT hit(exclude_any_pure)
其中 hit(X) = normalise_title(title) 與 X 有交集（沿用 jieba token，與 assign_category 同源）
```
- 「肇事逃逸」：命中 `肇事`（require）→ on-topic，即使另含刑案性質。**邊界由 require_any 優先解掉。**
- 純竊盜：命中 `竊`（exclude）、無事故 token → off-topic。
- **欄位皆選填**：只給 `exclude_any` = 純黑名單；只給 `require_any` = 純白名單；本 seed 兩者都給。

**驗證規則**：token 必須是 jieba 會切出的詞（同 taxonomy 既有註記——複合詞如「機車事故」會被切開）。
規則載入失敗（缺鍵／格式錯）時該類別**視為不套閘**（fail-open，寧可漏擋不可誤殺整類），並記 log。

## 2. `blocked_content_keywords` 擴充（config，既有欄位）

住 `config/pipeline_config.yml`（既有）。Tier 1 只是**新增詞**，欄位與消費點皆已存在
（`src/pipeline/traffic.py:66`，filter 階段標題子字串比對）。

```yaml
blocked_content_keywords:
  # …既有（售價/試駕/銷售排行/車展/優惠…）…
  - 油耗        # ← 08-03 金線案缺的市場詞（feature 012 Tier 1）
  - 市佔
  - 市占
  - 銷量
  - 戰報
  - 掛牌數
```
注意此為**全域 filter 封鎖**（該文從所有類別的 buffer 消失），故只放**確定是行銷噪音**的市場詞；
語意較模糊的離題留給 §1 的 per-category 閘（只影響該類別選材，不丟 buffer）。

## 3. Relevance Partition（記憶體中間值，不落地）

每週選材期，閘對候選集產出的分割——純函數回傳，不寫 DB：

| 欄 | 型別 | 說明 |
|---|---|---|
| `on_topic` | list[article] | 通過閘 → 進 `cluster_traffic_articles` |
| `off_topic` | list[article] | 未通過 → 排除於計分/選材（仍留 buffer） |
| 每篇附 `_relevance_reason` | str（僅 log/診斷）| 如 `excluded:竊` / `kept:肇事` / `no-rule` |

**FR-003 由此自動滿足**：某桶所有候選都落 `off_topic` → 該 major_category 無 on-topic 文章 →
不成桶、不 score、不 select → 不發布。無需額外「空桶」判斷碼。

## 4. Labeled Relevance Baseline（測試/量測資產，新增檔案）

供 `scripts/measure_relevance.py` 重播、量測 SC 階梯的**人工標記基準集**。落地為版控檔
（去識別化：只留 title／source／label，不含全文），置於 `tests/fixtures/` 或 `specs/012.../`。

| 欄 | 型別 | 說明 |
|---|---|---|
| `week_id` | str | 取樣週（如 `2026-W32`） |
| `major_category` | str | 該篇被指派的類別 |
| `title` | str | 標題（判定輸入） |
| `source` | str | 來源（feed 名） |
| `label` | enum `on`/`off` | **人工**標記的主題相關性（唯一的 ground truth） |
| `note` | str（選填）| 邊界案備註（如「肇事逃逸＝刑案∩事故」） |

**紀律**：`label` 只能人工標，禁止用閘自己的輸出回填（那等於讓系統批改自己的考卷，
見 review-loop-bounds「校準用後果、不用被矯正的判斷史」）。基準集以 08-03 兩案為錨、涵蓋多週。

---

## 不變式（Invariants）

- 閘為**純函數**：同 (articles, rules) 必得同 partition（憲章 III；可重播）。
- 閘**零外部呼叫**：只讀 config 與 in-memory token（憲章 IV / FR-006）。
- 閘**不改** `major_category`、不寫 DB、不丟 buffer（§1 路徑）；只有 §2 的全域市場詞封鎖會丟 buffer。
- `require_any` 命中 **優先於** `exclude_any`（邊界規則，FR 對「肇事逃逸」的要求）。
