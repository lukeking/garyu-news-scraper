# Data Model: Separate CF Pages + Modular Pipeline

**Feature**: 002-cf-pages-modular-pipeline  
**Date**: 2026-05-04

---

## New Entities

### Category (Python Protocol)

A structural type contract that each pipeline category module implements.

| Field / Method | Type | Description |
|---|---|---|
| `name` | `str` | Human-readable category name (e.g., `"traffic"`, `"ffxiv"`) |
| `content_type` | `str` | Matches `article["content_type"]` value (e.g., `"traffic"`, `"ffxiv"`) |
| `max_articles` | `int` | Maximum articles to pass to analysis stage |
| `output_dir` | `str` | Relative path from repo root for static site output (e.g., `"pages"`, `"pages-ffxiv"`) |
| `site_url` | `str` | Public URL of the deployed site (used in RSS feed and HTML `<link>`) |
| `collect() -> list[Article]` | method | Returns raw articles for this category only |
| `filter(raw: list) -> list[Article]` | method | Deduplicates, applies keyword filters, caps at `max_articles` |
| `analyze(articles: list) -> list[Article]` | method | Adds `analysis` field to each article via AI |
| `publish(articles: list) -> str` | method | Writes static files to `output_dir`; returns `week_id` |

**Validation rules**:
- `content_type` must match the value used in `article["content_type"]`
- `max_articles` must be a positive integer
- `output_dir` must be a non-empty relative path

### OutputSite

Represents a deployed static site for one content type.

| Field | Type | Description |
|---|---|---|
| `output_dir` | `str` | Local directory path (relative to repo root) where static files are written |
| `site_url` | `str` | Public URL served by the CF Pages deployment |
| `cf_pages_project` | `str` | Cloudflare Pages project name (used in deploy workflow) |
| `deploy_workflow` | `str` | GitHub Actions workflow file name (e.g., `deploy-pages-ffxiv.yml`) |

**Known instances**:

| Site | `output_dir` | `cf_pages_project` | `deploy_workflow` |
|---|---|---|---|
| Traffic | `pages/traffic` | `traffic-issue-scraper` | `deploy-pages.yml` |
| FFXIV | `pages/ffxiv` | `garyu-ffxiv-news` | `deploy-pages-ffxiv.yml` |

---

## Modified Entities

### Article (unchanged schema)

No schema changes. The `content_type` field added in feature 001 is what routes each article to the correct category module and output site.

### publish() function signature (changed)

**Before**: `publish(articles: list) -> str`  
**After**: `publish(articles: list, output_dir: str = "pages/traffic", site_url: str | None = None) -> str`

- `output_dir`: target directory for all static file output (data/, week/, feed.xml)
- `site_url`: overrides the `SITE_URL` env var for RSS feed generation; defaults to env var if `None`

The function is backwards-compatible — all existing callers with no keyword arguments continue to work unchanged.

---

## State Transitions

### Pipeline Execution Flow (per Category)

```
RAW ARTICLES (collect)
       │
       ▼
FILTERED ARTICLES (filter + cap at max_articles)
       │
       ▼
ANALYZED ARTICLES (analyze — adds article["analysis"])
       │
       ├──► STATIC FILES → output_dir/data/, output_dir/week/, output_dir/feed.xml
       │
       └──► [returned to main.py for centralized Supabase write]
```

### Main Orchestrator Flow

```
For each Category in [TrafficCategory, FFXIVCategory]:
    articles = category.collect() → filter() → analyze() → publish()
    all_analyzed.extend(articles)

_save_to_supabase(all_analyzed, week_id)  # centralized, once
```

---

## No New Database Tables

This feature introduces no Supabase schema changes. The `content_type` column from feature 001 is sufficient.
