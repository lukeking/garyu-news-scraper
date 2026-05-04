# Tasks: Site UX Polish

**Input**: Design documents from `specs/003-ux-polish/`
**Plan**: plan.md | **Spec**: spec.md | **Contracts**: contracts/freshness-filter.md, contracts/frontend-features.md

**Organization**: Tasks grouped by user story. US1 is pipeline-only; US2–US5 are frontend-only. Frontend stories share the same `index.html` files, so within each site they run sequentially.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no cross-dependency)
- **[Story]**: User story label (US1–US5)

---

## Phase 1: Setup

**Purpose**: Confirm current state of all files that will be modified.

- [X] T001 Read `src/filter.py`, `src/storage.py`, `src/pipeline/traffic.py`, `src/pipeline/ffxiv.py`, `src/publisher.py`, `pages/traffic/index.html`, `pages/ffxiv/index.html` to confirm their current structure before any modifications

**Checkpoint**: All 7 files reviewed and understood — implementation can begin

---

## Phase 2: Foundational

No foundational blocking work required. Pipeline stories (US1) and frontend stories (US2–US5) are fully independent. Proceed directly to user story phases.

---

## Phase 3: User Story 1 — Pipeline Freshness Filter (Priority: P1) 🎯 MVP

**Goal**: Exclude stale articles before analysis using a two-layer filter: cross-week title-fingerprint dedup against Supabase history, and a 30-day age gate for both direct RSS and Google News sources.

**Independent Test**: Run a pipeline filter call with a test article whose title matches an existing Supabase record → article must be absent from the output with a fingerprint-match log entry. Run with a test article whose `published` date is 35 days ago → article must be absent with an age-filter log entry.

### Implementation for User Story 1

- [X] T002 [US1] Add to `src/filter.py`: constant `FRESHNESS_THRESHOLD_DAYS = 30`; function `_normalize_title_for_fingerprint(title)` that returns `re.sub(r'[^\w一-鿿぀-ヿ]', '', title.lower().strip())`; function `title_fingerprint(article)` that returns `hashlib.sha256(_normalize_title_for_fingerprint(article.get("title","")).encode()).hexdigest()`; function `_extract_url_date(url)` that tries two regex patterns (`r'/(\d{4})[/-](\d{2})[/-](\d{2})/'` and `r'[/_-](\d{4})(\d{2})(\d{2})[/_.\-]'`) returning a `datetime.date` or `None`; function `_is_too_old_by_age(article, threshold_days)` that checks Google News URL date or RSS pubDate against threshold; function `freshness_filter(articles, existing_fingerprints, threshold_days=FRESHNESS_THRESHOLD_DAYS)` that iterates articles, skips those whose `title_fingerprint()` is in `existing_fingerprints` (logging reason), skips those where `_is_too_old_by_age()` is True (logging reason), and returns the passing articles — per contracts/freshness-filter.md

- [X] T003 [P] [US1] Add to `src/storage.py`: private function `_title_fingerprint(title)` using the same sha256-of-normalized-title algorithm as T002 (independent reimplementation, no import from filter.py); function `get_existing_title_fingerprints()` that calls Supabase `SELECT content_fingerprint FROM articles WHERE content_fingerprint IS NOT NULL`, returns a `set[str]`, logs a WARNING and returns `set()` on any exception or if `is_configured()` is False; modify `upsert_articles()` to always compute `_title_fingerprint(a.get("title",""))` and assign it to `content_fingerprint` in every row dict (removing the existing `fingerprint = None` default for URL-bearing articles, while keeping the `stable_synthetic_link()` call for the `link` field of URL-less articles)

- [X] T004 [US1] Update `filter()` method in `src/pipeline/traffic.py`: import `freshness_filter` and `title_fingerprint` from `src.filter`; import `get_existing_title_fingerprints` and `is_configured` from `src.storage`; before calling `filter_and_deduplicate`, call `get_existing_title_fingerprints()` wrapped in a try/except (on exception log WARNING and use empty set); then call `freshness_filter(raw, existing_fps)` and pass its result to `filter_and_deduplicate()` — pipeline sequence must be: `freshness_filter → filter_and_deduplicate → [:max_articles]`

