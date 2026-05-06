# Contract: KB Miss Re-Resolution Job

**Feature**: P6 — KB Miss Re-Resolution Job
**Files**: `scripts/resolve_kb_misses.py`, `.github/workflows/resolve-kb-misses.yml`

---

## GitHub Actions Workflow Contract

**File**: `.github/workflows/resolve-kb-misses.yml`

**Trigger**:
```yaml
on:
  push:
    branches: [main]
    paths: ['knowledge-base.md']
```

**Job steps**:
1. `actions/checkout@v4`
2. `pip install supabase`
3. `python scripts/resolve_kb_misses.py`

**Environment variables** (from existing GitHub Secrets — no new secrets):
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

**Guarantee**: Job MUST NOT trigger on pushes that do not touch `knowledge-base.md`. Job MUST complete within 10 minutes (Constitution Principle IV).

---

## Script Interface: `resolve_kb_misses.py`

**Location**: `scripts/resolve_kb_misses.py`

### Inputs

| Source | Value |
|--------|-------|
| `knowledge-base.md` | Read from repo root at runtime |
| `SUPABASE_URL` | Environment variable |
| `SUPABASE_SERVICE_ROLE_KEY` | Environment variable |

### Outputs

| Output | Description |
|--------|-------------|
| Supabase UPDATE | One UPDATE per article that had at least one resolvable `[[term]]` |
| KB MISS warning | One WARNING log line per still-unresolvable `[[term]]` (same format as main pipeline) |
| Exit 0 | Always — partial resolution is not a failure condition |

---

## Functional Contract

### Step 1 — Load KB mapping

Parse `knowledge-base.md` into `dict[str, str]` (JP Term → TW Term):

```python
def load_kb(kb_path: Path) -> dict[str, str]:
    mapping = {}
    for line in kb_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or "|---" in line:
            continue
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= 2 and cells[0] != "JP Term":
            mapping[cells[0]] = cells[1]
    return mapping
```

### Step 2 — Query Supabase

```sql
SELECT id, analysis
FROM articles
WHERE content_type = 'ffxiv'
  AND analysis::text LIKE '%[[%'
```

Returns all FFXIV articles whose `analysis` JSONB contains at least one `[[term]]` marker.

On Supabase failure: log `ERROR`, exit 0 (no crash).

### Step 3 — Resolve per article

For each article row:

1. Serialize: `text = json.dumps(analysis)`
2. Find all markers: `terms = re.findall(r'\[\[([^\]]+)\]\]', text)`
3. For each unique term:
   - If `term in kb_mapping`: replace all occurrences of `[[term]]` with `kb_mapping[term]` in `text`
   - Else: collect for KB MISS warning (do NOT modify)
4. If any replacements were made:
   - `updated_analysis = json.loads(text)`
   - UPDATE Supabase: `articles.analysis = updated_analysis WHERE id = article.id`
5. Emit one KB MISS warning block for all unresolvable terms in this run (same format as main pipeline)

### KB MISS Warning Format

```
[WARNING] ========== ⚠️  KB MISS 術語待審查 ==========
[WARNING] 以下術語出現在 FFXIV 分析結果中但未收錄於 knowledge-base.md：
[WARNING]   • {term_1}
[WARNING]   • {term_2}
[WARNING] 請更新 knowledge-base.md 後提交 PR，避免下次執行再次出現 [[term]] 標記。
[WARNING] ==============================================
```

Emitted once per script run, aggregating all unresolvable terms across all processed articles.

---

## Guarantees

- **Idempotent**: Running the script twice produces identical Supabase state. Resolved text contains no `[[`, so the query returns no rows on a second run.
- **Partial resolution**: An article with both resolvable and unresolvable markers is partially updated. The resolved markers are replaced; unresolvable markers remain. The article stays in the Supabase query result pool for the next KB update cycle.
- **No AI calls**: All resolution is done via KB string lookup.
- **No HTTP requests**: Script only communicates with Supabase.
- **No CF Pages redeploy**: Worker API serves `articles.analysis` dynamically; Supabase UPDATE is immediately visible to readers.
- **No pipeline interference**: Script runs in an independent GH Actions job; it does not interact with the weekly pipeline workflow.
