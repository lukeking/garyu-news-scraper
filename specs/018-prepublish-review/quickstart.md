# Quickstart: 018 週報發布前審核

本機 `python` 不在 PATH，一律用 `.venv/bin/python`。本機 `.env` 與 prod 是同一把 Gemini key：重播會計費，吃同一個 NT$300 月上限。

## 重播一份已發布的報告（不寫資料庫）

```bash
.venv/bin/python scripts/replay_report_review.py --week 2026-11-02 --topic "道安政策 · 彙整" \
    --out /tmp/claude-1000/<scratch>/replay
```

看 `<out>/2026-11-02-*.md` 的檢查結果；`*.json` 有重建的輸入、原稿（加 `--regenerate` 時還有重生成）與各自的 `check_report()` 計數。

## 量 SC-001（指令造成的錯型）

```bash
for w in 2026-10-19 2026-10-26 2026-11-02; do
  .venv/bin/python scripts/replay_report_review.py --week "$w" --topic "道安政策 · 彙整" --regenerate --out <out>
done
```

JSON 的 `checks.original` 是已發布原稿的四類計數（要 > 0，證明檢查會咬），`checks.regenerated` 是新指令重生成的（要全部 0）。

審稿、留一測試、審核紀錄與上線步驟隨 US2、US3 在 2026-11-08 拿掉，原文在 `06985f5`。
