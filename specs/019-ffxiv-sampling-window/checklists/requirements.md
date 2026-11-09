# Specification Quality Checklist: FFXIV 週報取樣修正（Reddit 收窄、英文官方論壇、移除論壇列表頁）

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-09
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
- [x] Dependencies and assumptions identified; every assumption tagged `Checked:` (with its evidence) or `Unchecked:` (with what breaks if wrong)

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- 「No implementation details」照 015 的慣例判：FR-006 用設定裡的來源型別與網址指認要移除的是哪一個來源，Assumptions 的 `file:line`
  是 `Checked:` 的證據；分類依據（例如 flair）、抓法、上限的數字都留給 plan。
- SC 讀自 `ffxiv-pool` artifact 與週報 log：那是量測的資料來源，不是實作要求（015 的 SC 同樣這樣寫）。
- 3 條 `Unchecked:` 直接決定 plan 的第一步：從 Actions 拿不拿得到 Reddit 的類別訊號、英文官方論壇有沒有對應的版、英文版每週的串數。
  第一條不成立時，FR-003 會讓 Reddit 一篇都不收，要回頭請 Luke 裁示。
- 驗證一輪通過（2026-11-09）。
