# Quickstart: Site UX Polish — Integration Test Scenarios

**Feature**: `specs/003-ux-polish/spec.md`
**Date**: 2026-05-04

These scenarios verify the feature end-to-end. Each can be run independently.

---

## Scenario 1: Pipeline Freshness Filter — Cross-Week Dedup (P1, SC-001)

**Precondition**: At least one article exists in Supabase from a previous week run.

**Steps**:
1. Identify the `title` of an existing Supabase article (any week_id).
2. Add a test article to the raw collect output with the same title (same exact text). This article must have a different `link` (so it won't be deduped by the existing URL-based upsert key).
3. Run `freshness_filter([test_article], existing_fingerprints)` where `existing_fingerprints = get_existing_title_fingerprints()`.
4. Assert the test article is NOT in the return value.
5. Assert a log entry at INFO level contains the word "fingerprint" and the article title.

**Expected outcome**: The test article is excluded. The log explains why.

---

## Scenario 2: Pipeline Freshness Filter — Age Gate, Direct RSS (P1, SC-002)

**Precondition**: None (no Supabase required; pass `existing_fingerprints=set()`).

**Steps**:
1. Construct a test article with:
   - `link`: any non-Google-News URL (e.g., `https://news.example.com/article-123`)
   - `published`: RFC 2822 date string 35 days in the past
   - `title`: unique string not in Supabase
2. Run `freshness_filter([test_article], set(), threshold_days=30)`.
3. Assert the return value is empty.
4. Assert a log entry at INFO level contains "age" or "過時" and the article title.

**Expected outcome**: Article excluded by age. Log explains why.

---

## Scenario 3: Pipeline Freshness Filter — Age Gate, Google News URL Date (P1, SC-003)

**Steps**:
1. Construct a test article with:
   - `link`: a Google News-style URL containing a date 35+ days ago, e.g. `https://news.google.com/rss/articles/xxx?hl=zh-TW&…` — note: in practice, the origin URL is in the article dict's `link` after redirect; for the test, use a direct TW news URL with embedded date like `https://udn.com/news/story/1234/2025-12-01/article` which is > 30 days from 2026-05-04
   - Actually: the `link` field on a Google News RSS article points to the Google News URL; the test simulates a case where the origin URL (linked from) contains an old date. Re-read spec: "Google News article whose origin URL embeds a date older than 30 days". In the implementation, `article["link"]` IS the Google News URL for RSS articles; the URL-date extraction is applied to `article["link"]` itself for the `news.google.com` detection path. Use a mock URL like `https://news.google.com/articles/CBMi.../details?hl=zh-TW` combined with a test helper that provides an extractable date, OR test `_extract_url_date()` and `_is_too_old_by_age()` in unit tests separately.
2. For the integration test: construct an article with `link` containing an extractable old date pattern (not necessarily Google News, to test `_extract_url_date` in isolation):
   - `link`: `https://example-news.tw/news/2025/01/01/article-about-topic`
   - `source`: any non-Google-News source (to test the pubDate path) — or mark as Google News to test the URL path
3. Run `freshness_filter([test_article], set(), threshold_days=30)`.
4. Assert article is excluded.

**Simpler unit test approach** (preferred):
- `assert _extract_url_date("https://udn.com/news/story/1/2025/01/15/article") == date(2025, 1, 15)`
- `assert _is_too_old_by_age({"link": "https://udn.com/.../2025/01/15/...", "published": ""}, threshold_days=30) is True`

---

## Scenario 4: Dismiss Button — Article Hidden After Click (P2, SC-004)

**Precondition**: Browser with the traffic or FFXIV site open; at least one article visible.

**Steps**:
1. Note the URL of the first visible article card.
2. Click "標記過時" on that card.
3. Verify the card disappears immediately (no page reload).
4. Check `localStorage.getItem('dismissed-traffic')` (or `dismissed-ffxiv`) — it should be a JSON array containing the article's URL.
5. Reload the page.
6. Verify the article does not appear in the list.

**Expected outcome**: Article hidden immediately and remains hidden after reload.

---

## Scenario 5: Dismiss Button — Empty State and Clear (P2)

**Precondition**: Site open with at least one article visible.

**Steps**:
1. Dismiss ALL visible articles in the current week.
2. Verify the "本週所有文章均已標記為過時" empty state appears with "清除過時標記" button.
3. Click "清除過時標記".
4. Verify articles reappear.
5. Verify `localStorage.getItem('dismissed-traffic')` is `"[]"` or null.

---

## Scenario 6: Theme Toggle — Persistence (P3, SC-005)

**Steps**:
1. Open the site in light mode (default).
2. Click the theme toggle button (🌙 → ☀️).
3. Verify the page switches to dark mode instantly (background color changes).
4. Verify `localStorage.getItem('theme')` equals `"dark"`.
5. Close and reopen the browser tab.
6. Verify dark mode is pre-applied (no flash of light mode before dark mode kicks in).
7. Click the toggle again (☀️ → 🌙).
8. Verify light mode is restored and `localStorage.getItem('theme')` equals `"light"`.

---

## Scenario 7: Theme Toggle — OS Preference (P3)

**Steps**:
1. Clear `localStorage.removeItem('theme')`.
2. Set OS to dark mode (system settings) or emulate via browser DevTools → `prefers-color-scheme: dark`.
3. Reload the page.
4. Verify dark mode is applied without clicking the toggle.
5. Verify `localStorage.getItem('theme')` is null or absent (first-visit: OS pref is read but not persisted until user explicitly toggles).

---

## Scenario 8: Date Label (P4, SC-006)

**Steps**:
1. Open the traffic site with at least one article that has a date.
2. Verify every date shown on the page is prefixed with "收錄時間" (not raw date only).
3. Repeat on the FFXIV site.
4. Find an article with no date — verify no date element is rendered (not shown as empty or "收錄時間").

---

## Scenario 9: FFXIV RSS Feed (P5, SC-007)

**Precondition**: FFXIV pipeline has run at least once (or `pages/ffxiv/feed.xml` exists from a test run).

**Steps**:
1. Open `pages/ffxiv/index.html` in browser.
2. Verify the header contains a "📡 RSS 訂閱" link pointing to `./feed.xml`.
3. Click the link — verify a valid XML document loads (or feed reader accepts it).
4. Open `pages/ffxiv/feed.xml` directly and verify:
   - Root element is `<rss version="2.0">`
   - `<title>` is "最終幻想XIV 週報" (not "台灣機車交通週報")
   - `<language>` is "zh-tw"
   - At least one `<item>` if articles exist; zero items if no articles (still valid RSS)

---

## Known Limitations (by design)

- Google News articles with no extractable date in their URL and no Supabase fingerprint match are **included** in output. This is the accepted graceful degradation per spec.
- Dismissed articles reappear when localStorage is cleared or a different browser is used. This is per-device behavior by design.
- OS theme preference change after page load does NOT auto-update the page. A toggle click or reload is required.
