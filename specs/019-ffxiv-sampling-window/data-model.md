# Data Model: 019

沒有資料表或 artifact 的形狀變更。變的是兩份設定與一行 log。

## `SOURCES_FFXIV_YML`（＋鏡像 `config/sources_ffxiv.example.yml`）

| 動作 | 項目 | 欄位 |
|---|---|---|
| 刪除 | `Reddit r/ffxiv`（`rss`，`new/.rss`，權重 20） | — |
| 刪除 | `FFXIV JP Forum`（`html_forum`，`512-Japanese-Forums`，權重 10） | — |
| 新增 ×5 | 英文對應的 PLL、TANK、DPS、HEALER、戰鬥系統（`vb_forum`） | `url`：`external.php?type=RSS2&forumids=<id>&lastpost=1`（id 待 research R3）；`weight`：PLL 100、其他 80；`content_type: "ffxiv"`；其他欄位（`max_pages`、`max_replies`、`max_chars`）沿用日文版的值 |
| 視 R4 新增 | 英文版的時區欄位（只有英文版頁面不是日本時間時才加；缺欄位＝日本時間，日文版不用改） | — |

名稱照日文版的寫法：`FFXIV EN Forum - <版名>`（log 的逐來源篇數各自一列）。

## `PIPELINE_CONFIG_YML`（＋鏡像 `config/pipeline_config.example.yml`）

- 新增 FFXIV 分析篇數上限的鍵 `ffxiv.max_selected`（定義在 `contracts/config-and-logs.md`）。缺鍵時是 20，行為跟現在一樣。值由 Luke 依 research R5／R6 核定。

## log

- 既有：`FFXIV 候選池 N 篇：…`、`FFXIV 入選 N 篇：…`（015 FR-010），英文各版各自出現。
- 新增：上限截掉論壇串時，一行寫出被擠掉的論壇串數（格式見 `contracts/config-and-logs.md`）。
