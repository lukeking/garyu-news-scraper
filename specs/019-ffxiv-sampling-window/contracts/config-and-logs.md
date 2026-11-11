# Contract: 設定與 log（019）

讀這些的有三個：週驗收 routine（讀 log）、`scripts/check_config_drift.py`（比對鏡像）、驗收時讀 `ffxiv-pool` 的人。格式是契約，用測試鎖住。

## 分析篇數上限

- 位置：`PIPELINE_CONFIG_YML` 的 `ffxiv.max_selected`，`load_pipeline_config()` 讀得到，`game_deduplicate` 取用。T005、T007、T008 都用這個名字。
  名字對應 log 的 `FFXIV 入選` 與 `game_deduplicate` 裡的 `selected`；不叫 `max_articles`，因為 `src/pipeline/ffxiv.py` 已有一個 `max_articles = 30`（T008 查它有沒有被用到）。
- 型別：正整數。缺鍵（含整個 `ffxiv` 區塊不在或是空的）→ 20。不是正整數 → `game_deduplicate` 一開始就報錯（`RuntimeError`，不靜靜退回 20），輸入是空的也報。
- 報錯落在 FFXIV 的 filter 階段，不在載入設定時：`src/main.py` 逐 category 接住例外，印 `[ffxiv] 處理失敗：[pipeline_config] ffxiv.max_selected 必須為正整數…`，
  那一週沒有 FFXIV 報告，交通照常，job 不標紅。Luke 2026-11-11 裁示照實際行為寫（原本寫「啟動時報錯停下」）：檢查不搬進 `load_pipeline_config`，
  交通的 daily 讀同一份設定、載入失敗時會降級跑。週驗收靠 FOCUS 找 `[ffxiv] 處理失敗` 那一行（T013）。
- 回復：刪掉鍵 → 20（FR-008）。

## 截掉論壇串的 log

- 只在上限截掉至少一篇論壇（`vb_forum`）項目時印；沒截掉不印。
- 一行，WARNING，內容至少有：上限值、被擠掉的論壇項目數、逐來源篇數（跟 `FFXIV 入選` 那行同一種寫法）。
- 例（格式示意，字面在實作時定並寫進測試）：`FFXIV 上限 20 截掉論壇 3 篇：FFXIV EN Forum - TANK 2、FFXIV JP Forum - DPS 1`

## 英文論壇版的來源項目

- 型別 `vb_forum`，欄位與日文版相同；只有 research R4 判定英文頁面不是日本時間時，才多一個時區欄位，缺欄位＝日本時間。
- 時區解析失敗的回覆照 015：當窗口外並印原因，不猜。
