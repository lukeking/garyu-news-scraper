# Contract: Article Dict Schema

The article dict is the shared data structure passed between all pipeline stages.
Every stage that produces or consumes articles MUST conform to this contract.

## Fields

| Field | Type | Set by | Required | Description |
|-------|------|--------|----------|-------------|
| `title` | string | collector | ✅ | Title text, stripped of leading/trailing whitespace |
| `link` | string | collector | ✅ | Canonical URL; synthetic `urn:` if none available |
| `source` | string | collector | ✅ | Source `name` from config |
| `published` | string | collector | (empty if unknown) | RFC2822 date string or `""` |
| `summary` | string | collector | (empty if unknown) | Raw excerpt ≤500 chars; `"[JP Forum] {title}"` for `html_forum` sources |
| `content_type` | string | collector | ✅ | `"traffic"` \| `"ffxiv"` |
| `analysis` | dict | analyzer | Added by analyzer | See Analysis schema below |

## Analysis sub-dict

Added to the article dict by `analyzer.py`. Absent until analysis stage runs.

| Field | Type | Description |
|-------|------|-------------|
| `summary` | string | 2-3 sentence summary |
| `analysis` | string | 4-6 sentence impact analysis |
| `importance` | string | `"高"` \| `"中"` \| `"低"` |
| `importance_reason` | string | One sentence rationale |
| `tags` | list[str] | 2-4 topic tags |

## Invariants

1. `title` MUST be non-empty after stripping; articles with empty titles are dropped
   in `filter.py` (existing behavior).
2. `link` MUST be non-empty; `storage.py` generates a synthetic `urn:` link if absent.
3. `content_type` MUST be set by `collector.py` before the article reaches `filter.py`.
   Any stage reading `content_type` MUST treat an absent/unrecognized value as `"traffic"`.
4. `analysis` is absent until `analyzer.py` processes the article. Stages downstream of
   the analyzer (storage, publisher) MUST handle its absence gracefully with a fallback.
5. `summary` from `html_forum` sources is prefixed `"[JP Forum] "`. The analyzer uses this
   as a signal that only the title is available for context.

## content_type dispatch summary

| Stage | traffic | ffxiv |
|-------|---------|-------|
| `filter.py` | `MUST_INCLUDE` motorcycle keywords | Light relevance check; RSS articles pass through |
| `analyzer.py` | `ANALYSIS_PROMPT_TEMPLATE` | `FFXIV_ANALYSIS_TEMPLATE` + knowledge base injection |
| `storage.py` | `content_type='traffic'` in row | `content_type='ffxiv'` in row |
| `publisher.py` | Traffic section | FFXIV section |
