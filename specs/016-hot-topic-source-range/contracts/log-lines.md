# Contract: 週報 log 的「焦點事件帶發布時間」那一行（FR-010）

**讀者**：週驗收 routine（`routines/weekly-verify/`）。它跑在雲端，打不到 Worker API 與 Supabase（`PROMPT.md` 的環境段落），
只讀得到 Actions log，所以 SC-003 只能靠這一行判定。有讀者的 log 是契約，格式用測試鎖住。

**位置**：`src/storage.py` 的 `upsert_hot_topic_report`，upsert 成功、印出既有的 `✓ hot_topic_report upserted: …` 之後。
一般報告與彙整報告都經過這裡，一個位置涵蓋兩條路。既有那一行不改（routine 的 PROMPT 與 FOCUS 都在讀它）。

**格式**（每份報告一行，INFO）：

```text
✓ hot_topic_report 焦點事件帶發布時間：<n>/<m>（<week_start_date> / <topic_label>）
```

- `m`：`source_article_links` 的項數；`n`：其中是 dict 且帶非空 `published` 的項數（純字串項目算沒帶）。
- `m` 為 0 時照樣印（`0/0`），不省略——沒印＝沒跑，不是「沒東西」。
- upsert 失敗時不印這一行（既有的 `✗ hot_topic_report upsert 失敗` 已經出聲）。

**判讀**：上線後每份新報告應為 `m/m`；`n < m` 標待查交給本地（多半是來源本身沒有發布時間）。
