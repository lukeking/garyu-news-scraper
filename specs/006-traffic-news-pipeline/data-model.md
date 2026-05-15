# Data Model: Modular News Processing Engine

**Feature**: `006-traffic-news-pipeline` | **Date**: 2026-05-12

---

## Existing Table: `articles` (new columns only)

Migration file: `supabase_migrations/002_traffic_pipeline.sql`

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `major_category` | `TEXT` | YES | `NULL` | Category label from taxonomy; `NULL` for FFXIV articles; `'uncategorised'` for traffic with no keyword match |
| `initial_quality_score` | `FLOAT4` | YES | `NULL` | Algorithmic quality score 0.0–1.0; `NULL` for FFXIV articles |
| `buffered_at` | `TIMESTAMPTZ` | YES | `NULL` | Timestamp when article was first added to traffic buffer; `NULL` for FFXIV articles |
| `buffer_expires_at` | `TIMESTAMPTZ` | YES | `NULL` | `buffered_at + 8 weeks`; `NULL` for FFXIV articles |
| `hot_topic_analyzed` | `BOOLEAN` | YES | `FALSE` | Set `TRUE` when article's bucket is published as a HotTopicReport; prevents re-analysis |

**Index**: `CREATE INDEX idx_articles_traffic_buffer ON articles (major_category, buffer_expires_at) WHERE content_type = 'traffic' AND hot_topic_analyzed = FALSE;`

**Existing unique key**: `link` (unchanged)
**Existing fingerprint**: `content_fingerprint` sha256 (unchanged)

---

## New Table: `hot_topic_reports`

Migration file: `supabase_migrations/002_traffic_pipeline.sql`

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | `UUID` | NO | `gen_random_uuid()` | Primary key |
| `week_start_date` | `DATE` | NO | — | ISO date of the Monday that triggered this analysis (e.g. `2026-05-12`) |
| `topic_label` | `TEXT` | NO | — | Major category label (e.g. `大型車安全`) |
| `report_text` | `TEXT` | NO | — | AI-generated deep-analysis text in Traditional Chinese |
| `source_article_count` | `INTEGER` | NO | — | Number of articles in the bucket at time of analysis |
| `source_article_links` | `JSONB` | NO | `'[]'` | Array of `content_fingerprint` strings for source articles |
| `cumulative_score` | `FLOAT4` | NO | — | Composite topic score that crossed the threshold |
| `distinct_sources` | `INTEGER` | NO | — | Count of distinct news sources contributing to bucket |
| `distinct_days` | `INTEGER` | NO | — | Count of distinct publication days across buffer weeks |
| `created_at` | `TIMESTAMPTZ` | NO | `NOW()` | Insert timestamp |

**Unique constraint**: `UNIQUE (week_start_date, topic_label)` — idempotent re-run of Monday analysis.

**Index**: `CREATE INDEX idx_hot_topic_reports_week ON hot_topic_reports (week_start_date DESC);`

---

## New Config File: `config/categories_traffic.yml`

Stored as GitHub Environment Variable `CATEGORIES_TRAFFIC_YML`. Committed example: `config/categories_traffic.example.yml`.

```yaml
# Seed taxonomy — add new categories here without code changes.
# Each category defines the keywords that trigger assignment.
# An article is assigned the FIRST matching category (priority order).
# Articles matching no category → major_category = 'uncategorised'.
categories:
  大型車安全:
    keywords: [大型車, 聯結車, 貨車, 視野死角, 盲區, 砂石車, 重型車]
  酒駕:
    keywords: [酒駕, 酒後駕車, 酒測, 吹氣, 藥駕]
  道路施工:
    keywords: [施工, 道路工程, 封閉, 改道, 挖掘, 鋪路]
  行人事故:
    keywords: [行人, 斑馬線, 人行道, 行穿線]
  路口安全:
    keywords: [路口, 號誌, 闖紅燈, 轉彎]
  機車事故:
    keywords: [機車, 摩托車, 騎士, 重機, 白牌, 紅牌]
```

---

## New Config File: `config/pipeline_config.yml`

Stored as GitHub Environment Variable `PIPELINE_CONFIG_YML`. Committed example: `config/pipeline_config.example.yml`.

```yaml
jaccard:
  merge_threshold: 0.45      # Jaccard > this → deduplicate (keep higher word count)
  cluster_lower: 0.20        # 0.20–0.45 → cluster into same topic bucket
  game_threshold: 0.50       # Game pipeline: Jaccard > this → discard duplicate

topic_scoring:
  min_threshold: 1.5         # Cumulative score must meet/exceed this to qualify as hot topic
  max_hot_topics: 3          # Maximum hot-topic reports per weekly run

buffer:
  max_age_weeks: 8           # Articles older than this are expired from buffer

quality_score_weights:
  keyword_match_ratio: 0.4
  normalised_word_count: 0.3
  source_weight: 0.3

source_weights:              # Default 0.5 for unlisted sources
  中央社: 0.9
  聯合新聞網: 0.85
```

---

## New Config File: `config/jieba_userdict.txt`

Stored as GitHub Environment Variable `JIEBA_USERDICT_TXT`. Committed example: `config/jieba_userdict.example.txt`.

Plain text, one entry per line (jieba userdict format: `word frequency tag`):

```
台一線 5 n
台九丙 5 n
中山高 5 n
北二高 5 n
3死 10 m
57歲 10 m
3傷 10 m
```

---

## Entity Relationships

```
articles (existing)
  ├── [1] content_type = 'traffic'
  │     ├── major_category        → references categories_traffic.yml key
  │     ├── initial_quality_score → float 0–1
  │     ├── buffered_at           → set at TrafficCategory.publish()
  │     ├── buffer_expires_at     → buffered_at + 8 weeks
  │     └── hot_topic_analyzed    → set TRUE when consumed by weekly analysis
  │
  └── [2] content_type = 'ffxiv'
        └── (existing columns unchanged)

hot_topic_reports
  ├── week_start_date + topic_label → UNIQUE
  └── source_article_links[]        → content_fingerprint refs into articles
```
