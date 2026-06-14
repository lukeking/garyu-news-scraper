# Feature Specification: 節奏觸發式深度分析 + 深度來源分類補進（交通週報 Layer 3）

**Feature Branch**: `009-novelty-gated-hot-topics`  
**Created**: 2026-06-14  
**Status**: Draft  
**Input**: 交通週報深度分析（hot_topic）目前每週一固定重選 top-N 話題並對每個入選話題產出一份新報告，不參考該話題是否已分析過或本週是否有新進展 → 同一話題每週重複發布、幾週就同質疲乏。同時，策展的低頻深度來源（報導者、天下，經 Google News `site:` query 進入）標題為編輯式長標、不含分類關鍵字 token → 被判為 uncategorised → 低量單篇 bucket → 過不了門檻 → 永不被分析。本 feature 一起解決：(1) Novelty-gated 觸發；(2) Source-default 分類補進。

## Clarifications

### Session 2026-06-14

- Q: novelty gate 與 top-N cap 的套用順序？ → A: Gate-then-cap（先對所有過 `min_threshold` 的 bucket 套 novelty gate，再於通過者中依分數取 top `max_hot_topics`）。
- Q: 話題被 gate 抑制時，當週頁面顯示什麼？ → A: 直接抑制（當週僅顯示新觸發話題；冷清週沿用 008 既有空狀態，不 carry-forward、不改前端）。
- Q: 讀取 last-reported 基準失敗時如何處理？ → A: Fail-open（視為 novel 照常分析，受 `max_hot_topics` 上限保護；記 warning）。
- Q: FR-007(b) 在 `hot_topic_analyzed` 使前後報告文章集互斥下如何精確化？ → A: 由「distinct_days 數量比較」改為「本週至少 1 篇 `published` 嚴格晚於上次報告 `latest_source_date`」（保留「新進展」精神、避免互斥集下語意失效；見 research D1）。

## User Scenarios & Testing *(mandatory)*

主要角色：**讀者**（交通週報深度分析的閱讀者）；**維運者**（維護來源與分類設定者）。深度分析由每週一的批次流程產生並發布。

### User Story 1 - 不再重複疲乏的深度分析（Novelty gate）(Priority: P1)

身為讀者，我希望每週看到的深度分析是「有新進展的話題」，而不是同一個話題每週換個日期重貼一次。一個長期停留在分析窗內、但本週沒有實質新增累積的話題，不應該再次產出深度分析報告。

**Why this priority**: 這是本 feature 的主軸與當前的實際痛點 —— 固定每週硬產 top-N，使深度素材呈 episodic 特性的交通話題反覆被重發，幾週就疲乏、訊息增量趨近零。

**Independent Test**: 連續模擬兩週分析。第 1 週某話題達門檻並產出報告；第 2 週該話題沒有顯著新增累積（無新文章/新來源/新天數）→ 驗證第 2 週不再為它產出新報告。另備一個第 2 週有顯著新增累積的話題 → 驗證它會再次產出報告。

**Acceptance Scenarios**:

1. **Given** 某話題上週已產出報告且其累積分數被記錄，**When** 本週該話題分數相對上次無顯著成長，**Then** 系統不為該話題產出新報告。
2. **Given** 某話題上週已產出報告，**When** 本週累積了足量新文章使其分數成長達 novelty delta，**Then** 系統再次為該話題產出新報告。
3. **Given** 一個從未產出過報告的話題，**When** 它本週首次達到 min_threshold，**Then** 系統視為通過 novelty 條件並產出報告。
4. **Given** 本週所有候選話題都未通過 novelty gate，**When** 流程執行，**Then** 系統正常結束、不產出也不發布任何新報告（非錯誤）。

---

### User Story 2 - 深度來源能進入深度分析（Source-default 分類）(Priority: P2)

身為讀者，我希望策展的深度媒體（報導者、天下等）的政策／結構報導能被納入深度分析；不應只因標題不含分類關鍵字就永遠落入 uncategorised、從不被分析。維運者能用設定把某來源的未分類文章導入一個合適的預設政策分類。

**Why this priority**: 這些低頻高價值素材是 axis B/C（政策／官方論述）分析的養分；把它們導入正確的政策分類 bucket，使其與既有政策 feed 累積、共同跨門檻，是讓 US1 的深度分析「有料可分析」的供給面補強。次於 US1，因為先要有不疲乏的觸發機制，導入的素材才有意義。

