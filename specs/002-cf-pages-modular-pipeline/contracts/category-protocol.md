# Contract: Category Protocol

**Feature**: 002-cf-pages-modular-pipeline  
**Type**: Python structural typing contract (Protocol)  
**File**: `src/pipeline/base.py`

---

## Purpose

Every content category module in `src/pipeline/` must implement this interface.
The orchestrator in `main.py` iterates registered `Category` instances without knowing their concrete type.

---

## Protocol Definition

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Category(Protocol):
    name: str          # e.g., "traffic", "ffxiv"
    content_type: str  # matches article["content_type"]
    max_articles: int  # cap applied after filtering
    output_dir: str    # relative path from repo root
    site_url: str      # public URL for RSS/HTML

    def collect(self) -> list[dict]: ...
    def filter(self, raw: list[dict]) -> list[dict]: ...
    def analyze(self, articles: list[dict]) -> list[dict]: ...
    def publish(self, articles: list[dict]) -> str: ...
```

---

## Method Contracts

### `collect() -> list[dict]`

- Returns raw articles for this category only (already tagged with `content_type`)
- Returns `[]` if no sources configured or all sources unreachable
- Logs a warning per unreachable source; does not raise
- Never returns articles belonging to another category's `content_type`

### `filter(raw: list[dict]) -> list[dict]`

- Applies keyword/stale/dedup logic appropriate for this category
- Caps result at `self.max_articles`
- Returns `[]` if `raw` is empty; does not raise
- Returned articles retain all original fields from `raw`

### `analyze(articles: list[dict]) -> list[dict]`

- Adds `article["analysis"]` dict to each article
- Returns articles in the same order as input
- Raises `RuntimeError` only for unrecoverable errors (e.g., KB file missing for FFXIV)
- Skips individual articles that fail analysis rather than aborting the batch

### `publish(articles: list[dict]) -> str`

- Writes static files under `self.output_dir/`
- Creates `output_dir/` if it does not exist
- Returns `week_id` string (e.g., `"2026-W19"`)
- Is idempotent — re-running with the same articles overwrites output cleanly
- Does NOT write to Supabase (centralized in main.py)

---

## Registered Categories

Registered in `main.py` as a list:

```python
CATEGORIES = [
    TrafficCategory(),   # src/pipeline/traffic.py
    FFXIVCategory(),     # src/pipeline/ffxiv.py
]
```

---

## Failure Isolation

The orchestrator wraps each category in a try/except:
- A single category failure logs the error with `category.name` and continues to next category
- Both sites are attempted independently per FR-003

---

## Adding a New Category

1. Create `src/pipeline/<name>.py` implementing the `Category` protocol
2. Register it in `CATEGORIES` in `main.py`
3. Create a corresponding `deploy-pages-<name>.yml` workflow if it produces a static site

No other changes required.
