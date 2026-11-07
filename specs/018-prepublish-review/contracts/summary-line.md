# Contract: 週報 log 的 `[審稿]` 摘要行

讀者：週驗收 routine（`routines/weekly-verify/PROMPT.md`），它從 Actions log 逐字取這一行寫進 Linear 報告。格式改了，routine 就讀不到，
所以格式由單元測試鎖住（`decision-style` §三：有讀者的 log 格式是契約）。

每份報告一行，在發布決定之後、寫入審核紀錄之前印出（紀錄寫入失敗也已經印過）：

```text
[審稿] <topic_label> | 狀態=<status> | 高 <a>／中 <b>／低 <c> | 套用 <x>/<y> | 原因=<status_reason 或 -> | <秒數>s
```

- `<status>` 是 `data-model.md` 的六種狀態之一。
- `高／中／低` 是三個嚴重度的發現數；`not_reviewed` 時三個都寫 `-`。
- `套用 x/y`：y 是中、高的發現數，x 是實際套用的條數；沒有審時寫 `-/-`。
- `原因`：`not_reviewed`、`revision_rejected`、`partially_applied` 時是 `status_reason`，其餘寫 `-`。
- 秒數是審稿呼叫加套用的時間，取整數。

例：

```text
[審稿] 道安政策 · 彙整 | 狀態=revised | 高 1／中 3／低 2 | 套用 4/4 | 原因=- | 31s
[審稿] 機車事故 · 中時 | 狀態=not_reviewed | 高 -／中 -／低 - | 套用 -/- | 原因=call_failed: HTTP 503 after 8 attempts | 0s
```

一週跑完，另印一行合計，讓 routine 分得出「零份報告」和「審稿整段沒跑」：

```text
[審稿] 本週合計：報告 <n> 份，已審 <r> 份，修稿採用 <m> 份
```
