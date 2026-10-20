# Evaluation: FFXIV 週報取樣修正

merge 前的驗證紀錄。週報上的判定（SC-001、SC-002、SC-005、SC-006）在 BACKLOG `GNS-20261020-sbe`。

## T026 SC-004 實測：舊的 Lodestone 設定在新程式下會出聲

**時間**：2026-10-20 20:59（+0800），本機（家用 IP），程式 `b5e4cd6`（S3 已審過）。
**設定**：prod 現行的 `SOURCES_FFXIV_YML`（`gh variable get … --env production`，9 個來源；Lodestone 仍是 `category/2`
與 `li.news__list--topics`）。只跑 `FFXIVCategory().collect()`，不篩選、不分析、不寫庫。

```text
[WARNING] FFXIV Lodestone JP 更新資訊: 回 200 但解析出 0 項（selector 可能失效）
[INFO] FFXIV Lodestone JP 更新資訊: 0 筆
[INFO] 收集完成，共 51 筆（去重前）
[INFO] 來源失敗：1/9（FFXIV Lodestone JP 更新資訊）
```

各來源：Reddit 25、Lodestone 0、論壇列表頁 15、TW 修正說明 5、論壇 RSS（舊網址、沒有 `lastpost=1`）PLL 0／TANK 0／DPS 1／
HEALER 0／その他 5。

**結論**：通過。09-21～10-19 五週記成 INFO、沒人發現的 `0 筆`，在新程式下是 WARNING，而且列進 `來源失敗`。
