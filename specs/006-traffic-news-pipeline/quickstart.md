# Quickstart: Traffic News Pipeline (Local Development)

**Feature**: `006-traffic-news-pipeline` | **Date**: 2026-05-12

## Prerequisites

All existing prerequisites from the project (`.env`, `config/sources_traffic.yml`, etc.) plus three new config files.

### 1. Create new local config files

```bash
cp config/categories_traffic.example.yml config/categories_traffic.yml
cp config/pipeline_config.example.yml config/pipeline_config.yml
cp config/jieba_userdict.example.txt config/jieba_userdict.txt
```

Edit `config/categories_traffic.yml` to customise the seed taxonomy for local testing.

### 2. Add new env vars to `.env`

```bash
# Paths to the new config files (pipeline reads these at startup)
CATEGORIES_TRAFFIC_YML_PATH=config/categories_traffic.yml
PIPELINE_CONFIG_YML_PATH=config/pipeline_config.yml
JIEBA_USERDICT_PATH=config/jieba_userdict.txt
```

### 3. Install new dependency

```bash
pip install -r requirements.txt   # jieba is now included
```

### 4. Run database migration (one-time)

Apply `supabase_migrations/002_traffic_pipeline.sql` to your Supabase project:
- Supabase dashboard → SQL Editor → paste and run the migration file

---

## Running the Daily Buffer Phase

Collects today's traffic articles, normalises + categorises them, and stores them to the buffer. No AI calls. No frontend publish.

```bash
python scripts/traffic_buffer.py
```

Expected output:
```
[traffic_buffer] 收集到 23 篇原始文章
[traffic_buffer] 過濾後 17 篇（去重、類別指派完成）
[traffic_buffer] ✓ 寫入 buffer：17 筆（week_id=2026-W20）
```

---

## Running the Weekly Analysis Phase (Manual Trigger)

Reads the current week's buffered articles, computes topic scores, selects hot topics, calls Gemini for each, and publishes hot topic reports. Requires at least 3 buffered traffic articles.

```bash
python scripts/traffic_weekly_analysis.py
```

Expected output:
```
[weekly_analysis] 讀取 buffer：45 篇（過去 8 週）
[weekly_analysis] 聚類完成：3 個主題桶
[weekly_analysis] 熱點主題：大型車安全（score=2.34）、酒駕（score=1.89）
[weekly_analysis] Gemini 分析：大型車安全 ✓
[weekly_analysis] Gemini 分析：酒駕 ✓
[weekly_analysis] ✓ 寫入 hot_topic_reports：2 筆
[weekly_analysis] ✓ 前端發布完成
```

If fewer than 3 articles are in the buffer:
```
[weekly_analysis] ⚠ buffer 文章數不足（2 < 3），跳過本週分析
```

---

## Running the Unit Tests

```bash
pytest tests/unit/test_text_normaliser.py -v    # FR-001 to FR-004
pytest tests/unit/test_jaccard.py -v            # FR-005, FR-006
pytest tests/unit/test_category_assign.py -v   # FR-015
pytest tests/unit/test_topic_scoring.py -v     # FR-016, FR-016b
```

---

## Running the Integration Tests

Requires a configured `.env` with `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.

```bash
pytest tests/integration/test_traffic_buffer.py -v
pytest tests/integration/test_weekly_analysis.py -v
```

---

## Verifying Hot Topic Reports in Supabase

```sql
SELECT week_start_date, topic_label, source_article_count, cumulative_score
FROM hot_topic_reports
ORDER BY week_start_date DESC, cumulative_score DESC;
```

---

## Checking Buffered Traffic Articles

```sql
SELECT major_category, COUNT(*) as count, AVG(initial_quality_score) as avg_score
FROM articles
WHERE content_type = 'traffic'
  AND hot_topic_analyzed = FALSE
  AND buffer_expires_at > NOW()
GROUP BY major_category
ORDER BY count DESC;
```
