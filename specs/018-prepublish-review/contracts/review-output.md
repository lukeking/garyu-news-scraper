# Contract: 審稿呼叫的輸出

審稿模型以 structured output（`responseMimeType: application/json`）回這個形狀。不是合法 JSON、或缺必要欄位，整份就記
`not_reviewed / invalid_response`，照發原稿（FR-012）。

```json
{
  "findings": [
    {
      "quote": "另自 7 月起毒駕納入第二當事人統計，單月造成 7 死 [9]",
      "category": "wrong",
      "severity": "high",
      "cause": "input",
      "problem": "統計定義放寬被寫成因果，讀者會以為毒駕者撞死 7 人",
      "replacement": "另自 7 月起毒駕統計納入第二當事人（被撞的一方也計入），該月統計數字為 7 人死亡 [9]"
    }
  ]
}
```

| 欄位 | 必要 | 值 |
|---|---|---|
| `findings` | 是 | 陣列，可以是空的 |
| `quote` | 是 | 逐字取自報告的一段；程式要在報告裡剛好找到一次才套用 |
| `category` | 是 | `wrong`（寫錯）／`bias`（觀點偏頗） |
| `severity` | 是 | `high`／`medium`／`low` |
| `cause` | 是 | `instruction`／`input`／`model` |
| `problem` | 是 | 錯在哪、讀者可能怎麼誤讀 |
| `replacement` | 否 | 取代 `quote` 的文字；空字串＝刪掉；沒有這個欄位＝只記錄不套用 |

程式端的規則（`src/report_review.py`，由單元測試鎖住）：
- 只套用 `severity` 為 `high`、`medium` 而且有 `replacement` 的發現。
- `quote` 在報告裡出現 0 次或多於 1 次，不套用，`apply_note` 寫 `quote_not_found`／`quote_ambiguous`。
- 先在**原稿**上把所有要套的原句定位好，再一次套用（不是一條改完再找下一條）；位置重疊的兩條都不套，`apply_note` 寫 `quote_overlap`。
- 整份檢查只算修稿新增的失敗；刪掉的字數超過原稿 30% 也整份退回（research R2）。
- 套用之後跑單條檢查（research R5）；沒過就退回這一條，`apply_note` 寫 `check_failed:<項目>`。
- 未知的 `category`、`severity`、`cause` 值：那一條記錄、不套用，`apply_note` 寫 `invalid_field:<欄位>`。