**Independent Test**: 取一篇深度來源、標題不含任何分類 token 的政策報導 → 驗證它被指派到設定的預設政策分類（而非 uncategorised），且能與該分類其他文章聚成同一 bucket。另取一篇標題已命中分類的文章 → 驗證其分類不被預設值覆蓋。

**Acceptance Scenarios**:

1. **Given** 一篇來源在設定 map 中、標題 token 分類為 uncategorised 的文章，**When** 進行分類，**Then** 它被指派為該來源的預設 major_category。
2. **Given** 一篇標題 token 已命中某分類的文章，**When** 進行分類，**Then** 預設值不覆蓋既有命中結果。
3. **Given** 一篇來源不在 map 中、標題也未命中的文章，**When** 進行分類，**Then** 維持 uncategorised（不誤分類）。

---

### Edge Cases

- **Re-surface**：曾報告過的話題分數先下降（buffer 過期掉文章）後又回升並重新通過 novelty delta（FR-007 兩條件）→ 視為有新進展，可再次觸發（預設不設固定 cooldown 週數）。
- **門檻優先於 novelty**：話題分數有成長但仍 < min_threshold → 不觸發。
- **首次話題無基準**：無 last-reported score 的話題視為 novelty 條件成立。
- **成長恰等於 delta**：以 `≥`（含）判定為通過。
- **topic 身分不穩定**：若「同一話題」跨週無法被穩定識別，會被當成新話題而誤觸發重複報告 —— 故需要穩定的 topic 識別鍵（見 FR-006）。
- **多來源匯入同一預設分類**：數個深度來源 fallback 到同一政策分類，與 Google News 政策 feed 混群 —— 可接受，前提是同屬該政策類別、主題仍一致。
- **被 gate 抑制的冷清週**：當週通過 gate 的話題少於上限甚至為 0 時，頁面僅顯示實際新觸發者，其餘沿用 008 既有「這一週尚無熱點話題」空狀態；不 carry-forward 前週報告。
- **last-reported 基準讀取失敗**：novelty gate 無法評估時採 **fail-open** —— 將受影響話題視為 novel 照常分析（仍受 `max_hot_topics` 上限保護），並記錄 warning；該次執行退化為近似 pre-novelty 行為，不中斷產出。

## Requirements *(mandatory)*

### Functional Requirements

**Novelty gate（US1）**

- **FR-001**: 系統 MUST 為每個已產出深度分析報告的話題，持久化 novelty 比對所需的基準 —— 至少包含上次報告時的累積分數（last-reported score）、來源文章的最新日期（latest source date），以及供 hybrid 話題識別用的代表詞簽章，供後續週次比對。
- **FR-002**: 系統 MUST 僅在話題同時滿足 (a) 本週累積分數 ≥ `min_threshold` 且 (b) 相對其 last-reported score 的成長達到 novelty delta 門檻時，才產出新的深度分析報告。
- **FR-003**: 對「從未產出過報告」的話題（無 last-reported score），系統 MUST 視為通過 novelty 條件（首次達門檻即可觸發）。
- **FR-004**: 系統 MUST 保留既有每週深度分析 AI 呼叫上限（`max_hot_topics`，預設 3）作為成本上限；novelty gate 只會減少、不會增加觸發數。選取順序為 **gate-then-cap**：novelty gate 先套用於所有達 `min_threshold` 的 bucket，再於通過 gate 的存活者中依分數取 top `max_hot_topics` 進行分析（故某週實際報告數可能 < `max_hot_topics`）。
- **FR-005**: 當某週所有候選話題都未通過 novelty gate 時，系統 MUST 正常結束且不產出/發布任何新報告（非錯誤狀態）。
- **FR-006**: 系統 MUST 以 hybrid 鍵跨週識別「同一話題」：先以 `major_category` 分組，再以該 bucket 與先前已報告話題的代表詞集合相似度（達可設定門檻）判定是否為同一話題；相似度不足者視為新話題。此需持久化先前已報告話題的代表詞識別資訊（見 FR-001）。
- **FR-007**: 一個話題 MUST 同時滿足兩條件才算「有新進展」（通過 novelty delta）：(a) 本週累積分數相對 last-reported score 的成長達可設定的百分比門檻 `p`（`score ≥ last × (1 + p)`，預設 `p=0.5`）且 (b) 該話題本週 bucket 至少有 1 篇文章的 `published` 嚴格晚於上次報告的 `latest_source_date`（確保話題在上次報告之後確有新事件延伸）。百分比 `p` MUST 可由設定調整。
- **FR-008**: 系統 MUST 允許 re-surface：曾報告過的話題若分數再次成長並重新通過 novelty delta（FR-007 的兩條件），可再次觸發；預設不另設固定 cooldown。

