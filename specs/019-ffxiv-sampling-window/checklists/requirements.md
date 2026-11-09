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
- 2 條 `Unchecked:` 直接決定 plan 的第一步：英文官方論壇有沒有對應的子版（id、RSS、時區），以及英文版每週的串數。
- 2026-11-09 範圍改了三次（Reddit：收窄 → 拿掉 → 收窄加回覆 → 因 robots.txt 拿掉），每次改完重跑一輪，最後一輪通過。
