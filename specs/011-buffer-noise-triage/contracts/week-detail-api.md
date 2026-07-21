# Contract: week-detail API — 雜訊分級欄位

**Feature**: 011-buffer-noise-triage | **Date**: 2026-07-21
**Endpoint**: `GET /api/weeks/{week_id}` （`handleWeekDetail`，`workers/api/src/index.js`）

## 變更摘要

於回應的每個 article 物件新增兩個**推導**欄位。既有欄位、排序、分頁、篩選參數皆不變。

## 新增欄位

| 欄位 | 型別 | 語意 |
|---|---|---|
| `noise_downgrade` | `boolean` | 該篇是否應被呈現層降級。已套用門檻，前端直接消費 |
| `source_multiple` | `number \| null` | 該來源的採用率倍率。`null` = 設定未涵蓋此來源。僅供除錯與調校可見性，前端 MUST NOT 用它自行套門檻 |

**回應片段**：

```json
{
  "week_id": "2026-W30",
  "article_count": 85,
  "articles": [
    {
      "title": "…",
      "source": "Google News 機車交通",
      "major_category": "機車事故",
      "image_url": "",
      "initial_quality_score": 0.213,
      "hot_topic_analyzed": false,
      "noise_downgrade": true,
      "source_multiple": 0.41
    }
  ]
}
```

## 不變式（MUST 成立）

1. **`noise_downgrade` 與 `source_multiple` 不存在於資料庫。** 兩者於回應組裝時推導，MUST NOT 出現在任何 `select=` 子句或 upsert 欄位清單中。
2. **`noise_downgrade` 為 `false` 當且僅當**該來源未出現在設定中，或其 `multiple >= threshold`。
3. **設定缺失或無法解析時**，所有文章的 `noise_downgrade` MUST 為 `false`、`source_multiple` MUST 為 `null`。端點 MUST NOT 因設定問題而回傳錯誤——降級是增益功能，不是必要路徑。
4. **對所有 `week_id` 一致套用**，包含設定量測窗口以外的週次。舊週不因缺乏當時的量測而被排除。
5. **零額外 I/O**：推導 MUST NOT 觸發任何 Supabase 查詢或外部請求。

## 相容性

- **新增欄位，無破壞性變更。** 既有前端忽略未知欄位，可先部署 Worker 再部署前端。
- FFXIV 路徑共用同一端點但不同 `content_type`。FFXIV 文章的來源不會出現在交通的設定中，因此 `noise_downgrade` 恆為 `false`，行為不變（spec 明訂 FFXIV 不在範圍且不得退化）。

## 驗證方式

無 JS 測試框架（見 plan.md 的 Complexity Tracking）。契約以手動請求驗證：

1. 取一個設定涵蓋來源佔多數的週次 → 確認 `noise_downgrade` 有 `true` 也有 `false`。
2. 取 W20（最早週，遠早於量測窗口）→ 確認欄位仍存在且值合理（不變式 4）。
3. 將 Worker 設定變數暫時設為無效字串 → 確認端點仍 200、全部 `noise_downgrade: false`（不變式 3）。
4. 以 `content_type=ffxiv` 請求 → 確認全部 `false`。
