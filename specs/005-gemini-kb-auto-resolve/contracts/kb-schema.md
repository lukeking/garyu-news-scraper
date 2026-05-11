# Contract: knowledge_base Supabase Table

**Feature**: Gemini-Powered Self-Evolving Knowledge Base  
**Files**: Supabase SQL migration (run once in dashboard), `scripts/migrate_kb.py`

---

## Table Contract

**Table name**: `knowledge_base`  
**Access key**: `SUPABASE_SERVICE_ROLE_KEY` (same as `articles` table)  
**RLS**: Not required; service role key bypasses RLS

### Read interface (used by `src/analyzer.py`)

```python
supabase.table('knowledge_base') \
    .select('jp_term, tw_term, en_term, category') \
    .execute()
```

**Returns**: list of dicts with `jp_term`, `tw_term`, `en_term`, `category`  
**On empty result**: `load_knowledge_base()` raises `RuntimeError` (pipeline halts — not silent)  
**On Supabase error**: exception propagates; `load_knowledge_base()` does not catch it

### Write interface (used by `scripts/auto_kb.py`)

```python
supabase.table('knowledge_base').insert({
    'jp_term': str,
    'tw_term': str,
    'en_term': str,       # may be empty string
    'category': str,      # may be empty string
    'notes': str,         # may be empty string
    'auto_generated': True,
}).execute()
```

**Uniqueness**: `jp_term` has a UNIQUE constraint; inserting a duplicate raises a PostgreSQL error.  
**Duplicate handling**: `auto_kb.py` must deduplicate against existing `jp_term` values before inserting.

### Migration interface (used by `scripts/migrate_kb.py`)

```python
supabase.table('knowledge_base').upsert(
    rows,  # list of dicts
    on_conflict='jp_term'
).execute()
```

Sets `auto_generated = False` for all migrated rows.

---

## Guarantees

- `jp_term` is globally unique across all rows.
- `tw_term` is never empty (required field).
- `auto_generated = True` exclusively for rows written by `scripts/auto_kb.py`.
- `auto_generated = False` for all rows migrated from `knowledge-base.md` and for any future manual entries.
- The table is the sole authoritative source for FFXIV term translations; `knowledge-base.md` is deleted after migration.