- [X] T005 [P] [US1] Update `filter()` method in `src/pipeline/ffxiv.py` identically to T004 (same three-step sequence: fetch fingerprints, freshness_filter, filter_and_deduplicate, cap)

**Checkpoint**: US1 complete — run `python -m src.main` locally; confirm log shows "跨週去重跳過" or "過時文章跳過" for any matching articles; confirm pipeline continues if Supabase is unreachable

---

## Phase 4: User Story 2 — Mark News as Outdated (Priority: P2)

**Goal**: Per-device dismiss button on each article card stores the dismissed URL in localStorage and hides the card immediately; dismissed articles stay hidden across page loads and filter changes; an empty state with "清除過時標記" appears when all cards in the current view are dismissed.

**Independent Test**: Click "標記過時" on a card → card disappears; reload page → card absent; `localStorage.getItem('dismissed-traffic')` contains the article URL; dismiss all visible articles → empty state appears with "清除過時標記"; click it → articles reappear.

### Implementation for User Story 2

- [X] T006 [US2] Add dismiss feature to `pages/traffic/index.html`: (1) in the JS function that renders each article card, append `<button class="dismiss-btn" data-url="${article.link}" onclick="dismissArticle(this)">標記過時</button>` as the last element of the card footer; (2) add `function getDismissed()` that returns a `Set` parsed from `localStorage.getItem('dismissed-traffic')` (JSON array, default `[]`), with try/catch returning empty Set on failure; (3) add `function dismissArticle(btn)` that gets the URL from `btn.dataset.url`, calls `getDismissed()`, adds the URL, writes back with `localStorage.setItem('dismissed-traffic', JSON.stringify([...set]))`, hides the card with `btn.closest('.card').style.display='none'`, then calls `checkEmptyDismissed()`; (4) add `function checkEmptyDismissed()` that counts visible cards and if zero, shows `#empty-dismissed-state`; (5) add the empty-state HTML `<div id="empty-dismissed-state" style="display:none" class="empty-state"><p>本週所有文章均已標記為過時。</p><button onclick="clearDismissed()">清除過時標記</button></div>` inside the article list container; (6) add `function clearDismissed()` that sets `dismissed-traffic` to `[]`, hides `#empty-dismissed-state`, and re-triggers the current week render; (7) in the article render loop (after building all cards), call `applyDismissed()` — a function that reads `getDismissed()` and hides any card whose `data-url` is in the set, then calls `checkEmptyDismissed()`. Add `.dismiss-btn` CSS: `font-size:11px; cursor:pointer; color:#999; background:none; border:1px solid #ddd; border-radius:4px; padding:2px 8px;` and `.empty-state { text-align:center; padding:40px; color:#999; }`

- [X] T007 [P] [US2] Add the same dismiss feature to `pages/ffxiv/index.html` using localStorage key `dismissed-ffxiv` (same logic as T006, adjusted key name and any FFXIV-specific class names)

**Checkpoint**: US2 complete — test dismiss flow in browser on both sites; verify localStorage persistence across reload; verify "清除過時標記" restores articles

---

## Phase 5: User Story 3 — Dark/Light Theme Toggle (Priority: P3)

**Goal**: Theme toggle button in header; dark/light mode applied instantly; preference stored in localStorage; OS `prefers-color-scheme` used on first visit with no stored preference.

**Independent Test**: Click theme toggle → page switches mode; close and reopen tab → mode persists; clear `theme` from localStorage, set OS to dark → dark mode pre-applied on load.

### Implementation for User Story 3

