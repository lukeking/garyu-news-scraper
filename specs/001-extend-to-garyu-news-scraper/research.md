# Research: Extend to Garyu News Scraper (FFXIV Integration)

**Date**: 2026-05-03
**Branch**: `epic/extend-to-garyu-news-scraper`

## Decision Log

### 1. Reddit RSS Endpoint for /r/ffxiv

**Decision**: Use `https://www.reddit.com/r/ffxiv/new/.rss` (unauthenticated Atom feed).

**Rationale**:
Reddit still serves public RSS for subreddits without OAuth. The existing `_fetch_rss`
function in `collector.py` already uses `feedparser` + `requests`; the pattern reuses
directly. Fields available: `title`, `link`, `published`, `summary` (HTML-escaped post body
or empty for link posts). One fetch per week is negligible against any rate limit.

**Alternatives considered**:
- Reddit OAuth API: Requires app registration and token refresh; overkill for one fetch/week.
- Pushshift: Deprecated and unreliable.

---

### 2. JP/TW Official FFXIV Site Scraping

**Decision**: Scrape `https://jp.finalfantasyxiv.com/lodestone/news/category/2`
(Lodestone JP, Updates category) using BeautifulSoup HTML parsing. Use `type: html_patch`
in sources config with a CSS `selector` field.

**Rationale**:
Lodestone news pages are standard HTML with list-item news entries parseable by BeautifulSoup.
`robots.txt` for `jp.finalfantasyxiv.com` does not disallow `/lodestone/news/`.
The existing `_fetch_web` function provides the pattern; a new `_fetch_html_patch` function
extends it with configurable CSS selectors and title/link extraction.
The Taiwan site (`www.ffxiv.com.tw`) uses the same approach; robots.txt MUST be checked
before enabling (added to implementation checklist).

**Alternatives considered**:
- Third-party FFXIV APIs (xivapi.com, cafemaker): These are game data APIs, not news feeds.
- Social media polling: Unreliable structure, anti-scraping measures.

---

### 3. Knowledge Base Format

**Decision**: Markdown table in `knowledge-base.md` with columns:
`JP Term | TW Term | EN Term | Category | Notes`.

**Rationale**:
Plain text is easily diffable in PRs and requires no external tooling. The analyzer
loads it at runtime via a simple file read; rows are parsed by splitting on `|`.
Small enough (<500 entries foreseeable) that a flat file outperforms any database.

**Alternatives considered**:
- YAML/JSON: More structured but adds friction for manual PR-based updates.
- Supabase table: Overly complex; increases deployment coupling.

**Loading implementation**:
```python
def load_knowledge_base(path="knowledge-base.md") -> dict:
    """Returns {jp_term: {"tw": tw_term, "en": en_term, "category": cat}} mapping."""
    ...
```
Inject into the FFXIV prompt as a condensed reference block:
```
【知識庫】
零式 → 零式 (Savage)
絶討伐戦 → 絕境戰 (Ultimate)
...
```

---

### 4. Supabase Schema Extension

**Decision**: Add `content_type TEXT NOT NULL DEFAULT 'traffic'` to `articles` via
migration `db/supabase_migrations/002_add_content_type.sql`.

**Rationale**:
Default `'traffic'` preserves all existing rows without backfill. TEXT type is flexible
for future content types. No change to existing upsert logic; only the row dict gains
one new key. An index on `content_type` supports the Worker's filter query efficiently.

**Alternatives considered**:
- Separate `ffxiv_articles` table: Doubles maintenance burden; shared schema aligns with
  constitution III (Idempotency and shared upsert logic).
- PostgreSQL ENUM: Inflexible; adding a new type requires a migration.

---

### 5. Gemini Prompt Design for FFXIV

**Decision**: Separate `FFXIV_SYSTEM_PROMPT` and `FFXIV_ANALYSIS_TEMPLATE` in
`analyzer.py`, dispatching by `content_type`. Knowledge base injected as inline reference.

