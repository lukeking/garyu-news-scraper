# Research: FFXIV 週報來源調整（019）

證據等級照慣例：實測／推論／判斷。硬門檻只收實測。三題 2026-11-09 沒查完（R3–R5），它們是 tasks 的第一個 spike，不是猜出來的答案。

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

## R3 英文官方論壇的五個子版（未完成：spike）

- 實測（11-09）：`forum.php` 回 200，英文上層版是 642 Letters from the Producer、656 Classes & Jobs（日文 535、549）。
- 子版 id 沒查到：讀 642、656、535、549 的版頁連續 429；等 2 分鐘、每頁隔 15 秒重抓仍 429；約 10 分鐘後打一次 RSS（`forumids=656,642`）也 429。
  約 20 分鐘內本機對 `forum.square-enix.com` 送了 10 個請求。日文的子版是連號（549 → 550–553、535 → 537），英文照推只是猜測。
- **怎麼查**：RSS2 每則帶 `<category domain=…/forums/<id>-…>`，對 642、656 各打一次就能列出子版 id 與名稱；請求之間至少隔 30 秒，429 就停、隔天再試；
  或請 Luke 用瀏覽器看版頁。查到的對應寫回本節。

## R4 英文版串頁面的時間格式與時區（未完成：spike）

- 015 R2 的做法：同一則回覆，比 RSS 的 `pubDate`（GMT）與頁面 `span.date` 的顯示。日文版是日本時間、格式 `MM-DD-YYYY hh:mm AM/PM`／`Today`／`Yesterday`。
- 英文版是同一套 vBulletin，訪客的顯示時區可能是站台預設（推論），但沒驗；`_parse_vb_time` 寫死 `JST`。
- **怎麼查**：英文每個子版取一串，比對 RSS `pubDate` 與頁面顯示；格式、時區跟日文版相同就沿用，不同就讓時區變成來源設定的一個欄位（預設日本時間，日文版不變）。

## R5 英文版每週的供給（未完成：spike）

- 沒量。決定 R6 的上限與 SC-005 的 runtime。
- **怎麼查**：R3 查到 id 後，對各子版的 `lastpost=1` RSS 數窗口內的串數（015 的量法）；至少一週，最好兩週。上線前量不到的話，先用 20 上線，從第一週的 log 讀。

## R6 分析篇數上限（判斷，Luke 裁示「可以考慮加大」）

- **Decision**: 上限改由 `PIPELINE_CONFIG_YML` 的一個鍵決定（缺鍵時 20，行為不變）；新值等 R5 量到供給後提出，Luke 核定。
- **Rationale**: 憲章 IV 要求生成式呼叫有明寫的上限，值住在執行它的地方；`docs/external-services.md` 的 Gemini 那一列同步改成指向這個鍵。
- 參考量：拿掉 Reddit 後，日文版加 Lodestone 一週約 7～11 篇（`3cq` 節三週）；每篇分析約 15～18 秒，多 10 篇約多 3 分鐘。
- 上限截掉論壇串時印一行（FR-003），讓之後調整有依據。

## R7 請求量與間隔（判斷，憲章 IV）

- 每個論壇版每週：RSS 1 次，加上每串最多 `max_pages`（預設 3）頁，頁間 `time.sleep(1)`（`src/collector.py:712`）。英文五個版加上去，請求數大約翻倍。
- 11-09 本機連打 10 次就 429（R3）。Actions 上目前日文五個版沒有 429 的紀錄（11-02 有一版逾時、一版 502）。
- **Decision**: 照 015 的間隔上線，log 已會印每版的失敗；英文版加入後的第一、二週看 `來源失敗` 那一行，有 429 再加大間隔（判斷）。

## R8 UA（實測，讀程式；11-09 更正）

- RSS 走 `_fetch_rss_bytes`，送 `GaryuNewsBot/1.0 (+mailto:…)`（`src/collector.py:176`）；HTML 送 `Mozilla/5.0 (compatible; GaryuNewsBot/1.0; +mailto:…)`（`src/collector.py:23`）。
  只有 `PTT_HEADERS`（`src/collector.py:28`，交通來源）是瀏覽器 UA。
- 更正：11-09 討論中 agent 一度說「collector 靠瀏覽器 UA 讀 Reddit」，是把 `PTT_HEADERS` 當成 collector 的 UA 讀錯了；當天讀本週熱門 feed 也是用那個（拼壞的）字串打的。
  拿掉 Reddit 之後，FFXIV 的來源都送 `GaryuNewsBot` 的 UA。PTT 的瀏覽器 UA 屬交通來源，不在本 spec。
