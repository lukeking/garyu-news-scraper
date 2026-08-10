# Phase 0 — Research: 政策 digest 池匯流

**Feature**: `013-policy-digest-pool-merge` | **Date**: 2026-08-10

本檔解決 plan 的 Technical Context 與 Constitution Check 帶出的未定項。
所有結論皆可從 repo 現況或 2026-08-10 的實測直接驗證，無 NEEDS CLARIFICATION 殘留。

---

## R1. 匯流清單含未知類別名時的行為

**Decision**: **設定載入時驗證＋WARNING 留痕，不在執行時靜默跳過。**

具體語意分三種情況：

| 情況 | 行為 |
|---|---|
| 型別錯誤（非 list、元素非字串） | **載入時 `RuntimeError`**，與既有 `category_digest` 驗證同強度 |
| 類別名合法但不存在於分類法 | **載入時記一筆 WARNING**（列出該名稱與可用類別），仍繼續啟動 |
| 類別名存在但該週零篇 | 正常，不記警告——這是預期的日常狀況 |

**Rationale**: spec 的 Edge Cases 原文寫「忽略該項，不得使 digest 失敗」，但憲章 I 明文
**「silent failures are forbidden」**。照字面實作會直接違憲。

兩者的衝突其實是假的——spec 真正要的是「**不要因為一個打錯的類別名就讓整份週報掛掉**」
（fail-soft 的價值），而憲章要的是「**不要讓錯誤無聲無息**」。**WARNING 同時滿足兩者**：
週報照跑，但錯誤有痕跡。

選擇「載入時」而非「執行時」有額外好處：設定錯誤在 pipeline 啟動時就浮現，
而不是等到週一的 digest 階段才在幾百行 log 中間出現一行；且驗證邏輯與既有的
`category_digest` 驗證同處一地（`pipeline_config.py:118–144`），不散落。

**Alternatives considered**:

- **靜默忽略**（spec 字面）——違反憲章 I。**否決。**
- **直接 `RuntimeError`**——一個打錯的類別名會讓整份週報不產出。對一個「擴充池組成」
  的選用功能來說代價過高，且與既有 digest 的 fail-soft 風格不一致
  （`traffic_weekly_analysis.py` 對 Gemini 失敗是「跳過、池不消耗」而非中止）。**否決。**
- **執行時 WARNING**——可行但較差，理由如上（時機晚、位置散）。**否決。**

---

## R2. 匯流清單放在設定的哪一層

**Decision**: **per-digest 鍵**，即 `category_digest.<類別>.include_categories`。

**Rationale**: 匯流是**某一份 digest 的池組成規則**，不是全域概念。放在 per-digest 之下：

- 沿用既有的 `_deep_merge` 與預設值補齊機制（`pipeline_config.py:120` 的 `digest_defaults`），
  新增一個預設 `[]` 即可，不需要新的設定載入路徑。
- 未來若有第二份 digest，它能有自己的匯流清單，不必互相干擾。
- **預設 `[]` 直接給出 FR-002（預設關閉）**：空清單 → 集合退化為 `{category}` →
  與現況逐篇相同。這讓「預設不改變行為」成為**結構保證**而非需要記得的約定。

**Alternatives considered**:

- **頂層 `digest_merge:` 區塊**——需要新的載入與驗證路徑，且與 `category_digest` 的
  對應關係要另外表達。多一層間接換不到任何好處。**否決。**
- **改分類法讓文章直接落到 `道安政策`**——會失去 buffer list 的細分類（`路權政策` 等在
  前端仍有用），且改動不可逆（歷史文章的分類已寫入 DB）。spec 的 Assumptions 已明確
  排除此路。**否決。**

---

## R3. 匯流是否需要新的去重

**Decision**: **不新增去重邏輯。**

**Rationale**: 兩種「重複」要分開看——

1. **同一 link 被計入兩次**：**結構上不可能**。`major_category` 是單值欄位，一篇文章
   只屬於一個類別，集合成員判定不會讓它命中兩次。
