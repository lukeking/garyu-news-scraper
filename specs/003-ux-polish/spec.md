# Feature Specification: Site UX Polish

**Feature Branch**: `003-ux-polish`
**Created**: 2026-05-04
**Status**: Draft

## Clarifications

### Session 2026-05-04

- Q: Should dismissed-article state be stored in the database? → A: No — dismissed state stays in localStorage (per-device). Pipeline handles automatic filtering instead.
- Q: What dedup signal should the pipeline use? → A: Option A — title fingerprint (sha256 of normalized title), no HTTP redirects to avoid being blocked.
- Q: What is the definition of "recycled news"? → A: Two distinct problems: (1) articles already stored in Supabase from a previous week (title fingerprint match); AND (2) articles whose actual publication date is more than 30 days ago, regardless of Supabase history. Google News re-surfaces old articles with a fresh RSS date, so RSS date alone is not a reliable age signal for Google News sources.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pipeline Freshness Filter (Priority: P1)

A reader notices the weekly report contains articles that were actually published months ago and re-surfaced by Google News with a fresh RSS timestamp. They want the pipeline to automatically exclude articles that lack real-time sensitivity — both articles already collected in previous weeks, and brand-new articles whose true publication date is more than 30 days old.

**Why this priority**: Root-cause fix for the stale-article problem — no manual reader action required. Two-layer approach covers both recycled articles and genuinely old content Google News promotes as fresh.

**Independent Test**: Submit a Google News article whose actual origin URL embeds a date from 2 months ago — it must be absent from the pipeline output. Also submit an article URL already in Supabase from 3 weeks ago — it must also be absent.

**Acceptance Scenarios**:

1. **Given** an article's normalized title fingerprint matches any existing Supabase record, **When** the pipeline runs, **Then** the article is excluded as a previously-seen recycled item.
2. **Given** an article comes from a direct RSS source (non-Google-News) and its RSS `<pubDate>` is more than 30 days old, **When** the pipeline runs, **Then** the article is excluded as lacking real-time sensitivity.
3. **Given** a Google News article whose origin URL embeds a date older than 30 days, **When** the pipeline runs, **Then** the article is excluded via URL-date extraction (no HTTP request made).
4. **Given** a Google News article with no detectable date in its URL and no Supabase history match, **When** the pipeline runs, **Then** the article is included (graceful limitation — cannot determine true age without scraping).
5. **Given** the Supabase query fails, **When** the pipeline runs, **Then** the pipeline continues using only the age filter; a warning is logged.
6. **Given** an article is filtered by either signal, **When** the pipeline logs output, **Then** the log entry includes the article title and the reason for exclusion (fingerprint match or age filter).

---

### User Story 2 - Mark News as Outdated (Priority: P2)

A reader wants to manually dismiss an article the automatic filter missed, so it no longer appears on their device.

**Why this priority**: Safety net for edge cases the pipeline filter cannot catch (e.g., Google News articles with no detectable date and no Supabase history). Entirely client-side.

**Independent Test**: Click "標記過時" on any card, reload the page — the dismissed article must not reappear.

**Acceptance Scenarios**:

1. **Given** an article is visible, **When** the user clicks "標記過時", **Then** the card is immediately hidden and the article's URL is stored in the browser's local storage.
2. **Given** a dismissed article exists in local storage, **When** the page loads or the user switches weeks, **Then** the dismissed article does not appear in the list.
3. **Given** multiple articles are dismissed, **When** the user filters by importance or tag, **Then** dismissed articles remain hidden across all filter states.
4. **Given** dismissed articles exist in local storage, **When** the user clears browser data or uses a different browser, **Then** dismissed articles reappear (per-device by design).

---

### User Story 3 - Dark / Light Theme Toggle (Priority: P3)

A reader who prefers dark mode wants to switch the site to a dark colour scheme, with their preference remembered across visits.

**Why this priority**: High-impact comfort feature; zero backend dependency.

**Independent Test**: Toggle to dark mode, close the tab, reopen the site — dark mode must still be active.

**Acceptance Scenarios**:

1. **Given** the site is in light mode (default), **When** the user clicks the theme toggle, **Then** the entire page switches to a dark colour scheme instantly.
2. **Given** the user has selected dark mode, **When** they close and reopen the site, **Then** dark mode is restored automatically.
3. **Given** the user's OS is set to dark mode preference, **When** they first visit the site with no stored preference, **Then** dark mode is pre-applied automatically.
4. **Given** the user is in dark mode, **When** they click the theme toggle again, **Then** the site returns to light mode and that preference is saved.

---

### User Story 4 - Collected-Time Date Label (Priority: P4)

A reader notices the displayed date does not match the article's original publication date. A corrected label makes clear the date is when the scraper collected the article.

**Why this priority**: One-line label change; removes confusion with minimal effort.

**Independent Test**: All article cards show "收錄時間" before the date value.

**Acceptance Scenarios**:

1. **Given** any article card, **When** a date is displayed, **Then** it is prefixed with "收錄時間" rather than implying original publication date.
2. **Given** an article with no date value, **When** the card renders, **Then** no date element is shown.

---

### User Story 5 - FFXIV Site RSS Feed (Priority: P5)

A reader wants to subscribe to the FFXIV weekly report via RSS.

**Why this priority**: Parity with the traffic site. Requires a pipeline change to generate the feed file.

