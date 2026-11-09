# Contract: 設定與 log（019）

讀這些的有三個：週驗收 routine（讀 log）、`scripts/check_config_drift.py`（比對鏡像）、驗收時讀 `ffxiv-pool` 的人。格式是契約，用測試鎖住。

## 分析篇數上限

- 位置：`PIPELINE_CONFIG_YML`，`load_pipeline_config()` 讀得到，`game_deduplicate` 取用。
- 型別：正整數。缺鍵 → 20。不是正整數 → 啟動時報錯停下（不靜靜退回 20）。
- 回復：刪掉鍵 → 20（FR-008）。

## 截掉論壇串的 log

- 只在上限截掉至少一篇論壇（`vb_forum`）項目時印；沒截掉不印。
- 一行，WARNING，內容至少有：上限值、被擠掉的論壇項目數、逐來源篇數（跟 `FFXIV 入選` 那行同一種寫法）。
- 例（格式示意，字面在實作時定並寫進測試）：`FFXIV 上限 20 截掉論壇 3 篇：FFXIV EN Forum - TANK 2、FFXIV JP Forum - DPS 1`

## 英文論壇版的來源項目

- 型別 `vb_forum`，欄位與日文版相同；只有 research R4 判定英文頁面不是日本時間時，才多一個時區欄位，缺欄位＝日本時間。
- 時區解析失敗的回覆照 015：當窗口外並印原因，不猜。
