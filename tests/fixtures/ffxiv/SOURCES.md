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

## Lodestone

抓取日：2026-10-20（13:02 UTC，回應的 `Date` 標頭），用 `collector.HEADERS`。

| 檔案 | 來源網址 | 留下的節點 |
|---|---|---|
| `lodestone_category3.html` | `https://jp.finalfantasyxiv.com/lodestone/news/category/3`（アップデート，當下 20 則） | 最新的 5 個 `li.news__list`，照頁面順序：`更新のお知らせ(10/20)`、`Lodestone 更新のお知らせ(10/13)`、`コンパニオンアプリ 更新のお知らせ(10/13)`、`更新のお知らせ(10/13)`、`更新のお知らせ(9/19)` |
| `lodestone_detail.html` | `https://jp.finalfantasyxiv.com/lodestone/news/detail/148f852faaa79f79a8542a9450e9361b17940884`（上表第一則，10/20 hotfix） | `article.news__detail` 裡的 `header`（標題與時間）和 `div.news__detail__wrapper`（內文約 414 字） |

每個 `li` 照抓到的原樣，含 `<a href>`、`p.news__list--title` 與 `ldst_strftime(<epoch>, 'YMD')`。五則的 epoch（UTC）：
10-20 06:50、10-13 11:00、10-13 07:27、10-13 07:13、09-19 02:38。
詳細頁拿掉了 `div.news__footer`；留下 `header` 是為了讓測試分得出「取 `detail_selector` 的節點」與「取整頁」。
