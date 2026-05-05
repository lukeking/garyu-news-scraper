# Contract: Pipeline Freshness Filter

**Feature**: P1 — Pipeline Freshness Filter
**Module**: `src/filter.py` (logic) + `src/storage.py` (data access)

## Interface: `freshness_filter(articles, existing_fingerprints, threshold_days=30)`

**Location**: `src/filter.py`

### Input

| Parameter | Type | Description |
|-----------|------|-------------|
| `articles` | `list[dict]` | Raw articles from `collect_all()`, each with at minimum `title`, `link`, `published`, and `source` keys |
| `existing_fingerprints` | `set[str]` | Set of 64-char hex sha256 strings from `storage.get_existing_title_fingerprints()`; may be empty if Supabase query failed |
| `threshold_days` | `int` | Age cutoff in days; default 30 |

### Output

`list[dict]` — filtered subset of input articles, in the same order, with no modifications to article dict contents.

### Behavior

For each article in `articles`:

1. Compute `fp = title_fingerprint(article)` (sha256 of normalized title)
2. If `fp in existing_fingerprints`: **exclude** with log `INFO "跨週去重跳過：{title[:50]} (fingerprint match)"`
3. Else, determine source type:
   - If `"news.google.com" in article["link"]`: apply URL-date age check
     - Extract date from URL via regex; if date found and age > threshold_days: **exclude** with log `INFO "過時文章跳過：{title[:50]} (URL date: {date}, age: {age}d)"`
     - If no extractable date: **include** (known limitation)
   - Else (direct RSS source): apply `<pubDate>` age check
     - If `article["published"]` parseable and age > threshold_days: **exclude** with log `INFO "過時文章跳過：{title[:50]} (pubDate: {date}, age: {age}d)"`
     - If `article["published"]` empty or unparseable: **include**
4. Articles that pass both checks are returned.

### Guarantees

- Never raises; failures in date parsing → article included.
- Order of returned articles matches input order.
- No HTTP requests made.
- Both `existing_fingerprints=set()` (Supabase failure) and `threshold_days=30` produce valid output.

---

## Interface: `title_fingerprint(article)` → `str`

**Location**: `src/filter.py`

### Input

| Parameter | Type | Description |
|-----------|------|-------------|
| `article` | `dict` | Article dict with a `title` key |

### Output

64-character hex string (sha256).

### Algorithm

```python
import hashlib, re

def _normalize_title_for_fingerprint(title: str) -> str:
    return re.sub(r'[^\w一-鿿぀-ヿ]', '', title.lower().strip())

def title_fingerprint(article: dict) -> str:
    normalized = _normalize_title_for_fingerprint(article.get("title", ""))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
```

---

## Interface: `get_existing_title_fingerprints()` → `set[str]`

**Location**: `src/storage.py`

### Input

None (reads from Supabase using the initialized client).

### Output

`set[str]` — all non-null `content_fingerprint` values currently in the `articles` table.
Returns empty `set()` if Supabase is not configured or query fails.

### Behavior

- Single SELECT call: `SELECT content_fingerprint FROM articles WHERE content_fingerprint IS NOT NULL`
- On failure: logs `WARNING "跨週指紋查詢失敗：{error}"`, returns `set()`
- If `is_configured()` returns False: returns `set()` silently

---

## Pipeline Integration Contract

The pipeline category `filter()` method MUST orchestrate in this order:

```text
1. get_existing_title_fingerprints()   ← storage.py (may return empty set on failure)
2. freshness_filter(raw, fingerprints) ← filter.py  (cross-week dedup + age gate)
3. filter_and_deduplicate(after_fresh) ← filter.py  (within-run keyword + hash dedup)
4. [:max_articles]                     ← category cap
```

This sequence satisfies Constitution Principle III (dedup in filter.py) and Principle I (stage ordering).
