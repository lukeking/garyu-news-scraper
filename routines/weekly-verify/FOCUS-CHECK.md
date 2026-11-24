# 週一 FOCUS 檢查

你是 cloud routine，零先前脈絡。只做下面這件事：不改 repo、不開 PR、不動 Linear。

為什麼有這支：週驗收 routine 每週四 07:00Z 從 `main` 讀 `FOCUS.md`，驗收同一週週一的兩份週報；FOCUS 的適用週要在那之前改成那個週一。
09-28 那次沒更新，routine 照舊版跑，沒有任何東西出聲。這支只負責在過期時讓維護者當場知道。
Linear 不能當通道：維護者手機的 Linear 通知是關的，而且 routine 以維護者的帳號做的動作不會產生通知。
2026-11-24 起改成每週一 04:00Z、檢查本週一（已定 2026-11-24，`GNS-20261123-1wx`）；之前是每週三檢查下週一，驗收在週一。

## 1. 判定

1. 用 `date -u +%F` 取今天（UTC），算「本週一」＝今天或之前最近的週一、「本週四」＝本週一加 3 天，格式都是 `YYYY-MM-DD`。
2. 讀 `routines/weekly-verify/FOCUS.md`（已 checkout 的 `main`），找 `適用週：YYYY-MM-DD` 那一行。
3. 適用週 ≥ 本週一 → 已更新：不通知，最後一行回報 `FOCUS 已更新（適用週 <日期>）`，結束。
4. 其他情況（較舊、找不到那行、檔案不存在）→ 過期，做第 2 節。

## 2. 通知：兩個都做，一個失敗不影響另一個

**(a) 推播**：用 `ToolSearch` 載入 `PushNotification`，呼叫一次，`status` = `proactive`，`message` =
`garyu FOCUS.md 過期：適用週 <目前值>，應為 <本週一>。<本週四> 15:00（台北）前要 merge。`
逐字記下工具回傳值。

**(b) 日曆事件**：用 Google Calendar connector 在 primary 日曆建事件：

- `summary`：`garyu：更新 FOCUS.md（<本週四> 15:00 前 merge）`
- 時間：今天 20:00–20:15，`timeZone` = `Asia/Taipei`。若台北時間已過 19:50，改成現在起 10 分鐘後開始、長 15 分鐘。
- `overrideReminders` = `[{"method": "popup", "minutes": 0}]`，`availability` = `AVAILABILITY_FREE`，`notificationLevel` = `NONE`。
- `description`：適用週目前是 <目前值>、應為 <本週一>；更新步驟見 `routines/weekly-verify/README.md`「每週維護」；本週驗收報告在 Linear project「News Scraper Weekly Verification」。

建完用回傳的 event id 讀回一次（`get_event`），確認事件存在、開始時間是你要的那個。

## 3. 回報

最後一行：`FOCUS 過期（<目前值>，應為 <本週一>）→ 推播：<回傳值或失敗原因>；日曆：<event id 與開始時間，或失敗原因>`。
