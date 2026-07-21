# Specification Quality Checklist: Buffer List 雜訊分流呈現層

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-07-21
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification
- [x] Quantitative targets expressed as ladders with derivations (專案慣例：Gate 設在最寬鬆一階)
- [x] Numeric claims traceable to measurement, not invented

## Validation Notes (2026-07-21)

**通過前修正的項目：**

1. **實作細節外洩** — 初稿的 FR 直接指名檔案與資料表。已改寫為能力敘述（「隨文章資料一併提供給呈現層」而非指名 API 欄位；「設定驅動、不需改動程式碼」而非指名設定檔）。使用者原始輸入中的檔名保留在 Input 欄位作為紀錄，未進入需求正文。

2. **成功標準原為單一門檻** — 依專案決策慣例改為三階階梯（L0 Gate／L1／L2），每階附推導。SC-001 的基準 15%、SC-003 的 30 秒基線皆回溯至實測，非憑感覺挑選。

3. **SC-001 存在退化解** — 「把所有東西都降級」可讓未降級內容的高價值濃度趨近 100%。已補 SC-002（漏失率）作為守門員，並明訂兩者必須同時回報。

4. **缺少地面真值定義** — 「值得讀」原為主觀詞，導致 SC-001／SC-002 不可驗證。已補 FR-018 要求建立人工標註基準集，並在 Assumptions 說明可行性依據。

**已知的規格外前置工作（不阻擋 planning，但阻擋實作驗收）：**

- 各來源的雜訊比例目前只有 1 個來源（20 篇中 2 篇高價值）具備完整量測，其餘 29 個啟用來源未測。FR-005 要求每個判定值有量測依據，故實作階段需先補這份量測。
- FR-018 的人工標註基準集需使用者投入，尚未產出。

**與 07-27 驗收的時序關係：**

本規格與 digest 調參（07-27 weekly 實測）共用「來源雜訊比例」這份量測。兩者可共用同一次量測結果，不需各做一次。

## Clarification Pass (2026-07-21，5 題全數解決)

- [x] 分級的持久化策略已定（讀取時推導，零回填）
- [x] 設定值形狀已定（連續比例 + 單一可調門檻）
- [x] 降級的版面形式已定（預設收合為提示行）
- [x] 收起單位已定（收集來源 feed，非發稿媒體）
- [x] 基準集與交付的關係已定（只擋階數宣告，不擋交付）

**澄清過程中修掉的規格缺陷：**

1. **內部矛盾（最嚴重）** — SC-005 要求在舊週驗證，但原 FR-001 的分級是新增資料、舊文章身上沒有，兩條要求直接打架。改為讀取時推導後矛盾消失，且順帶消除了回填與 schema 變更的整批工作。
2. **「雜訊分級」名實不符** — 詞彙暗示分級，但所有 FR 與 SC 都按二分處理。現已明確：設定層連續、呈現層二分、門檻獨立可調。
3. **User Story 1 的版面敘述涵蓋三種互斥設計**（淡化／縮排／收合），驗收情境無法寫死。現已收斂為單一設計，acceptance scenarios 由 4 條擴充為 6 條。
4. **收起單位未定義，且正對準本專案既有的故障模式** — `source` 欄位是 feed 名、發稿媒體藏在標題尾碼，品牌封鎖曾因此失效過一次。已明訂為 feed 並補 FR-012a 與對應 edge case，避免重演。
5. **驗收 gate 可能無限期卡住交付** — FR-018 的人工標註需使用者投入且尚未存在。已改為只擋階數宣告，並明訂不得以主觀印象或品質分數代替（後者已實測無鑑別力）。