2. **不同 link、同一事件**（近似重複）：**真實存在**。2026-08-10 實測，匯流新進的 9 篇中
   有 2 組近似重複（「機車修理業者太常吃檢舉 - UDN」×2、「道安會報聚焦捷運萬大線」
   分別來自民眾新聞網與報新聞）。

第 2 種由**既有的 `embed_dedup`** 在 buffer 階段處理（`pipeline_config.yml` 的
`threshold: 0.88`），那是正確的位置——去重應該發生在資料進 buffer 時，而不是在每個
下游消費者各做一次。本功能在 buffer 之後，**不該重做上游的工作**（憲章 III 明訂
「Deduplication MUST occur in `src/filter.py` before articles reach the analysis stage」）。

**但殘餘重複必須被記錄**：spec 的 Assumptions 已要求驗收時記錄殘餘重複數。
若該數字偏高，那是 `embed_dedup` 門檻的議題，不是本功能的。

---

## R4. 如何證明測試「咬得到」（避免空測試）

**Decision**: 每條核心行為配一個**故意改壞就會失敗**的單元測試，並在實作時實際驗證一次。

「咬得到」＝**故意把實作改壞，看測試會不會失敗**（拋餌看魚咬不咬——沒咬的話，
湖裡沒魚、餌是死的、還是根本沒拋，從水面上看都一樣。舉證責任在實作者）。
反面詞：**vacuous**（通過了但根本不可能失敗）、**toothless**（有規則但沒執行）。

具體對應：

| 行為 | 測試 | 改壞什麼會讓它失敗 |
|---|---|---|
| 匯流生效 | 給含兄弟類別的輸入，斷言它們進入 `pool_all`／`effective` | 把集合改回單一字串比對 |
| **預設關閉**（FR-002） | 不給 `include_categories`，斷言結果與只含主類別時**逐篇相同** | 把預設從 `[]` 改成非空 |
| 分類標記不變（FR-003） | 匯流後斷言每篇的 `major_category` 仍是原值 | 在選材時改寫 `major_category` |
| 排除清單優先（FR-004） | 兄弟類別文章在 `excluded_links` 中時不得進池 | 把 excluded 判斷移到集合判斷之前／之後錯位 |
| 自我去重 | 清單含主類別自己時不得重複計數 | 用 list 串接而非集合聯集 |
| 型別驗證（FR-006） | 非 list／元素非字串 → `RuntimeError` | 拿掉驗證分支 |

**Rationale**: 本 repo 有現成的反例警告——`test_filter_attaches_category_and_score`
長期失敗被標 latent 繞過（見 BACKLOG「CI gating」節），那是「有規則沒執行」的實例。
且憲章與 BACKLOG 都記著：**測試贏過註解的地方只有一個，是讓違反的那一刻可見**。
一個不可能失敗的測試連這一點都做不到。

**本功能在這方面條件特別好**：改動面 100% 落在純函數與設定驗證，
不像 011／012 有「只能手動驗收」的前端缺口——所以沒有理由降低驗證強度。

---

## R5. 驗收用的量測方式

**Decision**: **離線重播既有 buffer 資料**，不等新資料、不呼叫外部服務。

`select_digest_pool` 是純函數，可直接餵入從 Supabase 唯讀查出的文章列表，
比對匯流前後的 `pool_all`／`effective`／`selected`。SC-001／SC-002 的全部指標
都能這樣算出來，且**可重跑**。

2026-08-10 已用此法取得全部錨定值（見 spec 的 Success Criteria），
證明這條路徑可行——不是計畫，是已經做過一次的事。

**唯一需要線上驗證的是 SC-003（雜訊判讀）與 prod 部署**，前者是人工逐篇讀標題
（每週約 9 篇），後者比照 012 的 T013 形狀：`gh variable set` 後用 YAML parse 比物件
（**不可比位元組**——012 實測 `gh variable set < 檔案` 會把尾端 `\r\n` 存成單一 `\n`）。
