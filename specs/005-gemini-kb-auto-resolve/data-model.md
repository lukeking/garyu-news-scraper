# Data Model: Gemini-Powered Self-Evolving Knowledge Base

**Branch**: `005-gemini-kb-auto-resolve` | **Date**: 2026-05-11

---

## New Entity: `knowledge_base` (Supabase table)

Replaces `knowledge-base.md` as the authoritative source for FFXIV term translations.

### Schema

```sql
CREATE TABLE knowledge_base (
  id              SERIAL PRIMARY KEY,
  jp_term         TEXT NOT NULL,
  tw_term         TEXT NOT NULL,
  en_term         TEXT NOT NULL DEFAULT '',
  category        TEXT NOT NULL DEFAULT '',
  notes           TEXT NOT NULL DEFAULT '',
  auto_generated  BOOLEAN NOT NULL DEFAULT false,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT knowledge_base_jp_term_key UNIQUE (jp_term)
);
```

### Column Definitions

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `id` | SERIAL | system | Auto-incrementing primary key |
| `jp_term` | TEXT | ✓ | Lookup key — exact form from source (kanji, katakana, EN abbreviation, or EN full name). Must be unique. |
| `tw_term` | TEXT | ✓ | Official TW localization or dominant TW community colloquial term |
| `en_term` | TEXT | ✓ (empty ok) | English name (official EN localization) |
| `category` | TEXT | ✓ (empty ok) | One of the valid category values listed below |
| `notes` | TEXT | ✓ (empty ok) | Optional context: version, source, alternative names, usage notes |
| `auto_generated` | BOOLEAN | ✓ | `true` if written by `auto_kb.py`; `false` if manually added or migrated from `knowledge-base.md` |
| `created_at` | TIMESTAMPTZ | system | Row creation timestamp (UTC) |
| `updated_at` | TIMESTAMPTZ | system | Last modification timestamp (UTC) |

### Valid `category` Values

Matches the existing `knowledge-base.md` categories (no changes):

`遊戲`、`資料片`、`資料片縮寫`、`副本`、`副本縮寫`、`職能`、`職業`、`技能`、`道具`、`貨幣`、`地區`、`系統`、`機制`

### Indexes

```sql
-- UNIQUE constraint already creates an index on jp_term (primary lookup path)
-- No additional indexes needed at current scale
```

### RLS Policy

The `knowledge_base` table is read by the weekly pipeline using `SUPABASE_SERVICE_ROLE_KEY`, which bypasses RLS. The same key is used for writes by `auto_kb.py`. No RLS policies are required for this table — consistent with the existing `articles` table pattern.

### Supabase Trigger (optional, for `updated_at`)

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_knowledge_base_updated_at
  BEFORE UPDATE ON knowledge_base
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

---

## Existing Entity: `articles` (unchanged schema, new query pattern)

The `articles` table schema is unchanged. Two new query patterns are introduced:

### Pattern A — Auto-KB job miss collection

```sql
SELECT id, analysis
FROM articles
WHERE content_type = 'ffxiv'
  AND analysis::text LIKE '%[[%'
```

Returns all FFXIV articles whose `analysis` JSONB contains at least one `[[term]]` marker. Identical to the query in the retired `scripts/resolve_kb_misses.py`.

### Pattern B — Auto-KB job re-resolution

```sql
UPDATE articles
SET analysis = <patched_analysis_jsonb>
WHERE id = <article_id>
```

One UPDATE per article where at least one `[[term]]` was replaced with a newly-added KB term. Idempotent: re-running after a successful run produces no-op UPDATEs.

---

## Migration

All existing rows from `knowledge-base.md` are migrated to the `knowledge_base` table via `scripts/migrate_kb.py` with `auto_generated = false`.

### Migration row count (approximate)

Current `knowledge-base.md` contains ~60 term rows across 8 sections. All rows will be migrated with their existing `jp_term`, `tw_term`, `en_term`, `category`, and `notes` values.

### Migration idempotency

`scripts/migrate_kb.py` uses upsert (INSERT … ON CONFLICT DO NOTHING) so it can be run safely multiple times without creating duplicates.

---

## Retired Entities

| Artifact | Was | Now |
|----------|-----|-----|
| `knowledge-base.md` | Markdown file; source of truth for KB | Deleted; replaced by `knowledge_base` Supabase table |
| `config/knowledge-base-template.md` | Format reference for manual KB entry | Deleted; schema documented in this file |