**Independent Test**: After a weekly run, `pages/ffxiv/feed.xml` exists and is valid RSS; the FFXIV site header shows a working RSS link.

**Acceptance Scenarios**:

1. **Given** a completed weekly FFXIV pipeline run, **When** the FFXIV site is loaded, **Then** an RSS subscription link is visible in the header.
2. **Given** the RSS link is clicked, **When** a feed reader requests the URL, **Then** a valid RSS document is returned containing the current week's FFXIV articles.
3. **Given** multiple weekly runs have occurred, **When** the feed is fetched, **Then** it contains articles from at most the 3 most recent weeks.

---

### Edge Cases

- What if the Supabase query fails? → Pipeline continues using only the URL-date age filter; a warning is logged. No crash.
- What if a Google News article has no detectable date in its URL and no Supabase history? → Article is included; this is a known limitation without HTTP scraping.
- What happens if a user dismisses all articles in a week? → The list shows an empty state with a "清除過時標記" action to restore dismissed articles for that device.
- What if localStorage is unavailable? → Dismiss hides the card for the session only; no error shown.
- What if the FFXIV pipeline produces no articles? → `feed.xml` is still generated with no `<item>` elements.
- What if the user's OS theme preference changes after the page loads? → No auto-update; only the toggle or a fresh page load re-evaluates.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Before analysis, the pipeline MUST compute a normalized title fingerprint (sha256 of lowercased, punctuation-stripped title) for each collected article and exclude any article whose fingerprint matches an existing Supabase record.
- **FR-002**: Before analysis, the pipeline MUST apply an age filter: for non-Google-News sources, articles whose RSS `<pubDate>` is more than 30 days old MUST be excluded; for Google News sources, articles whose origin URL contains an extractable date older than 30 days MUST be excluded (no HTTP requests).
- **FR-003**: For each article excluded by either filter, the pipeline MUST log the article title and the exclusion reason (fingerprint match / age filter).
- **FR-004**: If the Supabase fingerprint query fails, the pipeline MUST log a warning and continue using only the age filter (no crash).
- **FR-005**: Each article card MUST display a dismiss button labelled "標記過時" that hides the card immediately upon click.
- **FR-006**: Dismissed article URLs MUST be persisted in the browser's local storage, keyed per site (`dismissed-traffic` / `dismissed-ffxiv`).
- **FR-007**: On page load and on week/filter changes, locally-dismissed articles MUST be excluded from the rendered list.
- **FR-008**: When all visible articles in a week are dismissed, the list MUST show an empty state with a "清除過時標記" action that clears the dismissed set for that site.
- **FR-009**: The site header MUST include a theme toggle button accessible on all views.
- **FR-010**: Theme preference (light / dark) MUST be persisted in the browser's local storage.
- **FR-011**: On first visit with no stored theme preference, the site MUST apply the user's OS-level colour scheme preference.
- **FR-012**: Article date labels MUST read "收錄時間" on both the traffic and FFXIV sites.
- **FR-013**: The FFXIV weekly pipeline MUST generate `pages/ffxiv/feed.xml` in valid RSS 2.0 format.
- **FR-014**: The FFXIV site header MUST include an RSS subscription link pointing to `feed.xml`.

### Key Entities

- **TitleFingerprint**: sha256 of the article's normalized title (lowercased, punctuation stripped); computed per article before Supabase insertion; used as the cross-week dedup signal.
- **DismissedArticle**: An article URL stored in the browser's local storage per site; cleared via "清除過時標記". No server-side representation.
- **ThemePreference**: A `light` | `dark` value in the browser's local storage; applied on every page load.
- **FFXIVFeed**: An RSS 2.0 document generated by the weekly pipeline, analogous to the existing traffic feed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Articles already in Supabase (any previous week, matched by title fingerprint) do not appear in the new week's output — verified by the manual insertion test.
- **SC-002**: Direct-RSS articles older than 30 days are excluded from the weekly output — verified by injecting a test article with a date 35 days in the past.
- **SC-003**: Google News articles whose URL embeds a date older than 30 days are excluded — verified by injecting a test URL with an embedded old date.
- **SC-004**: A locally-dismissed article does not reappear after page reload on the same device.
- **SC-005**: Theme preference persists across browser sessions on the same device.
- **SC-006**: All date displays on both sites carry the "收錄時間" label — zero unlabelled dates.
- **SC-007**: `pages/ffxiv/feed.xml` is present and parseable by a standard feed reader after the next weekly run.

## Assumptions

- The `content_fingerprint` column already exists in the Supabase `articles` table; its purpose is expanded from fallback-key to primary cross-week dedup signal.
- Google News source detection is based on whether `"news.google.com"` appears in the article URL — the same check already present in `_fetch_rss`.
- URL-date extraction uses regex pattern matching against common TW news URL date patterns (e.g., `/YYYY/MM/DD/`, `/YYYYMMDD`); no HTTP requests are made.
- For Google News articles with no detectable URL date and no Supabase history, the pipeline cannot determine true publication age without HTTP scraping; such articles are included by design.
- The 30-day age threshold applies to both traffic and FFXIV pipelines equally.
- Dismissal is per-device via local storage; no user account or login is involved.
- The FFXIV RSS feed reuses the identical code path as the traffic feed with FFXIV-scoped parameters.
- Dark mode colour palette is defined by the implementer; exact values are out of scope.
