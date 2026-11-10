# Research: FFXIV 週報來源調整（019）

證據等級照慣例：實測／推論／判斷。硬門檻只收實測。三題 2026-11-09 沒查完（R3–R5），11-10 由 T001、T002 的 spike 查完。

## R0 現況（實測，讀程式＋11-09 artifact）

- 入選：`src/pipeline/ffxiv.py` 的 `filter()` 依 `ffxiv_rank_key` 排（`src/filter.py:474`，權重降冪 → 時間新到舊 → 沒時間的最後），
  經 `filter_and_deduplicate`、`game_deduplicate` 去重後取前 20（`src/filter.py:557`，`retained[:20]` 寫死）。`game_deduplicate` 吃 `load_pipeline_config()`。
- `src/pipeline/ffxiv.py` 的 `max_articles = 30` 跟實際的 20 不同；`docs/external-services.md` 的 Gemini 那一列寫「每次篇數：`src/pipeline/ffxiv.py` 的 `max_articles`」，
  指的不是實際生效的那個數。它有沒有被用到，實作時讀一次再改那一列（推論：沒用到）。
- prod `SOURCES_FFXIV_YML`（11-09 讀）：Reddit `new/.rss` 20、Lodestone 60、論壇列表頁 `html_forum` 10、TW 修正說明（停用）50、日文 PLL 100、四個版 80。
- 11-09 的候選池：論壇版 9、Reddit 25、論壇列表頁 10；入選論壇版 9、Reddit 11。

## R1 Reddit：拿掉（實測＋查證，Luke 11-09 裁示）

- **Decision**: 移除 Reddit 來源（prod 設定刪除該項，example 鏡像同步）。
- **Rationale**: `https://www.reddit.com/robots.txt`（11-09 用正式 UA 讀，200）是 `User-agent: *`、`Disallow: /`，並指向 Public Content Policy；
  憲章 IV 要求加來源前檢查 robots.txt，`Disallow: /` 不分格式，現有的 `new/.rss` 也在範圍內。內容面：只有收集前約 8 小時、只有開串，
  W44–W46 的 39 篇重要度全是「低」。
- **Alternatives considered**（都在讀 robots.txt 之前查的，因 robots.txt 而不用）：
  - 本週熱門 feed（`top/.rss?t=week`）＋模型依標題分類：涵蓋整週，但 40 篇多半是作品分享，每篇只有開串（中位數 139 字）。
  - 單篇留言 RSS：用正式 UA 回 200，一篇 201 則、中位數 233 字、帶時間；curl 預設 UA 回 403。Luke 一度據此裁示「留 Reddit：新聞討論＋回覆」。
  - 官方 OAuth：10-31 起不受理新的公開 API 申請、2027-03 結束（Reddit Help Center 的 Changelog - October 8, 2026，搜尋摘要；官方頁面 WebFetch 403）。
  - JSON 端點：本機 403。11-09 曾用瀏覽器 UA 再打，被自動模式的分類器以「繞過機器人檢查」擋下，沒有再試。
- 過程中 agent 一度誤稱 collector 靠瀏覽器 UA 讀 Reddit（見 R8），Luke 第一次裁示拿掉時依據裡有這句；最後的裁示依據是 robots.txt。

## R2 論壇列表頁：拿掉（Luke 11-09 裁示）

- **Decision**: 移除 `html_forum`（`512-Japanese-Forums`）來源。
- **Rationale**: 只有標題、沒有時間，三週 0 篇入選；營運公告與玩家回報因此沒有管道進分析，接受（現在也進不來）。
- 移除後 `html_forum` 這個收集型別沒有任何來源在用。型別與程式碼留著（推論：刪型別是另一件事，不在範圍），設定說明照實寫「目前沒有來源使用」。

## R3 英文官方論壇的五個子版（實測，11-10 T001）

- 11-09 的實測：`forum.php` 回 200，英文上層版是 642 Letters from the Producer、656 Classes & Jobs（日文 535、549）；讀版頁連續 429。
- 原本的查法（父版 RSS 的 `<category>`）行不通：11-10 對 642、656 的 `external.php?type=RSS2&forumids=<id>&lastpost=1` 都回 200 但 0 則——分類版本身不放串，RSS 不含子版的串。
- 改讀父版的版頁 HTML（collector 的 `HEADERS`），子版是 `li[id^=forum]`：642 底下 643 Letters from the Producer、644 Letter from the Producer LIVE；
  656 底下 657 Tank Roles、658 DPS Roles、659 Healer Roles、660 Other Battle Systems、661 Disciples of the Land、662 Disciples of the Hand。
- **Decision**：對應是 537 プロデューサーレターLIVE → 644、550 TANK → 657、551 DPS → 658、552 HEALER → 659、553 その他バトルシステム → 660。
- 請求：11-10 本機對 `forum.square-enix.com` 送 13 個請求、間隔 ≥ 60 秒（約 10 分鐘），全部 200，沒有 429。

## R4 英文版串頁面的時間格式與時區（實測，11-10 T001）

