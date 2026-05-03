# Contract: Sources Configuration Schema

Both `sources_traffic.yml` (traffic) and `sources_ffxiv.yml` (FFXIV) share the same base schema.

## Base fields (all source types)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | ✅ | — | Human-readable label used in article `source` field |
| `type` | string | ✅ | — | `rss` \| `ptt` \| `web` \| `html_patch` \| `html_forum` |
| `enabled` | boolean | — | `true` | Set `false` to skip without removing the entry |
| `content_type` | string | — | `"traffic"` | `"traffic"` \| `"ffxiv"` — propagated to every article produced |

## Type: `rss`

Handled by existing `_fetch_rss()`. Works for both traffic and FFXIV RSS feeds.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | ✅ | RSS or Atom feed URL |

Example:
```yaml
- name: "Reddit r/ffxiv"
  type: "rss"
  url: "https://www.reddit.com/r/ffxiv/new/.rss"
  enabled: true
  content_type: "ffxiv"
```

## Type: `ptt`

Handled by existing `_fetch_ptt()`. Traffic sources only.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `board` | string | ✅ | — | PTT board name (e.g., `biker`) |
| `min_pushes` | integer | — | `5` | Minimum push count to include an article |

## Type: `web`

Handled by existing `_fetch_web()`. Keyword-filtered generic HTML scraper.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | string | ✅ | — | Page URL to scrape |
| `max_items` | integer | — | `10` | Maximum articles to extract |

## Type: `html_patch` (NEW — FFXIV)

Structured news-listing pages (e.g., Lodestone). Uses configurable CSS selectors.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | string | ✅ | — | HTML page URL |
| `selector` | string | ✅ | — | CSS selector for each news item container element |
| `title_selector` | string | — | `"a"` | CSS selector for title text within the item |
| `link_attr` | string | — | `"href"` | Attribute on the link element within the item |
| `max_items` | integer | — | `10` | Maximum items to extract |
| `content_type` | string | ✅ | — | MUST be `"ffxiv"` |

Example:
```yaml
- name: "FFXIV Lodestone JP Updates"
  type: "html_patch"
  url: "https://jp.finalfantasyxiv.com/lodestone/news/category/2"
  enabled: true
  content_type: "ffxiv"
  selector: "li.news__list--topics"
  title_selector: "p.news__list--title"
  max_items: 10
```

## Type: `html_forum` (NEW — FFXIV)

vBulletin-style forum listing pages. Collects thread titles + links only;
full thread bodies are NOT fetched (may require authentication).

Thread links are auto-detected via the `threads/[ID]-[SLUG]` href pattern.
Article `summary` is set to `"[JP Forum] " + title` to indicate title-only content.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | string | ✅ | — | Forum index or sub-forum page URL |
| `max_items` | integer | — | `15` | Maximum thread entries to extract |
| `content_type` | string | ✅ | — | MUST be `"ffxiv"` |

Example:
```yaml
- name: "FFXIV JP Forum"
  type: "html_forum"
  url: "https://forum.square-enix.com/ffxiv/forums/512-Japanese-Forums"
  enabled: true
  content_type: "ffxiv"
  max_items: 15
```

## Invariants

- Every source entry MUST have a non-empty `name` — used in Supabase `source` column.
- `content_type` absent on a source defaults to `"traffic"` in the collector.
- Sources with `enabled: false` MUST be silently skipped; no warning logged.
- Unrecognized `type` values MUST log a warning and skip (existing behavior).
