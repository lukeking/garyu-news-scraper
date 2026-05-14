# Contract: Configuration Files

**Feature**: `006-traffic-news-pipeline` | **Date**: 2026-05-12

Three new configuration files follow the same pattern as `config/sources_traffic.yml`: committed example file, real content stored as GitHub Environment Variable, written to `config/` at workflow runtime.

---

## `config/categories_traffic.yml`

**GitHub Environment Variable**: `CATEGORIES_TRAFFIC_YML`
**Committed example**: `config/categories_traffic.example.yml`
**Loaded by**: `src/filter.py` at module import (`load_category_taxonomy()`)

**Schema** (YAML):

```yaml
categories:
  <category_label>:       # string — must be unique; used as major_category DB value
    keywords:             # list of strings — any match assigns this category
      - <keyword>
```

**Rules**:
- Category labels must be non-empty strings
- Keywords are matched case-insensitively against the normalised article title
- First matching category wins (priority = list order in YAML)
- Articles matching no category receive `major_category = 'uncategorised'`
- Minimum 1 category required; no maximum
- Adding a new category requires no code change — only `CATEGORIES_TRAFFIC_YML` update

**Validation at load time**: If file is empty or unparseable, `src/filter.py` raises `RuntimeError` and halts the pipeline (same pattern as KB integrity check in Principle VI).

---

## `config/pipeline_config.yml`

**GitHub Environment Variable**: `PIPELINE_CONFIG_YML`
**Committed example**: `config/pipeline_config.example.yml`
**Loaded by**: `src/filter.py` and `src/analyzer.py` at module import (`load_pipeline_config()`)

**Schema** (YAML):

```yaml
jaccard:
  merge_threshold: float      # 0.0–1.0; traffic dedup threshold (default 0.45)
  cluster_lower: float        # 0.0–1.0; cluster lower bound (default 0.20)
  game_threshold: float       # 0.0–1.0; game dedup threshold (default 0.50)

topic_scoring:
  min_threshold: float        # cumulative score minimum (default 1.5)
  max_hot_topics: integer     # 1–3 (default 3)

buffer:
  max_age_weeks: integer      # buffer expiry in weeks (default 8)

quality_score_weights:
  keyword_match_ratio: float  # sum of all three weights MUST equal 1.0
  normalised_word_count: float
  source_weight: float

source_weights:               # map of source name → float 0.0–1.0
  <source_name>: float        # sources not listed default to 0.5
```

**Validation at load time**: Weights must sum to 1.0 (±0.001). Thresholds must be in [0, 1]. If validation fails, pipeline halts with an actionable error message.

---

## `config/jieba_userdict.txt`

**GitHub Environment Variable**: `JIEBA_USERDICT_TXT`
**Committed example**: `config/jieba_userdict.example.txt`
**Loaded by**: `src/filter.py` at module import (`jieba.load_userdict(path)`)

**Format**: Standard jieba userdict plain text — one entry per line:
```
<word> <frequency> <pos_tag>
```

Where:
- `<word>`: the token to preserve as-is (e.g. `台一線`, `3死`)
- `<frequency>`: integer; higher = jieba prefers this segmentation (use 5–10 for road names, 10+ for numerical patterns)
- `<pos_tag>`: `n` for nouns (place names), `m` for numerals/quantities

**Validation**: If the file is missing or empty, `src/filter.py` logs a warning but does NOT halt — jieba runs without a custom dictionary (degraded quality, not pipeline failure).
