# Data Model: Extend to Garyu News Scraper (FFXIV Integration)

**Date**: 2026-05-03
**Branch**: `epic/extend-to-garyu-news-scraper`

## Entities

### Article (pipeline dict)

Produced by `collector.py`, consumed by all downstream stages.

```python
{
    "title":        str,   # Article/thread title, stripped (non-empty)
    "link":         str,   # Canonical URL (synthetic urn: if absent)
    "source":       str,   # Source name from config (e.g., "Reddit r/ffxiv")
    "published":    str,   # RFC2822 date string, or "" if unavailable
    "summary":      str,   # Raw excerpt ≤500 chars, or "[JP Forum] {title}" for forum sources
    "content_type": str,   # "traffic" | "ffxiv"  ← NEW; set by collector from source config
}
```

### Analysis (JSONB stored in Supabase `analysis` column)

Produced by `analyzer.py`. Structurally identical for both content types to keep
storage and sorting logic unchanged.

```python
{
    "summary":           str,        # 2-3 sentences on content core
    "analysis":          str,        # 4-6 sentences on impact/implications
    "importance":        str,        # "高" | "中" | "低"
    "importance_reason": str,        # One sentence
    "tags":              list[str],  # 2-4 tags (content-type-specific tag pool)
}
```

**Traffic importance criteria** (existing, unchanged):
- 高: Fatal/serious accident, nationwide policy enacted, major road safety threat.
- 中: Local accident, policy draft/discussion, road works update.
- 低: Informational/event, follow-up with no new info.

**FFXIV importance criteria** (new):
- 高: Major patch content — new raids (零式/絕境戰), full job revamps, expansion content.
- 中: Balance patches, limited events, QoL changes, new side content.
- 低: Minor hotfixes, announcements with no immediate gameplay change, community polls.

### Supabase `articles` table (extended)

```sql
-- Existing columns (unchanged):
id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid()
week_id              TEXT        NOT NULL                 -- e.g., "2026-W18"
title                TEXT        NOT NULL
link                 TEXT        NOT NULL UNIQUE          -- upsert conflict key
source               TEXT
published            TEXT
summary              TEXT
analysis             JSONB
content_fingerprint  TEXT
created_at           TIMESTAMPTZ DEFAULT now()

-- NEW column (migration 002_add_content_type.sql):
content_type         TEXT        NOT NULL DEFAULT 'traffic'
```

Migration SQL:
```sql
ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'traffic';

CREATE INDEX IF NOT EXISTS articles_content_type_idx
  ON articles (content_type);
```

### Source config entry

**Traffic** (`sources_traffic.yml` / `SOURCES_TRAFFIC_YML`) — existing schema, unchanged:
```yaml
sources:
  - name: "..."
    type: "rss" | "ptt" | "web"
    url: "..."         # rss and web
    board: "..."       # ptt only
    enabled: true
```

**FFXIV** (`sources_ffxiv.yml` / `SOURCES_FFXIV_YML`) — new schema:
```yaml
sources:
  # type: rss — reuses existing _fetch_rss logic
  - name: "Reddit r/ffxiv"
    type: "rss"
    url: "https://www.reddit.com/r/ffxiv/new/.rss"
    enabled: true
    content_type: "ffxiv"

  # type: html_patch — Lodestone-style static news listing
  - name: "FFXIV Lodestone JP Updates"
    type: "html_patch"
    url: "https://jp.finalfantasyxiv.com/lodestone/news/category/2"
    enabled: true
    content_type: "ffxiv"
    selector: "li.news__list--topics"   # CSS selector for item elements
    title_selector: "p.news__list--title"
    link_attr: "href"                   # attribute on the <a> wrapping the item
    max_items: 10

  # type: html_forum — Square Enix vBulletin forum thread listing
  # Collects thread titles + links only; full thread body is behind OAuth login.
  - name: "FFXIV JP Forum"
    type: "html_forum"
    url: "https://forum.square-enix.com/ffxiv/forums/512-Japanese-Forums"
    enabled: true
    content_type: "ffxiv"
    max_items: 15
    # Thread link pattern: threads/[ID]-[SLUG] — detected automatically
```

### KnowledgeBaseEntry (`knowledge-base.md` row)

Plain markdown table. One header row, one separator row, then data rows.

```
| JP Term      | TW Term   | EN Term       | Category | Notes                           |
|--------------|-----------|---------------|----------|---------------------------------|
| 零式         | 零式      | Savage        | Raid     | High-end 4-player raid tier     |
| 絶討伐戦     | 絕境戰    | Ultimate      | Raid     | Highest-difficulty content      |
| ノーマル難易度 | 一般難易度 | Normal        | Raid     | Entry-level raid tier           |
```

Python load signature:
```python
def load_knowledge_base(path: str = "knowledge-base.md") -> dict:
    """
    Returns mapping: {jp_term: {"tw": str, "en": str, "category": str, "notes": str}}
    Skips header and separator rows. Logs warning if file missing or empty.
    """
```

Prompt injection format (condensed, to limit token usage):
```
【FFXIV知識庫 — 請使用以下對照翻譯，不得自行發明】
零式 → 零式（Savage）
絶討伐戦 → 絕境戰（Ultimate）
...
```

## State Transitions

```
sources_ffxiv.yml entry  { content_type: "ffxiv" }
    │
    ▼ collector.py  _fetch_rss / _fetch_html_patch / _fetch_html_forum
Article dict  { content_type: "ffxiv", title, link, summary, ... }
    │
    ▼ filter.py  filter_and_deduplicate()
    │   - FFXIV: keyword pass-through for RSS (already curated);
    │             light relevance check for HTML sources
    │   - Dedup: same MD5 hash on normalized title as traffic
    │
Filtered article
    │
    ▼ analyzer.py  analyze_article()
    │   - content_type == "ffxiv" → load_knowledge_base() + FFXIV_ANALYSIS_TEMPLATE
    │   - content_type == "traffic" → existing ANALYSIS_PROMPT_TEMPLATE
    │
Article with analysis dict
    │
    ▼ storage.py  upsert_articles()
    │   - Row includes content_type field
    │
Supabase row  { content_type: "ffxiv", week_id, title, link, analysis, ... }
    │
    ▼ workers/api/index.js  (GET /articles?content_type=ffxiv)
    │
Frontend / email digest
```

## Validation Rules

- `content_type` MUST be `"traffic"` or `"ffxiv"` at the collector boundary; any
  unrecognized value MUST trigger a log warning and default to `"traffic"`.
- `link` MUST be non-empty after collection; synthetic `urn:` link used as fallback
  (existing behavior unchanged).
- `week_id` format: `YYYY-WWW` (e.g., `2026-W18`).
- `knowledge-base.md` MUST contain ≥1 data row before `analyze_article()` is called
  for `content_type == "ffxiv"`; otherwise raise `RuntimeError`.
- Forum source (`html_forum`): `summary` field MUST be prefixed `"[JP Forum] "` to
  distinguish title-only entries from full-body summaries in the pipeline.
