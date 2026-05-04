# FFXIV Knowledge Base — Entry Format Reference

`knowledge-base.md` is parsed by `src/analyzer.py:load_knowledge_base()` as a **5-column pipe table**.
Every entry must follow this exact format:

```markdown
| JP Term | TW Term | EN Term | Category | Notes |
|---------|---------|---------|----------|-------|
| [lookup key] | [TW official/colloquial] | [EN term] | [Category] | [optional context] |
```

## Column Rules

| Column | Description |
|--------|-------------|
| **JP Term** | The lookup key — exact form from the source (kanji, katakana, EN abbreviation, or EN full name). Must be unique within the file. |
| **TW Term** | Official TW localization or dominant TW community colloquial term |
| **EN Term** | English name (use official EN localization) |
| **Category** | One of the valid values below |
| **Notes** | Optional — version, source, alternative names, or usage notes |

## Valid Category Values

`遊戲`、`資料片`、`資料片縮寫`、`副本`、`副本縮寫`、`職能`、`職業`、`技能`、`道具`、`貨幣`、`地區`、`系統`、`機制`

## Adding Entries

- Add under the appropriate `## Section` heading in `knowledge-base.md`
- One row per lookup key form — if a term has a full name AND an abbreviation, add both rows
- Use the `ffxiv-term-translator` subagent to resolve unknown terms; it produces ready-to-paste rows

## Exclusion Filter (analyzer behavior)

The analyzer skips terms it cannot find in the KB and logs `[KB MISS]`. Use those logs as your input queue for new KB entries.

社交辭令 (e.g., お疲れ様です), non-technical player venting, and generic phrases do not need KB entries.