**Rationale**:
Traffic and FFXIV content require different analytical frames. Mixing prompts risks
contamination. The FFXIV prompt explicitly injects the knowledge base to prevent
hallucinated translations (Principle VI).

**FFXIV analysis output fields** (structurally identical to traffic for storage
compatibility):
- `summary`: 2-3 sentences on the patch change or community discussion topic.
- `analysis`: 4-6 sentences on gameplay impact, accessibility, community reaction.
- `importance`: 高 (major patch content — raids, job revamps), 中 (balance/event/QoL),
  低 (minor patches, announcements with no immediate gameplay change).
- `importance_reason`: One sentence.
- `tags`: FFXIV-specific tags (e.g., "零式", "8.0", "職業調整", "活動", "修正").

**Alternatives considered**:
- Single prompt with `content_type` injection field: Risk of analytical frame leakage.

---

### 6. Backwards Compatibility Strategy

**Decision**: If `SOURCES_FFXIV_YML` is not set (or `config/sources_ffxiv.yml` is absent),
`collector.py` logs a warning and continues with traffic sources only; no pipeline failure.

**Rationale**:
Existing deployments that haven't set `SOURCES_FFXIV_YML` continue to work unchanged.
Enables traffic-pipeline validation independently before enabling FFXIV sources.

---

### 7. Cloudflare Worker API Extension

**Decision**: Add `?content_type=<value>` query parameter support to `workers/api/index.js`.
Default (no parameter): returns all content types (backwards compatible).

**Rationale**:
Allows the frontend to request only traffic or only FFXIV articles without breaking
existing callers. The filter maps to a Supabase REST `content_type=eq.<value>` parameter.

---

### 8. Square Enix JP Forum Scraping

**Decision**: Include `https://forum.square-enix.com/ffxiv/forums/512-Japanese-Forums`
as a `type: html_forum` source. Collect thread titles and links from the publicly
accessible forum index/sub-forum listing pages only. Do NOT attempt to fetch individual
thread content pages.

**Rationale**:
Live inspection of the page confirms it is publicly accessible without login: thread
titles, links, and last-post timestamps are visible to unauthenticated requests.
Thread links follow the pattern `threads/[THREAD_ID]-[URL_ENCODED_TITLE]`.
The forum hierarchy shows sub-forums including ニュース (news) and patch discussion
categories, which are the most relevant to FFXIV news aggregation.

Full thread bodies likely require Square Enix OAuth (login prompt present in page header),
but **thread titles alone are sufficient** for this pipeline: the title is passed to
Gemini as the primary content, and the link is stored for readers to follow.

`robots.txt` for `forum.square-enix.com` redirects to a 404 — no explicit disallow
rules exist, and the content is publicly rendered HTML without a login gate on the
listing pages.

**Implementation approach** (`type: html_forum`):
- Fetch the sub-forum listing page.
- Extract thread `<a>` tags matching the `threads/[ID]-[SLUG]` href pattern.
- Build article dict: `title` = thread title text, `link` = absolute thread URL,
  `summary` = `"[JP Forum] " + title` (no full-body fetch), `published` = "" (dates
  visible in listing but inconsistently formatted across vBulletin versions).
- Limit to `max_items` most recent threads.

**Alternatives considered**:
- Fetching individual thread pages for full body: Requires OAuth; non-starter.
- Filtering by sub-forum: Parameterize via `selector` field in source config to target
  specific sub-forums (e.g., ニュース) rather than the top-level index.

---

### 9. robots.txt Compliance Findings

| Site | Path checked | Disallowed? |
|------|-------------|-------------|
| `jp.finalfantasyxiv.com` | `/lodestone/news/` | Not disallowed ✅ |
| `www.reddit.com` | `/r/ffxiv/new/.rss` | Not disallowed ✅ |
| `forum.square-enix.com` | `/ffxiv/forums/` | No robots.txt found (404 redirect) ✅ |
| `www.ffxiv.com.tw` | `/web/special/patchnote_log/` | **Must verify before enabling** ⚠️ |

Action: Check `www.ffxiv.com.tw/robots.txt` during implementation before adding the TW
site as an enabled source.
