# Specification Quality Checklist: 政策 digest 池匯流兄弟政策類別

**Purpose**: Validate specification completeness and quality before proceeding to planning  
**Created**: 2026-08-10  
**Feature**: [spec.md](../spec.md)

## Content Quality

- [X] No implementation details (languages, frameworks, APIs)
- [X] Focused on user value and business needs
- [X] Written for non-technical stakeholders
- [X] All mandatory sections completed

## Requirement Completeness

- [X] No [NEEDS CLARIFICATION] markers remain
- [X] Requirements are testable and unambiguous
- [X] Success criteria are measurable
- [X] Success criteria are technology-agnostic (no implementation details)
- [X] All acceptance scenarios are defined
- [X] Edge cases are identified
- [X] Scope is clearly bounded
- [X] Dependencies and assumptions identified

## Feature Readiness

- [X] All functional requirements have clear acceptance criteria
- [X] User scenarios cover primary flows
- [X] Feature meets measurable outcomes defined in Success Criteria
- [X] No implementation details leak into specification

## Notes

**驗證第 1 輪發現並已修正的問題：**

1. **FR 洩漏實作細節** — 初稿的 FR-001 寫成「`select_digest_pool` 接受類別集合」，
   點名了函數。已改寫為「digest 池的組成能由設定指定一組類別」，行為不變、無實作綁定。
2. **SC-002 原為不可達的單一門檻** — 初稿寫「現行選材不得掉出」。08-10 實測證明
   結構性不可達（匯流文章分數整批壓過現行墊底，擠出數與 `max_articles` 無關）。
   已依 012 SC-004 的教訓改為**可歸因階梯**，並把推導寫進 spec 正文，避免下次重蹈。
3. **SC-003 原本可被略過** — 初稿把雜訊寫在 Assumptions 裡，讀起來像免責聲明。
   已提升為必須產出的數字，並明文「不得以『現況也沒擋』為由略過量測」。

**Clarify 輪（2026-08-10，2 問）補上的缺口：**

4. **消耗語意漏寫（承重）** — spec 初稿把「不改 `max_articles`」寫成 Assumptions 裡的一句
   「這是獨立的編輯決定」，但當時**尚未查證 `pool_all` 的消耗語意**。查證後發現消耗的是整池
   而非選材，匯流會把「被消耗但從未發布」從 12/37 推高到 21/46——這與本 spec 的 US2
   正面相關，不能只當成上限設定。已補進 Key Entities（附 ⚠️）與 Assumptions（附實測依據：
   兄弟類別 9 篇全在 top 25 內，多出的消耗全是低分填充稿）。
5. **標籤與持久化鍵的耦合未寫** — `topic_label` 同時是讀者標題、upsert 主鍵的一半、
   以及傳給 LLM 的主題框架。初稿完全沒提。已新增 **FR-009** 明訂標題不變，並記錄理由。
6. **SC-003 的判讀方式未定** — 原文只要求「報出離題篇數」，沒說怎麼判。已補「人工逐篇
   （每週約 9 篇，不需基準集）＋判讀結果必須寫進驗收紀錄」，否則下次無法比較。

**刻意保留的兩個開放項（非缺陷）：**

- **SC-001 L2 未達成**（08-10 實測 60.9% > 50%）。這是階梯的設計意圖——
  Gate 在 L0，L2 是理想，未達成不阻擋交付。
- **雜訊無擋**：`道安政策` 的相關性 token 表屬 BACKLOG #7，不在本 spec 範圍。
  本 spec 沒有讓情況變差（匯流前同樣無擋），且 SC-003 產出的數字正是 #7 的起點。

**量測範圍的誠實標註**（已寫進 spec 的「已知限制」）：
錨定值來自單一週窗、兄弟類別僅 9 篇；`交通工程` 本週僅 1 篇。
本解法把既有內容用滿，不會無中生有——真正要更多來源時仍需回到 #8 原計畫。
