# Quickstart: 018 週報發布前審核

本機 `python` 不在 PATH，一律用 `.venv/bin/python`。本機 `.env` 與 prod 是同一把 Gemini key：重播會計費，吃同一個 NT$300 月上限。

## 重播一份已發布的報告（不寫資料庫）

```bash
.venv/bin/python scripts/replay_report_review.py --week 2026-11-02 --topic "道安政策 · 彙整" \
    --out /tmp/claude-1000/<scratch>/replay
```

看 `<out>/2026-11-02-*.md` 的修前修後並排；`*.json` 有每條發現與套用結果。

## 量 SC-001（指令造成的錯型）

```bash
for w in 2026-10-19 2026-10-26 2026-11-02; do
  .venv/bin/python scripts/replay_report_review.py --week "$w" --topic "道安政策 · 彙整" --regenerate --out <out>
done
```

JSON 的 `checks.original` 是已發布原稿的四類計數（要 > 0，證明檢查會咬），`checks.regenerated` 是新指令重生成的（要全部 0）。

## 量 SC-002（留一測試）

對每個錨點 id：排除它、重播它所在的那份報告，看發現裡有沒有點出那一句。

```bash
.venv/bin/python scripts/replay_report_review.py --week 2026-10-26 --topic "道安政策 · 彙整" \
    --exclude-anchor drug-driving-7-deaths --out <out>
```

## 本機整合測試（寫入新表）

```bash
npx supabase start            # garyu 專屬 stack：API 54331／DB 54332
bash scripts/setup_test_db.sh # 會套到 006
.venv/bin/python -m pytest tests/integration/test_report_review_storage.py -q
```

`tests/integration/conftest.py` 會擋非本機主機。

## 上線

1. Supabase dashboard 貼上 `supabase_migrations/006_report_reviews.sql`，讀回表與 grant。
2. `gh variable set GEMINI_REVIEW_MODEL_NAME --env production --body gemini-4-argon`，再 `gh variable get` 讀回。
3. `weekly.yml` 的「週交通熱點分析」step 的 env 加上 `GEMINI_REVIEW_MODEL_NAME`。
4. 手動 dispatch `weekly.yml` 一次，或等週一排程；log 搜 `[審稿]`，每份報告一行，最後一行是合計。
