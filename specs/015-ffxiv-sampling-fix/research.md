# Research: FFXIV 週報取樣修正

**日期**：2026-10-20｜**證據等級**：實測＝當場量到；推論＝從實測推出、未直接量；判斷＝取捨
所有請求唯讀、免憑證；探針與一次性腳本在 session scratchpad，結論寫在這裡。Actions 的可達性見 PR `#173`（run `39416499596`）。

## R0 現況：20 篇怎麼被選出來（實測，讀程式＋10-19 週報 log）

`FFXIVCategory.filter()`（`src/pipeline/ffxiv.py`）：`freshness_filter`（跨週標題指紋＋年齡）→ `filter_and_deduplicate`
（同週標題 hash，保留先出現的）→ `game_deduplicate`（Jaccard 去重後依 `published` 降冪取前 20）。

10-19 原始收集約 54 筆：Reddit 25、論壇列表頁 15、TW 修正說明 5、論壇 RSS 9（DPS 1、その他 8）、Lodestone 0。
Reddit 有時間且最新；HTML 來源 `published` 是空字串，`_pub_key` 給 `datetime.min`，永遠排最後。論壇 RSS 依開串時間，
多半比 Reddit 舊。結果 20 篇全是 Reddit。

**順序陷阱**（推論，讀程式）：兩個去重步驟都「保留先出現的」，而先出現的是設定檔裡排前面的來源。論壇列表頁（只有標題）
在設定裡排在五個版的 RSS 之前，同一串若同時出現，留下的會是只有標題的那份。→ 去重前就要依權重排序（R4）。

## R1 收集窗口：固定的週邊界，不用「現在往前 7 天」（判斷）

- **Decision**：論壇回覆的窗口＝［本次執行所在 ISO 週的週一 00:00 UTC − 7 天, 該週一 00:00 UTC）。
  串是否入選看 RSS 的最後回覆時間 ≥ 窗口起點；回覆是否收進看回覆時間落在窗口內。
- **Rationale**：週報排程是每週一 00:00 UTC（`weekly.yml`），實際開跑常延遲 30 分鐘到 2 小時。用「現在往前 7 天」，
  相鄰兩週的窗口會依開跑時間重疊或留縫，同一則回覆可能被分析兩次（違反 FR-003）。固定邊界讓相鄰兩週首尾相接；
  同一週重跑得到同一個窗口、同一個 link，upsert 覆寫同一列（憲章 III）。不必查資料庫。
- **Alternatives**：(a) 現在往前 7 天——其他來源現在的做法，論壇因為要做回覆級去重才不適用；
  (b) 查資料庫拿每串上次分析到的回覆 id——嚴格，但多一個查詢與它的失敗路徑。
- **範圍**：只有論壇回覆用固定邊界。Reddit、Lodestone 等照舊（`CUTOFF`），跨週標題指紋擋重複。

## R2 討論串頁面（實測，10-20，本機；Actions 可達見 `#173`）

- RSS 的 `link` 是 `threads/<id>-<slug>?goto=newpost`，會轉到最後一則所在那頁（`?p=<post_id>#post<post_id>`）。
  `guid` 是串網址本身。
- 每頁 10 則，回覆是 `li[id^=post_]`，內文在 `[id^=post_message_]`。分頁網址是 `<串網址>/pageN`；頁面上有「Page 65 of 65」。
- 時間在 `span.date`：`10-15-2026 01:16 PM`，最近兩天寫成 `Today 08:32 PM`／`Yesterday 04:53 PM`。
  **時區是日本時間**：RSS `pubDate` 11:32:28 GMT 的那則，頁面顯示 `Today 08:32 PM`。解析「Today／Yesterday」要以日本時間的「今天」為準。
- 回覆 id 遞增（`post_6848824` → `post_6851739`），可當同一串內的排序與去重鍵。
- 量（「獣使いスレ」，551）：窗口 10-12～10-19 跨 3 頁、約 25 則；每則 456～1,261 字。

## R3 回覆的上限（判斷，錨在 R2）

- **Decision**：每串最多往前翻 3 頁、收最新 20 則、合併後最多 6,000 字（新的優先，合併後依時間由舊到新排）。三個值寫在設定。
- **Rationale**：「獣使いスレ」一週約 25 則、3 頁；20 則／3 頁涵蓋大部分。6,000 字約是 6～8 則的長度，足以讓分析講出
  「這週在討論什麼」（SC-001 L2），又讓 20 篇裡最多十幾篇論壇項目的輸入不失控。成本：論壇項目一週約 6 串（10-20 實測）×
  ≤6,000 字，Gemini 輸入多約數萬 token，月成本增量是分的量級（推論，依 10-19 評比的 3.8 單價）。
- **Alternatives**：只收最後一則（Luke 10-20 否決：撐不起 L2）；不設字數上限（長期串一週可到 2 萬字）。

## R4 排序與權重（判斷，Luke 10-20 裁示純權重排序）

