# Contract: Auto-KB Job

**Feature**: Gemini-Powered Self-Evolving Knowledge Base  
**Files**: `scripts/auto_kb.py`, `.github/workflows/auto-kb.yml`

---

## GitHub Actions Workflow Contract

**File**: `.github/workflows/auto-kb.yml`

**Trigger**:
```yaml
on:
  workflow_run:
    workflows: ["Garyu News Scraper 週報"]
    types: [completed]
```

**Job guard**:
```yaml
if: github.event.workflow_run.conclusion == 'success'
```

**Job steps**:
1. `actions/checkout@v5`
2. `actions/setup-python@v5` with Python 3.11, pip cache
3. `pip install -r requirements.txt`
4. `python scripts/auto_kb.py`

**Environment variables** (all from existing GitHub Secrets/Variables — no new secrets):

| Variable | Source |
|----------|--------|
| `SUPABASE_URL` | `secrets.SUPABASE_URL` |
| `SUPABASE_SERVICE_ROLE_KEY` | `secrets.SUPABASE_SERVICE_ROLE_KEY` |
| `GEMINI_API_KEY` | `secrets.GEMINI_API_KEY` |
| `GEMINI_MODEL_NAME` | `vars.GEMINI_MODEL_NAME \|\| secrets.GEMINI_MODEL_NAME` |

**Guarantee**: Job MUST exit 0 in all cases (failures logged, non-blocking). Job MUST complete within 10 minutes.

---

## Script Contract: `scripts/auto_kb.py`

### Inputs

| Source | Value |
|--------|-------|
| Supabase `knowledge_base` table | All existing `jp_term` values (for deduplication) |
| Supabase `articles` table | FFXIV articles whose `analysis::text LIKE '%[[%'` |
| `SUPABASE_URL` | Environment variable |
| `SUPABASE_SERVICE_ROLE_KEY` | Environment variable |
| `GEMINI_API_KEY` | Environment variable |
| `GEMINI_MODEL_NAME` | Environment variable (falls back to `gemini-2.5-flash`) |

### Outputs

| Output | Description |
|--------|-------------|
| Supabase INSERT | One row per confidently-resolved term in `knowledge_base` table |
| Supabase UPDATE | One UPDATE per article where at least one `[[term]]` was replaced |
| `[KB AUTO-MISS]` log | One WARNING per still-unresolvable term after Gemini call |
| Exit 0 | Always — partial resolution is not a failure condition |

---

## Functional Contract

### Step 1 — Load existing KB terms

```python
result = supabase.table('knowledge_base').select('jp_term').execute()
existing_terms: set[str] = {row['jp_term'] for row in result.data}
```

On failure: log ERROR, exit 0.

### Step 2 — Collect unknown terms from Supabase articles

```python
# Query
SELECT id, analysis FROM articles
WHERE content_type = 'ffxiv'
  AND analysis::text LIKE '%[[%'

# Extract markers
MARKER_RE = re.compile(r'\[\[([^\]]+)\]\]')
unknown_terms: set[str] = set()
for row in rows:
    text = json.dumps(row['analysis'])
    for m in MARKER_RE.finditer(text):
        term = m.group(1).strip()
        if term not in existing_terms:
            unknown_terms.add(term)
```

If `unknown_terms` is empty: log "no unknown terms to resolve", exit 0.

### Step 3 — Call Gemini (batch)

**System prompt**:
```
你是 FFXIV 術語翻譯專家，專精繁體中文（台灣）玩家社群用語。
```

**User prompt template**:
```
以下是尚未收錄於知識庫的 FFXIV 術語，請為每個術語提供繁體中文（台灣）翻譯。

規則：
1. 只回傳你有高把握的術語（來源：官方 TW 補丁說明 > TW 維基/社群慣用）
2. 對沒把握或資訊不足的術語，直接省略，不要猜測
3. 回傳嚴格 JSON 陣列格式，每個元素包含：jp_term, tw_term, en_term, category, notes
4. category 必須是以下之一：遊戲、資料片、資料片縮寫、副本、副本縮寫、職能、職業、技能、道具、貨幣、地區、系統、機制
5. 若無任何把握的術語，回傳空陣列 []

待翻譯術語（每行一個）：
{terms_list}

回傳格式範例：
[
  {{"jp_term": "暁月のフィナーレ", "tw_term": "曉月", "en_term": "Endwalker", "category": "資料片", "notes": "6.0（2021）"}}
]
```

**Gemini call parameters**:
- Temperature: 0.1
- Max output tokens: 4096
- Retries: up to 3 (network errors only; 4xx are not retried)

On Gemini failure or unparseable JSON: log ERROR, skip insertion, proceed to Step 5 with empty resolved set.

### Step 4 — Write confident resolutions to Supabase

For each entry in Gemini's JSON response:
1. Validate required fields: `jp_term` and `tw_term` must be non-empty strings
2. Skip if `jp_term` already exists in `existing_terms` (race condition guard)
3. INSERT to `knowledge_base` with `auto_generated = True`
4. Add `jp_term` to `newly_added_terms` set

On INSERT failure for a specific term: log WARNING, skip that term, continue.

### Step 5 — Inline re-resolution

For each article row from Step 2:
1. `text = json.dumps(row['analysis'])`
2. Find all `[[term]]` markers in text
3. For each marker where `term` is in `newly_added_terms`:
   - Look up `tw_term` from the just-inserted rows
   - Replace `[[term]]` with `tw_term` in text
4. If any replacements were made:
   - `patched = json.loads(text)`
   - UPDATE `articles SET analysis = patched WHERE id = row['id']`
5. Emit `[KB AUTO-MISS]` for all terms in this article that are still in `[[]]` format

### KB AUTO-MISS Warning Format

```
[WARNING] ========== ⚠️  KB AUTO-MISS 術語待審查 ==========
[WARNING] 以下術語在本次 Gemini 解析中無法確認翻譯：
[WARNING]   • {term_1}
[WARNING]   • {term_2}
[WARNING] 術語已顯示於 FFXIV 頁面術語池，等待知識庫收錄。
[WARNING] ==============================================
```

Emitted once per script run, aggregating all unresolvable terms across all articles.

---

## Guarantees

- **Idempotent**: Running the script twice in the same week produces identical Supabase state. Resolved terms have no `[[` remaining, so Step 2 returns fewer rows on subsequent runs.
- **Non-blocking**: Script always exits 0; failures are logged but never propagate as pipeline failures.
- **No guesses**: Only Gemini-confident terms are written to the KB. The `[KB AUTO-MISS]` path is not a fallback — it is the intended path for terms Gemini cannot resolve.
- **Frequency**: Runs at most once per week (triggered by weekly pipeline success).
- **Retired workflows**: Replaces `scripts/resolve_kb_misses.py` and `.github/workflows/resolve-kb-misses.yml` entirely.