- [X] T008 [US3] Add theme toggle to `pages/traffic/index.html`: (1) audit all hardcoded color values in the existing `<style>` block and replace with CSS custom property references (e.g., replace `background:#F5F6FA` with `background:var(--bg)`); (2) define `:root { --bg:#F5F6FA; --surface:#ffffff; --text:#1a1a2e; --text-muted:#666; --border:#e0e0e0; --tag-bg:#E8F4FD; --tag-text:#1A5276; }` and `[data-theme="dark"] { --bg:#1a1a2e; --surface:#2d2d44; --text:#e8e8f0; --text-muted:#aaa; --border:#3d3d5c; --tag-bg:#2d3a4a; --tag-text:#7ec8e3; }`; (3) add `<button id="theme-toggle" onclick="toggleTheme()" style="background:none;border:none;cursor:pointer;font-size:1.2rem;" aria-label="切換主題">🌙</button>` to the right side of the `.site-header` top row; (4) add in `<head>` before `<style>`: `<script>` block that synchronously reads `localStorage.getItem('theme')`, and if absent checks `window.matchMedia('(prefers-color-scheme: dark)').matches`; sets `document.documentElement.setAttribute('data-theme', theme)` before first paint `</script>`; (5) add `function toggleTheme()` that reads current `data-theme`, toggles it, writes to localStorage, updates the button icon (🌙 for light mode, ☀️ for dark mode); (6) on DOM ready, sync the toggle button icon with the current active theme

- [X] T009 [P] [US3] Apply the same theme toggle changes to `pages/ffxiv/index.html` (same logic as T008; replace all hardcoded colors with CSS variables; add dark palette appropriate for the purple FFXIV theme: `[data-theme="dark"]` palette should keep `--accent: #6C3483` and `--accent2: #8E44AD` while darkening backgrounds)

**Checkpoint**: US3 complete — verify theme toggle works on both sites; verify dark mode persists across tab close/reopen; verify OS preference is respected on first visit (clear localStorage then reload in dark OS mode)

---

## Phase 6: User Story 4 — Collected-Time Date Label (Priority: P4)

**Goal**: All article dates on both sites are prefixed with "收錄時間"; no date element shown when value is empty.

**Independent Test**: All cards with a date show "收錄時間 {date}"; cards without a date show no date element.

### Implementation for User Story 4

