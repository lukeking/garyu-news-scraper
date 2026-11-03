# Contract: 交通頁存在讀者裝置上的狀態（`localStorage`）

只在交通頁使用；FFXIV 頁不讀不寫。值讀不到、格式不對時，一律當成「沒有記錄」，不讓頁面壞掉。

| 鍵 | 值 | 誰寫 | 誰讀 |
|---|---|---|---|
| `traffic_stream_pref` | `default`（預設）／`reports`／`articles` | 齒輪設定 | `landingStream` |
| `traffic_stream_last` | `reports`／`articles` | 窄螢幕上目前那一條確定時：打開時的落地（不論是哪一層規則決定的）與每次切換 | `landingStream`（設定是 `default` 時） |
| `traffic_seen_reports` | ISO 8601 時間字串 | 熱點被顯示時；第一次打開時 | 「有新報告」的基準 |
| `traffic_seen_articles` | ISO 8601 時間字串 | 新文章被顯示時；第一次打開時 | 「新文章」篇數的基準 |

- 「第一次打開」＝ `traffic_seen_reports` 與 `traffic_seen_articles` 都沒有。
- 既有的鍵（`theme`、`garyu_filter_importance`、`dismissed-traffic`、已收起來源）不動。
- 清掉站上的資料等於回到第一次打開。