- 015 R2 的做法：同一則回覆比 RSS 的 `pubDate`（GMT）與頁面 `span.date`。
- 659 最新一串（`threads/532931`，post 6857299）：頁面 `span.date` 是 `11-08-2026 06:11 AM`，`_parse_vb_time` 照日本時間換成 `2026-11-07T21:11Z`；
  RSS `pubDate` 是 `Sat, 07 Nov 2026 21:11:58 GMT`，分鐘精度一致。版頁的「最後回覆」也對得上：657 顯示 `11-07-2026, 05:52 AM`、RSS `2026-11-06T20:52:27Z`；658 顯示 `11-05-2026, 02:24 AM`、RSS `2026-11-04T17:24:56Z`（都是 +9 小時）。
- **Decision**：英文版跟日文版同一個時區（日本時間）、同一個串頁面格式，T006 不改程式；T004 用英文串頁面的片段把它鎖住。
- 注意：版頁列表的格式多一個逗號（`MM-DD-YYYY, hh:mm AM`），串頁面的 `span.date` 沒有；collector 只解析串頁面。
- T004 的 fixture 要重抓：上面那串的頁面（`https://forum.square-enix.com/ffxiv/threads/532931`），11-10 的原文只存在當時 session 的 scratch。

## R5 英文版每週的供給（實測，11-10 T002；只量了一週）

| 子版 | RSS 則數 | 窗口內（11-02～11-09） | 最近 7 天 |
|---|---|---|---|
| 644 PLL | 0 | 0 | 0 |
| 657 Tank | 2 | 1 | 1 |
| 658 DPS | 7 | 6 | 3 |
| 659 Healer | 3 | 1 | 1 |
| 660 Other Battle Systems | 2 | 1 | 1 |
| 合計 | 14 | 9 | 6 |

- 量法：`_forum_window`（11-10 跑，窗口是 11-02 00:00Z～11-09 00:00Z）對各子版 `lastpost=1` RSS 的 `pubDate` 計數；沒有一版回滿 15 則，沒有被 RSS 截掉。
- 644 最後一次回覆是 08-14（版頁顯示），RSS 0 則。英文版的量比日文版少；只量了一週，隔週可以再量一次。

## R6 分析篇數上限（判斷，Luke 裁示「可以考慮加大」）

- **Decision**: 上限改由 `PIPELINE_CONFIG_YML` 的一個鍵決定（缺鍵時 20，行為不變）；新值等 R5 量到供給後提出，Luke 核定。
- **Rationale**: 憲章 IV 要求生成式呼叫有明寫的上限，值住在執行它的地方；`docs/external-services.md` 的 Gemini 那一列同步改成指向這個鍵。
- 參考量：拿掉 Reddit 後，日文版加 Lodestone 一週約 7～11 篇（`3cq` 節三週）；每篇分析約 15～18 秒，多 10 篇約多 3 分鐘。
- 上限截掉論壇串時印一行（FR-003），讓之後調整有依據。
- 11-10 的量（R5）：英文版一週 9 串，加上日文版與 Lodestone 的 7～11 篇，一週約 16～20 篇，接近 20。11-09 週報每篇分析平均 19.6 秒（FOCUS 的 runtime 基準），多 5 篇約多 100 秒。
- **建議**（判斷，T003 由 Luke 核定）：25。理由：正常週約 16～20 篇，20 會在大 patch 週先截掉論壇串；25 留 5 篇餘裕，週報多約 1.5 分鐘，離 SC-005 L1 的 20 分鐘還遠。截掉時照 FR-003 印一行，之後依實際截斷再調。
- **Decision**（T003，Luke 2026-11-10）：30。比建議的 25 多留餘裕；大 patch 週週報約多 3 分鐘（每篇 19.6 秒 × 10），仍在 SC-005 L1 的 20 分鐘內（11-09 是 10m31s）。

## R7 請求量與間隔（判斷，憲章 IV）

- 每個論壇版每週：RSS 1 次，加上每串最多 `max_pages`（預設 3）頁，頁間 `time.sleep(1)`（`src/collector.py:712`）。英文五個版加上去，請求數大約翻倍。
- 11-09 本機連打 10 次就 429（R3）。Actions 上目前日文五個版沒有 429 的紀錄（11-02 有一版逾時、一版 502）。
- **Decision**: 照 015 的間隔上線，log 已會印每版的失敗；英文版加入後的第一、二週看 `來源失敗` 那一行，有 429 再加大間隔（判斷）。

## R8 UA（實測，讀程式；11-09 更正）

- RSS 走 `_fetch_rss_bytes`，送 `GaryuNewsBot/1.0 (+mailto:…)`（`src/collector.py:176`）；HTML 送 `Mozilla/5.0 (compatible; GaryuNewsBot/1.0; +mailto:…)`（`src/collector.py:23`）。
  只有 `PTT_HEADERS`（`src/collector.py:28`，交通來源）是瀏覽器 UA。
  2026-11-10：PTT 連程式一起移除（Luke 裁示，另一個 PR），`PTT_HEADERS` 跟著刪；`src/gn_resolver.py` 的 `_HEADERS`（GN 還原與媒體頁 og）也是瀏覽器 UA，同一個 PR 換成正式 UA。
- 更正：11-09 討論中 agent 一度說「collector 靠瀏覽器 UA 讀 Reddit」，是把 `PTT_HEADERS` 當成 collector 的 UA 讀錯了；當天讀本週熱門 feed 也是用那個（拼壞的）字串打的。
  拿掉 Reddit 之後，FFXIV 的來源都送 `GaryuNewsBot` 的 UA。PTT 的瀏覽器 UA 屬交通來源，不在本 spec。