- [X] T010 [US4] In `pages/traffic/index.html`, find the JS template literal or function that renders the article date (the `article.published` field display). Replace the date span so it reads `${article.published ? '<span class="date-label">收錄時間 ' + article.published + '</span>' : ''}` — removing the date element entirely when `article.published` is falsy. Update any CSS for `.date-label` to match existing date styling (color:#999; font-size:12px).

- [X] T011 [P] [US4] Apply the same "收錄時間" date label change to `pages/ffxiv/index.html` (find the date rendering code and apply identical conditional template)

**Checkpoint**: US4 complete — verify both sites show "收錄時間" prefix on all dates; verify articles without dates show no date element

---

## Phase 7: User Story 5 — FFXIV Site RSS Feed (Priority: P5)

**Goal**: `pages/ffxiv/feed.xml` carries FFXIV-specific channel title/description; FFXIV site header has an RSS subscription link.

**Independent Test**: After a pipeline run, `pages/ffxiv/feed.xml` has `<title>最終幻想XIV 週報</title>` (not the traffic title); `pages/ffxiv/index.html` header shows "📡 RSS 訂閱" link pointing to `./feed.xml`.

### Implementation for User Story 5

- [X] T012 [US5] In `src/publisher.py`, add `feed_title: str = "台灣機車交通週報"` and `feed_description: str = "每週自動彙整台灣機車交通相關新聞，含 AI 摘要與深度分析"` parameters to `build_feed()` and replace the two hardcoded string literals in the `feed = f"""..."""` template with these variables; add the same two parameters (same defaults) to `publish()` and pass them through to the `build_feed(...)` call

- [X] T013 [US5] In `src/pipeline/ffxiv.py`, update `FFXIVCategory.publish()` to call `publish(articles, output_dir=self.output_dir, site_url=self.site_url, feed_title="最終幻想XIV 週報", feed_description="每週自動彙整 FFXIV 遊戲相關資訊，含 AI 摘要與重點分析")`

- [X] T014 [P] [US5] In `pages/ffxiv/index.html`, add `<a href="./feed.xml" class="rss-link" rel="alternate" type="application/rss+xml" title="RSS 訂閱" style="color:rgba(255,255,255,0.85);font-size:13px;text-decoration:none;margin-left:auto;">📡 RSS 訂閱</a>` to the `.site-header` element alongside the existing header content; add `.rss-link:hover { color:#fff; }` to the style block

**Checkpoint**: US5 complete — inspect `pages/ffxiv/feed.xml` and confirm `<title>最終幻想XIV 週報</title>`; verify FFXIV index.html header shows RSS link; verify traffic `feed.xml` still reads "台灣機車交通週報" (backward compat)

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T015 [P] Run quickstart.md Scenarios 1–5 (pipeline scenarios can be run as Python unit calls; browser scenarios via manual verification); confirm no regressions in either site's existing week-list, tag-filter, importance-filter, and search features

- [X] T016 [P] Verify both `pages/traffic/index.html` and `pages/ffxiv/index.html` have no remaining hardcoded hex color values that bypass the CSS variable system introduced in T008/T009 (search for `#` color patterns in the `<style>` blocks; fix any missed replacements)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **US1 (Phase 3)**: Depends on Phase 1; fully independent of US2–US5
- **US2 (Phase 4)**: Depends on Phase 1; independent of US1 and US3–US5
- **US3 (Phase 5)**: Depends on US2 being complete (same `index.html` files — must apply sequentially)
- **US4 (Phase 6)**: Depends on US3 being complete (same files)
- **US5 (Phase 7)**: T012/T013 independent of frontend; T014 depends on US4 (same ffxiv index.html)
- **Polish (Phase 8)**: Depends on all stories complete

### Within User Story 1

```
T002 ──┐
       ├──→ T004
T003 ──┤
       └──→ T005
```

T002 and T003 can start in parallel. T004 and T005 wait for both T002 and T003, then run in parallel.

### Within Frontend Stories (same files — sequential per file)

**Traffic `index.html`**: T006 → T008 → T010
**FFXIV `index.html`**: T007 → T009 → T011 → T014

T006 and T007 can start in parallel (different files). T008 and T009 can start in parallel (different files). Etc.

### Parallel Opportunities

```bash
# US1 — Pipeline layer 1 (parallel):
Task T002: "Add freshness_filter() and helpers to src/filter.py"
Task T003: "Add get_existing_title_fingerprints() to src/storage.py"

# US1 — Pipeline layer 2 (parallel, after T002+T003):
Task T004: "Update traffic.py filter()"
Task T005: "Update ffxiv.py filter()"

# US2 — Dismiss button (parallel — different files):
Task T006: "Add dismiss feature to pages/traffic/index.html"
Task T007: "Add dismiss feature to pages/ffxiv/index.html"

# US3 — Theme toggle (parallel — different files):
Task T008: "Add theme toggle to pages/traffic/index.html"
Task T009: "Add theme toggle to pages/ffxiv/index.html"

# US4 — Date label (parallel — different files):
Task T010: "Add 收錄時間 label to pages/traffic/index.html"
Task T011: "Add 收錄時間 label to pages/ffxiv/index.html"

# Polish (parallel):
Task T015: "Run quickstart.md scenario verification"
Task T016: "Audit CSS variable completeness in both index.html files"
```

---

## Implementation Strategy

### MVP First (US1 Only — Pipeline Health)

1. Complete Phase 1: Setup (T001)
2. Complete US1: T002 → T003 (parallel) → T004 + T005 (parallel)
3. **STOP and VALIDATE**: Run pipeline locally or inspect log output; confirm stale articles excluded
4. Deploy pipeline changes — users immediately benefit from fresher article feed

### Incremental Delivery

1. US1 (pipeline) → deploy → stale articles stop appearing in weekly reports
2. US4 (date label) → deploy → clears up date confusion on both sites (quick 2-task increment)
3. US2 (dismiss button) → deploy → users can manually hide edge-case articles
4. US3 (theme toggle) → deploy → dark mode available
5. US5 (FFXIV RSS) → deploy → FFXIV subscribers get correct feed title + subscription link

---

## Notes

- US1 tasks T002 and T003 implement the same fingerprint algorithm independently — this is intentional (avoids cross-module import)
- Frontend tasks T006–T011 and T014 all edit `index.html` files; within each file, tasks must be applied in order: US2 → US3 → US4 → US5
- The traffic site's `feed.xml` is unaffected by US5 (defaults preserved in publisher.py)
- T013 only needs one line change in `ffxiv.py` (add two kwargs to the `publish()` call)
- After T008/T009, ALL color values in both index.html files must go through CSS variables — verify with T016
