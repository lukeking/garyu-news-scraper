# Contract: Hot Topics API Endpoint

**Feature**: `006-traffic-news-pipeline` | **Date**: 2026-05-12  
**Owner**: `workers/api/` (Cloudflare Worker)

---

## New Endpoint: `GET /api/hot-topics`

Returns hot topic reports for the specified week, or the most recent week if no parameter is given.

### Request

```
GET /api/hot-topics?week=2026-W20
GET /api/hot-topics          (returns latest week)
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `week` | `string` | No | ISO week string, e.g. `2026-W20`. Defaults to most recent week with data. |

### Response — 200 OK

```json
{
  "week": "2026-W20",
  "week_start_date": "2026-05-11",
  "reports": [
    {
      "topic_label": "大型車安全",
      "report_text": "本週大型車視野死角相關事故...",
      "source_article_count": 8,
      "cumulative_score": 2.34,
      "distinct_sources": 5,
      "distinct_days": 4,
      "created_at": "2026-05-11T00:05:32Z"
    }
  ]
}
```

| Field | Type | Notes |
|-------|------|-------|
| `week` | string | ISO week identifier |
| `week_start_date` | string | ISO date of the Monday |
| `reports` | array | 0–3 HotTopicReport objects, ordered by `cumulative_score` desc |
| `reports[].topic_label` | string | Category label from taxonomy |
| `reports[].report_text` | string | Full AI-generated report in Traditional Chinese |
| `reports[].source_article_count` | integer | Articles that fed this analysis |
| `reports[].cumulative_score` | float | The score that qualified this topic |
| `reports[].distinct_sources` | integer | Distinct news outlets |
| `reports[].distinct_days` | integer | Distinct publication days |
| `reports[].created_at` | string | ISO 8601 timestamp |

### Response — 200 OK (no data for week)

```json
{
  "week": "2026-W20",
  "week_start_date": "2026-05-11",
  "reports": []
}
```

Empty `reports` array is returned (not 404) when the week exists but has no qualifying hot topics.

### Response — 400 Bad Request

```json
{ "error": "Invalid week format. Use YYYY-Www (e.g. 2026-W20)." }
```

---

## Existing Endpoint: `GET /api/articles` (no change)

The existing articles endpoint continues to serve FFXIV content. It continues to filter on `content_type`. Traffic articles buffered under the new pipeline will have `hot_topic_analyzed = false` and are NOT surfaced via this endpoint (they are never published as individual articles).

**Breaking change for traffic consumers**: After migration, `GET /api/articles?type=traffic` will return zero results for the current week (traffic articles are no longer published individually). Frontend must switch to `GET /api/hot-topics`.

---

## Frontend Rendering Contract

`pages/shared/app.js` — new function `renderHotTopics(reports)` (traffic-gated, mirrors `renderFFXIVArticles` pattern):

- Called when `contentType === 'traffic'` and the API returns hot topic data
- Renders one card per report: `topic_label` as heading, `report_text` as body, `source_article_count` and `distinct_sources` as metadata
- Empty state: renders a "本週熱點話題尚未產生" message if `reports.length === 0`
- Previous week navigation follows the same `#week-nav` pattern as FFXIV page
