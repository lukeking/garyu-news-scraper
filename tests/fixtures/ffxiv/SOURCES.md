# tests/fixtures/ffxiv 的來源

抓取日：2026-10-20（約 12:26 UTC＝日本時間 21:26）。頁面上的 `Today`／`Yesterday` 以這一刻的日本日期為準
（Today＝10-20、Yesterday＝10-19），測試要注入同一個日本日期的「現在」。

| 檔案 | 來源網址 | 留下的節點 |
|---|---|---|
| `thread_last_page.html` | `https://forum.square-enix.com/ffxiv/threads/498925-%E7%8D%A3%E4%BD%BF%E3%81%84%E3%82%B9%E3%83%AC?goto=newpost`（轉到 `?p=6851739#post6851739`，「獣使いスレ」第 65 頁） | 「Page 65 of 65」、全部 3 則回覆（都是 `Today`） |
| `thread_prev_page.html` | `https://forum.square-enix.com/ffxiv/threads/498925-%E7%8D%A3%E4%BD%BF%E3%81%84%E3%82%B9%E3%83%AC/page64` | 「Page 64 of 65」、10 則中的 5 則（絕對日期 3 則、`Yesterday` 2 則） |

每則回覆只留 `li[id^=post_]`、其中的 `span.postdate`（含 `span.date`）與 `[id^=post_message_]`（內文照抓到的原樣）；
其餘節點與 HTML 註解都拿掉。

抓的當下最後一頁只有 3 則、全是 `Today`，所以 `Yesterday` 落在前一頁（tasks.md T001 原本預期兩者都在最後一頁）。
