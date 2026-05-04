# Research: Site UX Polish

**Feature**: `specs/003-ux-polish/spec.md`
**Date**: 2026-05-04

## Decision 1: Title Fingerprint Algorithm

**Decision**: sha256 of the article title after lowercasing and stripping all characters that are not alphanumeric, CJK unified ideographs (U+4E00–U+9FFF), or hiragana/katakana (U+3040–U+30FF).

**Rationale**: Punctuation differences between re-surfaced versions of the same article should not create distinct fingerprints. The regex `[^\w一-鿿぀-ヿ]` applied after `.lower()` achieves this while retaining all meaningful characters in both Latin and Japanese/Chinese text. `\w` in Python (without `re.ASCII`) already includes Unicode word characters, so CJK characters are technically covered by `\w` on CPython; the explicit ranges are belt-and-suspenders for clarity and forward compatibility.

**Implementation**: `re.sub(r'[^\w一-鿿぀-ヿ]', '', title.lower().strip())`

**Alternatives considered**:
- MD5 (faster, but collision risk; already used in the existing `_make_hash()` for within-run dedup — using sha256 for the cross-week signal avoids confusion between the two hash types).
- Title normalization via Unicode NFKC then strip — more thorough but adds complexity; unnecessary for the article titles in scope.

---

## Decision 2: Where to Store the Title Fingerprint

**Decision**: Reuse the existing `content_fingerprint` column in the `articles` table, but expand it to be populated for ALL articles (currently only populated for URL-less articles). The value stored changes from sha256(title+source+published) to sha256(normalized_title_only).

**Rationale**: Adding a new column would require a DB schema migration and permission change. The `content_fingerprint` column was already flagged in the spec assumptions as the intended cross-week dedup signal. The existing `stable_synthetic_link()` function generates the synthetic URN *link* (which uses a different, more precise hash internally); the link itself is the upsert key, not the column. Changing the column value does not affect upsert idempotency.

**Migration note**: Existing rows have `content_fingerprint = NULL` (for URL articles) or sha256(title+source+published) (for URL-less articles). After this change, new weekly runs populate all rows with the title-only fingerprint. Old rows will not match new fingerprints, so cross-week dedup only works going forward from the first run after deployment. This is acceptable per spec — dedup effectiveness improves over time.

**Alternatives considered**:
- New `title_fingerprint` column: cleanest semantically, but requires DB migration and Supabase schema change; rejected to minimize operational overhead.
- Query by `link` for dedup: less reliable per spec (Google News URLs can change across re-surfacing events).

---

## Decision 3: Google News Detection

**Decision**: Detect Google News URLs by checking `"news.google.com" in article["link"]`. This is the existing pattern already present in `collector.py`'s `_fetch_rss()`.

**Rationale**: Consistent with the existing codebase; no new detection logic required. The spec explicitly states this same check as the assumption.

---

## Decision 4: URL-Date Extraction Patterns

**Decision**: Extract the publication date from a URL using two regex patterns applied in order:

1. `r'/(\d{4})[/-](\d{2})[/-](\d{2})/'` — matches `/YYYY/MM/DD/` or `/YYYY-MM-DD/`
2. `r'[/_-](\d{4})(\d{2})(\d{2})[/_.\-]'` — matches `/YYYYMMDD` or `_YYYYMMDD` or `-YYYYMMDD` followed by a separator

Both patterns are common in TW and JP news URLs (e.g., UDN, ETtoday, NHK).

**Rationale**: No HTTP requests; purely structural. The two patterns cover the vast majority of TW/JP news URL date embedding conventions. The fallback for unmatched URLs is inclusion (per spec SC-004 and the known-limitation acceptance scenario).

**Alternatives considered**:
- More elaborate regex covering more formats — YAGNI; the two patterns cover the actual source URLs in scope.
- Third-party URL parsing library — unnecessary; stdlib `re` is sufficient.

---

## Decision 5: Age Threshold Application by Source Type

**Decision**:
- Non-Google-News RSS sources: use the parsed RSS `<pubDate>` (feedparser `published_parsed` attribute) as the article age signal; exclude if age > 30 days.
- Google News sources: use URL-date extraction; exclude if extracted date > 30 days old; if no date is extractable, **include** the article (known limitation per spec).

**Rationale**: RSS `<pubDate>` from direct sources is generally reliable. Google News re-stamps `<pubDate>` with the recirculation date (the root cause of the stale-article problem), so the URL-embedded date is the only available real-age signal without HTTP scraping.

**Threshold**: 30 days is the spec-defined value; stored as `FRESHNESS_THRESHOLD_DAYS = 30` in `filter.py`.

---

## Decision 6: localStorage Key Naming

**Decision**:
- Dismissed articles (traffic): `dismissed-traffic` → JSON array of URL strings
- Dismissed articles (FFXIV): `dismissed-ffxiv` → JSON array of URL strings
- Theme preference (both sites): `theme` → `"light"` or `"dark"` (each site is a separate Cloudflare Pages deployment with its own localStorage partition)

**Rationale**: Scoped keys prevent cross-contamination if the two sites share a domain in the future. `theme` is simple and idiomatic.

**Alternatives considered**:
- Single shared `dismissed` key: rejected (traffic and FFXIV articles may share URL patterns, and dismissal should be site-scoped).
- `garyu-theme-preference`: more explicit but unnecessarily verbose for a localStorage key.

---

## Decision 7: FFXIV RSS Feed Parameters

**Decision**: Add optional `feed_title` and `feed_description` parameters to `publisher.py`'s `build_feed()` function, defaulting to the existing traffic values. `publish()` passes them through. `FFXIVCategory.publish()` supplies FFXIV-specific strings.

**FFXIV feed values**:
- Title: `最終幻想XIV 週報`
- Description: `每週自動彙整 FFXIV 遊戲相關資訊，含 AI 摘要與重點分析`
- Language: `ja` (JP-focused sources) — actually `zh-tw` since the site is Traditional Chinese; keep `zh-tw` for consistency

**Rationale**: The `publish()` function already calls `build_feed()` for both pipeline types. A two-parameter extension is the minimal change. Default values preserve backward compatibility with the traffic pipeline.

**Alternatives considered**:
- Detect feed type from `output_dir` string: fragile (couples to directory naming convention).
- Separate `build_ffxiv_feed()` function: code duplication; rejected per YAGNI.

---

## Decision 8: Dark Mode CSS Strategy

**Decision**: CSS custom properties (variables) on `:root` for light mode defaults; a `[data-theme="dark"]` attribute on `<html>` overrides the variables. No external CSS framework.

**Rationale**: Both sites are already single-file SPAs using inline `<style>`. A `data-theme` attribute toggle is the minimal, framework-free approach. JavaScript sets `document.documentElement.setAttribute('data-theme', 'dark')` on toggle.

**Alternatives considered**:
- `prefers-color-scheme` CSS media query only (no toggle): does not satisfy FR-009/FR-010 (must remember preference).
- Class-based toggle (`.dark` on `<body>`): functionally equivalent; `data-theme` is semantically cleaner for theme switching.