**Source-default 分類（US2）**

- **FR-009**: 當文章標題 token 分類結果為 uncategorised 時，系統 MUST 依「來源 → 預設 major_category」設定套用 fallback 分類。
- **FR-010**: source-default 分類 MUST 僅作為 fallback；若標題 token 已命中任一分類，MUST NOT 覆蓋既有命中結果。
- **FR-011**: 「來源 → 預設分類」對應 MUST 以設定（config）維護，新增/調整免改程式碼（沿用既有 taxonomy「加分類免改碼」精神）。
- **FR-012**: 對於來源不在 map 中且標題未命中的文章，系統 MUST 維持 uncategorised（不誤分類）。
- **FR-013**: 「來源 → 預設分類」map 的初始內容 MUST 為：報導者交通→道安政策、天下交通→道安政策、道安統計→道安政策、行人地獄→行人事故、區間測速→科技執法。
- **FR-014**: 每日資料收集（buffer）階段 MUST 維持零 AI；source-default 為純設定查表，不得引入 AI 呼叫。

### Key Entities *(include if feature involves data)*

- **深度分析報告（hot_topic_report）**：既有實體。本 feature 引入「該話題上次報告時的 novelty 基準」概念（累積分數、來源最新日期 latest_source_date、代表詞簽章），作為下次比對基準。關鍵屬性：話題識別、報告週、累積分數、latest_source_date、代表詞簽章、來源文章。
- **話題（topic / bucket）**：一組同 major_category、標題相似的文章聚合，具累積分數與 distinct sources／distinct days。需有跨週穩定的識別鍵（FR-006）。
- **來源→預設分類對應（source-default category map）**：設定實體；鍵為來源名、值為 major_category；僅在標題未命中時作為 fallback（FR-009/010）。
- **buffer 文章**：既有實體；其 major_category 可能來自標題 token 命中或 source-default fallback。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 一個連續多週留在分析窗內、但無顯著新增累積的話題，自第二週起的重複報告數為 0（不再被重複產出）。
- **SC-002**: 在典型一週，深度分析報告數不超過既有上限（3），且其中每一份對應的話題相對上次報告都有可驗證的新增累積。
- **SC-003**: 一篇深度來源、標題不含任何分類關鍵字的政策報導，被指派到預設政策分類並參與該分類的話題聚合，不再落入 uncategorised 單篇。
- **SC-004**: 每日資料收集階段維持零 AI 呼叫；每週深度分析的 AI 呼叫次數不超過既有上限。
- **SC-005**: 標題已能命中分類的文章，其分類結果不因本 feature 變更而改變（既有分類無回歸）。

## Assumptions

- 沿用既有 8 週 buffer 與跨週累積評分（`score_topic_buckets`：Σquality × log(distinct_sources+1) × log(distinct_days+1)）；本 feature 不改評分公式，只在「選取/觸發」與「分類」兩處加邏輯。
- 沿用既有每週一節奏與既有發布管線；不改為 event-driven。
- 預設不設固定 cooldown 週數；re-surface 由「再次達 last-reported + delta」自然處理（FR-008）。
- **source-default map 初始內容（已確認，FR-013）**：報導者交通→道安政策、天下交通→道安政策、道安統計→道安政策、行人地獄→行人事故、區間測速→科技執法。
- novelty delta 的百分比門檻 `p` 的實際數值留待 plan 調校（FR-007）；其結構條件固定為「至少 1 個新 distinct publication day」。
- novelty 比對需持久化每個話題上次報告的基準（分數、distinct days、代表詞）；實際儲存位置留待 plan（可能擴 `hot_topic_reports` 欄位或另增持久層）。
- 深度來源無全文（collector 僅取 RSS summary，Google News 的 summary≈標題+媒體名），分類僅能依標題 token 或來源；本 feature 不引入全文抓取。

## Out of Scope

- event-driven／每日觸發深度分析（成本與重複控制過於複雜，已否決）。
- 以 LLM 進行分類（會把 AI 帶進零-AI 的 daily buffer；本次不做，未來 precision 不足再評估升級）。
- 全文抓取 article-fetch 階段。
- `pages/shared` 共用層重設計（另開後續）。
- 被抑制話題的 carry-forward／「沿用前週分析」顯示（本次採直接抑制 + 既有空狀態）。
