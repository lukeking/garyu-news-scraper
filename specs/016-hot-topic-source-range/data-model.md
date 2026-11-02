# Data Model: 熱點報告標示來源涵蓋的日期區間

不改 schema。唯一的資料形狀變更在 `hot_topic_reports.source_article_links`（JSONB 陣列）的每一項。

## 焦點事件項目（`source_article_links[]`）

| 欄位 | 型別 | 改動 | 說明 |
|---|---|---|---|
| `link` | string | 不變 | 來源文章的 link，對到 `articles.link` |
| `title` | string | 不變 | 回填時由純字串轉來的項目沒有這欄 |
| `summary` | string | 不變 | 產生報告時截前 200 字 |
| `published` | string（ISO 8601，帶時區） | **新增** | 來源文章的發布時間原字串；找不到文章或文章沒有發布時間時不帶這欄 |

規則：

- 新報告：`analyze_hot_topic`、`analyze_category_digest` 回傳的每一項都帶 `published`（來源有值時）。
- 回填：dict 項目補 `published`；純字串項目轉成 `{link, published}`；已有 `published` 的不覆寫；找不到的不補。
- 讀取端對兩種舊形狀（dict 沒有 `published`、純字串）都要容忍：沒有日期的項目不計入區間。

## 報告（`hot_topic_reports`）——不變的欄位

`week_start_date`、`topic_label` 是分享連結的錨點（`?week=<ISO 週>#topic-<topic_label 的 slug>`），本 spec 任何步驟都不寫它們。
回填以 `id` update，只寫 `source_article_links`。

## 衍生值（只在前端，不存）

- **涵蓋區間**：一份報告所有帶 `published` 的焦點事件，換成台灣時間日期後的最早／最晚。沒有任何可用日期 → 無區間。
- **link → 報告週次對照**：整份報告清單裡，每個焦點事件的 link 對到它所在報告的 ISO 週次（同一 link 可對到多個週次）。
  文章列的 ★ 與加強樣式只看這張對照。

## 狀態

沒有狀態轉換。`articles.hot_topic_analyzed` 的寫入與語意不變（週報選材、彙整消耗、buffer 清理照舊用它）；只有前端的 ★ 不再讀它。
