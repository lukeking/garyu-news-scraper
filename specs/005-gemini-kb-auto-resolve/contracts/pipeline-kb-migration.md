# Contract: Pipeline KB Migration

**Feature**: Gemini-Powered Self-Evolving Knowledge Base  
**Files**: `src/analyzer.py` (modified), `scripts/migrate_kb.py` (new)

---

## `src/analyzer.py` — `load_knowledge_base()` Rewrite

### Before (file-based)

```python
def load_knowledge_base(path: str = "knowledge-base.md") -> dict:
    global _KB_CACHE
    if _KB_CACHE is not None:
        return _KB_CACHE
    # ... reads file, parses markdown table ...
    _KB_CACHE = kb
    return kb
```

### After (Supabase-based)

**Signature**: `load_knowledge_base() -> dict`  
Parameter `path` is removed; no callers pass it.

**Behaviour**:
1. Return `_KB_CACHE` immediately if already populated (identical caching behaviour)
2. Create Supabase client inline:
   ```python
   url = (os.environ.get("SUPABASE_URL") or "").strip()
   key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()
   if not url or not key:
       raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 未設定")
   from supabase import create_client
   client = create_client(url, key)
   ```
3. Fetch all rows:
   ```python
   result = client.table('knowledge_base').select('jp_term, tw_term, en_term, category').execute()
   ```
4. Build `kb` dict identical to current return format:
   ```python
   kb = {
       row['jp_term']: {
           'tw': row['tw_term'],
           'en': row['en_term'],
           'category': row['category'],
       }
       for row in result.data
   }
   ```
5. If `kb` is empty: raise `RuntimeError("knowledge_base 表格中沒有有效的術語資料。...")`
6. Log: `"知識庫載入完成：%d 個術語"` (identical to current log line)
7. Set `_KB_CACHE = kb` and return

**Callers unchanged**: `analyze_article()` calls `load_knowledge_base()` without arguments — no call-site changes needed.

**FFXIV_ANALYSIS_TEMPLATE unchanged**: The `{knowledge_base}` block injected into the Gemini prompt is built from the same dict structure:
```python
kb_lines = [
    f"| {jp} | {v['tw']} | {v['en']} | {v['category']} |"
    for jp, v in kb.items()
]
```

### Failure behaviour

| Failure | Behaviour |
|---------|-----------|
| `SUPABASE_URL` or key missing | `RuntimeError` raised — pipeline halts with clear error |
| Supabase network error | Exception propagates — pipeline halts |
| Table returns 0 rows | `RuntimeError` raised — pipeline halts (empty KB is a configuration error) |

---

## `scripts/migrate_kb.py` — One-Time Migration Script

### Purpose

Reads `knowledge-base.md`, parses all term rows, and upserts them into the Supabase `knowledge_base` table. Run once before deploying the pipeline migration.

### Inputs

| Source | Value |
|--------|-------|
| `knowledge-base.md` | Read from repo root |
| `SUPABASE_URL` | Environment variable |
| `SUPABASE_SERVICE_ROLE_KEY` | Environment variable |

### Behaviour

1. Parse `knowledge-base.md` using the same logic as the current `load_knowledge_base()` — 5-column pipe table, skips header and separator rows
2. Build list of dicts with `jp_term`, `tw_term`, `en_term`, `category`, `notes`, `auto_generated = False`
3. Upsert with `on_conflict='jp_term'` (safe to re-run)
4. Log count of rows upserted
5. Exit 0 on success, exit 1 on fatal error

### Idempotency

Running `migrate_kb.py` multiple times produces identical Supabase state. Upsert with `on_conflict = 'jp_term'` skips duplicates rather than overwriting them — preserving any manual edits made to rows after the initial migration.

### Post-migration

After confirming migration success (log shows expected row count):
1. Delete `knowledge-base.md` from the repository
2. Delete `config/knowledge-base-template.md` from the repository
3. Delete `scripts/resolve_kb_misses.py`
4. Delete `.github/workflows/resolve-kb-misses.yml`

These deletions are tracked as separate tasks.
