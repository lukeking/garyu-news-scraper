# Implementation Plan: UX Improvements

**Branch**: `epic/ux-improvements-2026` | **Date**: 2026-05-05
**Do not merge until all phases are complete.**

---

## Overview

Three phases of incremental UX improvements across both sites. All changes are
additive — no existing behaviour is removed. Phases are independent and can be
implemented in order without blockers between them.

---

## Phase 1 — Quick Wins (frontend-only, no backend changes)

### P1-A: Cross-site navigation
Add a minimal header link on each site pointing to the other.

- `pages/traffic/index.html` → link to FFXIV site
- `pages/ffxiv/index.html` → link to Traffic site
- Targets: `FFXIV_SITE_URL` / `TRAFFIC_SITE_URL` env vars already exist; hard-code
  the known CF Pages URLs as fallback
- Style: subtle text link in the existing site header, no new UI components

### P1-B: Filter state persistence (localStorage)
When a user selects importance filter (高/中/低/全部) or content-type tab, restore
that selection on next page load.

- Store key: `garyu_filter_importance` / `garyu_filter_content_type` in localStorage
- On page load: read stored value before rendering, apply as default selection
- Affected files: `pages/traffic/index.html`, `pages/ffxiv/index.html`

### P1-C: "Last synced" timestamp
Show when the most recent article in the current week was published (i.e. max
`created_at` from the fetched API response), giving users confidence the data
is fresh.

- Derive from API response already in memory — no extra request
- Display: small muted line in the week header, e.g. "最後更新：3 小時前"
- Use `Intl.RelativeTimeFormat` for human-readable relative time in viewer's locale

**Deliverables**: changes to both `index.html` files only. No backend, no worker.

---

## Phase 2 — Source & Language Tagging (frontend config + minor backend)

### P2-A: Source language tags
Each article card gets a small flag/tag indicating original source language,
derived from the `source` name already in the API response.

- Frontend-only mapping: define a `SOURCE_LANG` lookup in each `index.html`
  (e.g. `{ "Reddit r/ffxiv": "EN", "FFXIV JP Forum": "JP", ... }`)
- Render as a small badge next to the source badge (reuse existing `.source-badge` style)
- No backend change needed

### P2-B: Geographic tags for traffic news
Extend the AI analysis prompt to extract a location tag (e.g. 台北/台中/全台/不明)
for traffic articles, stored in `analysis.location`.

- Modify `src/analyzer.py` traffic prompt to include location extraction
- Render in `pages/traffic/index.html` as a small location badge on each card
- Fallback: omit badge if `analysis.location` is absent (backward compatible with
  existing DB rows)

### P2-C: Share to Line button
Add a "分享至 LINE" icon button on traffic article cards. Tapping opens the LINE
share URL with the article link pre-filled.

- LINE share URL: `https://social-plugins.line.me/lineit/share?url={encoded_link}`
- Traffic site only (high-safety-value use case)
- Style: small icon link, visible on mobile, unobtrusive on desktop

**Deliverables**: `pages/traffic/index.html`, `pages/ffxiv/index.html`,
`src/analyzer.py` (prompt extension only).

---

## Phase 3 — Visual Polish

### P3-A: Importance card tints
Apply a very faint background tint to article cards based on importance, guiding
the eye without overwhelming the design.

- 高: faint red tint (`rgba(220,38,38,.06)` light / `rgba(220,38,38,.10)` dark)
- 中: no change (current neutral background)
- 低: no change
- CSS-only addition to both `index.html` files

### P3-B: WCAG contrast audit
Measure and fix contrast ratio of 🟡 Medium-importance text and any other
elements that fall below WCAG AA (4.5:1 for normal text) in dark mode.

- Audit tool: browser DevTools accessibility panel
- Fix: adjust CSS custom property values for dark theme only if needed
- Affected files: both `index.html` files (CSS variables section)

**Deliverables**: CSS changes in both `index.html` files only.

---

## Out of scope for this epic

| Feature | Reason |
|---|---|
| Image previews | Hotlinking risk; requires per-source thumbnail extraction logic |
| FFXIV job/category icons | Requires manual categorization; low signal value |
| Lazy loading | Article count (10–20) too small to matter |
| Per-category scraping frequency | Separate architectural topic |

---

## Phase order & merge strategy

Implement phases in order (1 → 2 → 3). Each phase is a separate commit or
small set of commits on this branch. Open a single PR for all phases when
Phase 3 is complete.
