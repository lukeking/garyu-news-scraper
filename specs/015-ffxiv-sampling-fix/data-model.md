# Data Model: FFXIV 週報取樣修正

不改資料庫 schema。以下是設定、記憶體中的文章 dict，以及它們之間的規則。

## 來源設定（`sources_ffxiv.yml` 的一筆）

| 欄位 | 型別 | 適用 | 規則 |
|---|---|---|---|
| `weight` | 整數 | 所有 FFXIV 來源 | 越大越先入選。沒寫＝0，每次收集印一行警告。初值見 research R4 |
| `type: vb_forum` | — | 論壇五個版 | 新型別，見下 |
| `max_pages` | 整數 | `vb_forum` | 每串最多往前翻幾頁（初值 3） |
| `max_replies` | 整數 | `vb_forum` | 每串最多收幾則，新的優先（初值 20） |
| `max_chars` | 整數 | `vb_forum`、`html_patch` | 合併後內容的字數上限（論壇 6,000、Lodestone 2,000） |
| `date_pattern` | regex | `html_patch` | 在每個項目的 HTML 裡找發布時間（UTC epoch 秒，第一個捕捉群組）。有寫就只收 `CUTOFF` 之後的 |
| `exclude_title_prefixes` | 字串清單 | `html_patch` | 標題以這些開頭的不收 |
| `detail_selector` | CSS selector | `html_patch` | 有寫就對每個收進的項目抓詳細頁，取這個節點的文字當 `summary` |

完整範例與向下相容規則見 [contracts/sources-ffxiv-config.md](./contracts/sources-ffxiv-config.md)。

## 論壇項目（`vb_forum` 產出的一篇文章）

一串在一個週窗口內的回覆合成一篇。

| 欄位 | 來源 | 規則 |
|---|---|---|
| `title` | RSS 的串標題 | 不加日期 |
| `link` | `<串網址>?p=<窗口內最新回覆 id>` | 每週不同；同一週重跑相同（upsert 覆寫同一列） |
| `dedup_key` | `forum:<串 id>:<最新回覆 id>` | `freshness_filter` 見到它就略過標題指紋 |
| `published` | 窗口內最新回覆的時間（UTC ISO） | 排序用 |
| `summary` | 收進的回覆，依時間由舊到新，每則前面標時間 | 截到 `max_chars`；超過 `max_replies` 時丟最舊的 |
| `source`、`content_type`、`source_weight` | 來源設定 | 同其他來源 |

**窗口**：［本次執行所在 ISO 週的週一 00:00 UTC − 7 天, 該週一 00:00 UTC）（research R1）。

**選串**：RSS 每一筆的 `pubDate`（最後回覆時間）≥ 窗口起點才處理。

**收回覆**：從 RSS `link`（`goto=newpost`）轉到的那頁開始，解析 `li[id^=post_]`；頁上最早一則仍 ≥ 窗口起點、
且還沒到 `max_pages`，就往前一頁（`<串網址>/page<N-1>`）。只收時間落在窗口內的回覆。

**回覆時間**：`span.date` 的文字，日本時間。`MM-DD-YYYY hh:mm AM/PM`；`Today`／`Yesterday` 以抓取當下的日本日期為準。

**退回**（每一種原因各自一句 log，見 contracts/log-lines.md）：

| 情況 | 結果 |
|---|---|
| 討論串頁面請求失敗 | 用 RSS 的最後一則（`content:encoded`）當唯一一則，若它在窗口內 |
| 頁面解析不到任何回覆 | 同上 |
| 回覆時間解析不出來 | 同上 |
| 窗口內 0 則（例：最後回覆在窗口終點之後，窗口內沒有其他回覆） | 這串不產出項目（不是退回，是沒內容） |
| 翻到 `max_pages` 仍未到窗口起點 | 照收，印「可能還有更早的回覆沒收」 |

**截斷**：一個版 RSS 回滿 15 筆、而且第 15 筆的最後回覆仍 ≥ 窗口起點，印截斷警告。

## 文章 dict 的新欄位（記憶體中，不進資料庫）

| 欄位 | 誰寫 | 誰讀 |
|---|---|---|
| `source_weight` | `collect_sources`（從來源設定的 `weight` 蓋上） | FFXIV 排序鍵 |
| `dedup_key` | `vb_forum` | `freshness_filter` |

## FFXIV 排序鍵

`(source_weight 降冪, published 降冪, 沒有 published 的排最後)`。`FFXIVCategory.filter()` 在 `freshness_filter` 之後、
`filter_and_deduplicate` 之前排一次；`game_deduplicate` 的 Jaccard 迴圈因此保留權重高的那份，最後依同一個鍵取前 20。