- **Decision**：每個 FFXIV 來源在 `sources_ffxiv.yml` 自己帶 `weight`（整數，越大越先）；收集時蓋到每篇文章上
  （與既有的 `relevance_exempt`、`lookback_days` 同一個做法）。`FFXIVCategory.filter()` 在兩個去重步驟之前就依
  （權重降冪, 時間降冪, 沒時間的最後）排序，`game_deduplicate` 保留排序、取前 20。
  初值：PLL 100、四個 class & jobs 版 80、Lodestone 60、TW 修正說明 50、Reddit 20、論壇列表頁 10。沒寫 `weight` 的來源是 0，
  每次收集印一行警告。
- **Rationale**：權重跟來源寫在一起，改名、增減來源不必同步第二份清單（traffic 的 `source_weights` 以名稱為鍵，
  名稱漂掉時是沉默的）。去重前就排序，同一串重複時留下的是權重高的那份（R0 的順序陷阱）。
- **Alternatives**：沿用 `pipeline_config.yml` 的 `source_weights`（名稱鍵、0–1 浮點、預設 0.5）——那是 traffic 的可信度分數，
  語意不同，混用會讓兩邊互相牽動。

## R5 跨週去重：論壇項目改以回覆為單位（判斷，讀程式）

- 現況：`freshness_filter` 拿標題指紋比對整張 `articles` 表；FFXIV 以 `link` 為鍵 upsert。長期串標題每週相同，第二週起會被擋。
- **Decision**：論壇項目的 `link` 是 `<串網址>?p=<窗口內最新回覆 id>`，每週不同；項目帶 `dedup_key = forum:<串 id>:<最新回覆 id>`，
  `freshness_filter` 對帶 `dedup_key` 的項目略過標題指紋比對（年齡檢查照做），並印一行「略過標題指紋（以回覆去重）」。
  不重複分析靠 R1 的固定窗口保證。
- **Alternatives**：標題加上日期區間讓指紋每週不同——改到讀者看到的標題，而且把「以回覆去重」藏進字串技巧裡。

## R6 Lodestone（實測，10-20）

- `category/3` 有 20 個 `li.news__list`（`li.news__list--topics` 對到 0，這就是五週 `0 筆` 的原因）。
- 每個 `li` 剛好有一個 `ldst_strftime(<epoch>, …)`（UTC 秒），可當發布時間。28 天內 7 則、7 天內 1 則。
- 標題分三種：`更新のお知らせ(10/20)`（遊戲）、`Lodestone 更新のお知らせ`、`コンパニオンアプリ 更新のお知らせ`（網站與 App）。
- 詳細頁內文在 `div.news__detail__wrapper`：hotfix 約 400 字、列出修正項目；大 patch（09-08）約 200 字、只有外部 patch notes 連結。
- **Decision**：html_patch 加三個選用設定——發布時間抽取、排除標題前綴、詳細頁內文（selector 與字數上限 2,000）。
  窗口用既有的 `CUTOFF`。詳細頁抓不到時退回只用標題並印原因。

## R7 PLL（537）：0 筆是沒人發文，不是壞掉（實測）

- 537 版面列表頁有串：第 89～93 回的「まとめを公開」都直接開在 537（最新第 93 回，08-17）。子版 1618、1597 的 RSS 也是 0。
- RSS 只涵蓋約四週（推論：551 最舊一則 09-21），08-17 已超出，所以現在 0 筆。
- 第 93 回剛發的兩週，週報 log 記到 `プロデューサーレターLIVE: 1 筆`（08-24、08-31），前後兩週都是 0——RSS 會吐出 537 的新串。
- **Decision**：不另接子版。FR-011 結案。

## R8 robots.txt（實測，憲章 IV）

- `forum.square-enix.com/robots.txt` → 302 到 `notfound.php`（404）；`jp.finalfantasyxiv.com/robots.txt` → 404。
  兩個主機都沒有宣告爬取限制。新增的抓取路徑（討論串分頁、Lodestone 詳細頁）照既有做法間隔 1 秒。

## R9 「解析出 0 項」的判斷點（判斷，讀程式）

- **Decision**：共用一個小函式，在 HTTP 成功之後、任何篩選之前，用「selector 對到的節點數」判斷：
  html_patch＝`soup.select(selector)` 的長度；html_forum＝符合 `threads/\d+` 的連結數；PTT＝`div.r-ent` 的數量。
  為 0 時印 `<來源>: 回 200 但解析出 0 項（selector 可能失效）` 並 `_mark_failed`。RSS 不套用。
- PTT 的影響：計入 traffic daily 的來源失敗比例（> 50% 中止）。PTT 現在每天 403，本來就計入；只有「200 但 0 列」是新增的失敗。

## R10 輸入長度（實測，讀程式）

- FFXIV 的分析 prompt 直接帶 `summary`，沒有另外截斷；現行唯一的上限是收集時 `_clean_summary` 的 500 字。
- 前端主要顯示分析後的摘要，原始 `summary` 只在缺分析時當備援（`pages/shared/app.js`），長內容不會直接上頁面。
- **Decision**：論壇項目 6,000 字（R3）、Lodestone 2,000 字（R6）各自在收集時截；其他來源照舊 500 字。
