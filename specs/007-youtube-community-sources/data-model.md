# Data Model: YouTube Community Sources

## YouTubeSource (config, not persisted)

Defined as a YAML entry in `sources_traffic.yml`. Fields:

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | yes | — | Human-readable label; stored as `source` on article |
| `type` | string | yes | — | Must be `"youtube"` |
| `enabled` | boolean | no | `true` | Set to `false` to disable without deleting |
| `channel_id` | string | yes | — | YouTube channel ID (starts with `UC`) |
| `max_items` | integer | no | `5` | Max videos to fetch per run (before Shorts filter) |
| `lookback_days` | integer | no | `2` | Only include videos published within this window |

## VideoArticle (in-memory dict, follows existing article shape)

Produced by `_fetch_youtube()` in `src/collector.py`. Fields match the existing article
dict contract so the article flows unchanged through filter → dedup → analyze → store.

| Field | Type | Source | Notes |
|---|---|---|---|
| `title` | string | `snippet.title` | Video title |
| `link` | string | `https://youtube.com/watch?v={id}` | Unique per video; used as upsert key |
| `summary` | string | transcript (truncated to 4000 chars) or title + description[:500] | Input body for Gemini |
| `source` | string | `source["name"]` from config | Channel label |
| `published` | ISO 8601 string | `snippet.publishedAt` | Video publish time |
| `content_type` | string | `"traffic"` | Unchanged — YouTube videos are traffic content |
| `source_type` | string | `"youtube"` | Used by `analyze_article()` for prompt dispatch; **not persisted to Supabase** |
| `transcript_available` | boolean | set by fetcher | `True` if transcript extracted; `False` if fallback used; not persisted |

## Supabase Schema Impact

**No schema changes required.** `VideoArticle` dicts write to the existing `articles` table
via the existing `upsert_traffic_buffer()` path. The `source_type` and `transcript_available`
fields are stripped or ignored at write time (only the standard columns are mapped).

The `link` column (video URL) provides natural idempotency — repeated runs upsert on
`on_conflict="link"` and produce no duplicates.

## Relationships

```
YouTubeSource (config)
    │  1:N (one channel → many videos per run)
    ▼
VideoArticle (dict)
    │  feeds into
    ▼
articles (Supabase table)   ← same destination as RSS/PTT/web articles
```
