# Contract: 只有標題的判定與機械檢查（`src/report_review.py`）

純函式，不碰網路、資料庫與檔案。週報串接（Unit 7）、重播（Unit 4、8）、套用（Unit 6）、摘要行（Unit 11）共用。
依據：research R2（刪除上限、只算修稿新增的失敗）、R4（只有標題）、R5（各項檢查）；spec FR-003、FR-004、FR-005a、FR-010、SC-001、SC-003。
這份是 main 在 Unit 2 派工前寫的介面（2026-11-07），R4、R5 沒寫到的細節以這份為準。

## `is_title_only(title: str, summary: str) -> bool`

0. 去掉 `summary` 裡的 HTML 標籤（`<…>`），再還原 HTML 實體（`&nbsp;`、`&amp;` 等；Luke 2026-11-08 裁示）。Google News RSS 的
   `<a href="https://news.google.com/rss/articles/…">標題</a>&nbsp;&nbsp;<font color="#6f6f6f">媒體名</font>` 因此變成「標題＋媒體名」，由第 3 步判成 `True`；
   去掉標籤後還有真內容的（例 `<p>` 包著的導言）照常判 `False`。
   結尾沒有閉合的標籤片段（`<` 接字母、之後到字串結尾都沒有 `>`）也去掉：庫裡有 7 篇錨點摘要存進去時就截在 500 字，斷在 `href` 的網址中間
   （2026-11-08 量，全在 07-20 以前的三軸報告）。`<` 後面不是字母的（例 `酒測值<0.15`）不動。
1. 從 `summary` 去掉已知的網站樣板（常數 `BOILERPLATE`，Luke 2026-11-07、11-08 裁示算進只有標題）：
   - LINE TODAY 討論牆前綴 `0則貼文 | 快來參與LINE TODAY討論牆上的討論 |`
   - 台視影音簡介整段 `台視影音：提供台視最新的綜藝、專題、節目預告及新聞影音，並有數個完整影音節目，供網友選擇收看。`
   - fclnews 推廣文字整段 `台灣新聞雲報提供台灣最中立最公正最即時的各類型新聞報導，包括政治新聞、焦點新聞、社會新聞、國際新聞、地方新聞、娛樂新聞、科技新聞、專訪新聞、政黨新聞、藝文活動、美食推廣、體育賽事等相關新聞報導。歡迎各界好友踴躍贊助推廣。`（庫裡 3 篇都是前面加一個 `-`，正規化會去掉）
2. 正規化 `title` 與 `summary`：NFKC、轉小寫、去掉標點（Unicode category `P*`）、分隔符（`Z*`）與空白。
3. 以下任一成立就回 `True`：
   - `summary` 是空的；
   - 與 `title` 相同，或被 `title` 包含；
   - 從 `summary` 去掉 `title` 之後，剩下不到 `TITLE_ONLY_MIN_CHARS`＝20 字（T001 定案）。
   `title` 比兩個版本：原樣，以及去掉最後一段「` - 媒體名`」（Google News 的標題結尾）之後；任一個版本符合就算。

驗收：fixture 三份彙整用它判出的 ID，與 fixture 裡 T001 記下的 `t001_title_only_ids` 完全相同。

## `check_report(report_text, *, template, sources, title_only_ids=(), original_text=None, replacements=()) -> dict[str, list[str]]`

- `template`：`"digest"` 或 `"hot"`；其他值丟 `ValueError`。
- `sources`：照清單順序的 dict（`title`、`summary`、`published`），第 i 個對到 `[i]`。彙整新格式裡只有標題的報導排在後面，也在 `sources` 裡。
- `title_only_ids`：只有標題的報導編號（1 起算）。
- 回傳：檢查名 → 命中字串的清單，空清單＝通過。該模板適用的檢查名都要出現在回傳裡（沒命中就是空清單）；不適用的不出現。

| 檢查名 | 模板 | 命中條件 | 命中字串 |
|---|---|---|---|
| `missing_section` | 兩者 | 缺節標題。彙整：`### 本期概覽`、`### 分節彙整`、`### 待追蹤`，`title_only_ids` 不是空的再加 `### 僅標題`。三軸：行首 `### 一、`、`### 二、`、`### 三、` | 缺的那個標題 |
| `id_out_of_range` | 兩者 | 方括號裡的數字不在 1..`len(sources)`；`[6, 8, 15]` 這種多個的逐一檢查；`[推斷，非直接證據]`、`[工程主導]` 這類不是數字的括號不算 | `[n]` |
| `title_only_in_sections` | 彙整 | `title_only_ids` 裡的編號出現在 `### 分節彙整` 那一節（到下一個 `### ` 開頭的行為止） | `[n]` |
| `self_count` | 彙整 | `### 本期概覽` 那一節有「共…N 起／個…事件」，例：`本期共收錄 19 起獨立事件`、`本期共彙整 24 個獨立事件`。程式寫的 `本期收錄 N 篇報導，其中 M 篇只有標題` 與 `本期收錄 25 篇報導` 不算 | 命中的那一段字 |
| `independence_claim` | 彙整 | 全文含 `互相獨立`、`無直接因果`、`各自獨立` | 命中的詞 |
| `date_unlabeled` | 彙整 | 報告裡帶「日」的日期（`2026 年 10 月 9 日`、`2026年10月2日`、`10 月 6 日`，空白可有可無）。日期後面 10 個字以內有「報導」，或任一 source 的 `title`／`summary` 去掉空白後含 `M月D日` 或 `M/D`，就算通過；其餘都命中。這項是啟發式，命中的由 main 逐條看 | 命中的日期原文 |
| `interweave_sum` | 三軸 | `交織度分布：` 那一行各類篇數（每個「N 篇」）的加總不等於 `len(sources)`；FR-005c 之後是六類（FR-005b 的 [工程資料未載]、[非事故]，加 FR-005c 的 [工程未見放大]），程式照舊整行加總；沒有這一行（A 軸寫「不適用」，FR-005a）就不檢查 | 例 `0+4+3=7≠8` |
| `replacement_new_number` | 兩者 | `replacements` 每一組 `(quote, replacement)`：`replacement` 裡的數字（阿拉伯數字，含千分位與小數）在 `quote` 與任一 source 的 `title`、`summary` 裡都沒出現 | 那個數字 |
| `deletion_over_cap` | 兩者 | `replacements` 刪掉的字數 Σ max(0, len(quote) − len(replacement)) 除以 `len(original_text)`，大於 `DELETION_CAP`＝0.30 | 例 `31.0%` |

- `replacements` 不是空的時 `original_text` 必填，否則丟 `ValueError`。
- 給了 `original_text`：同一套檢查（`replacement_new_number`、`deletion_over_cap` 除外）也跑在 `original_text` 上；
  每一項只留下原稿沒有的命中字串（同一檢查名內比字串）。原稿本來就有的失敗不算在修稿頭上（R2）。
- `SC001_CHECKS`＝`("independence_claim", "date_unlabeled", "self_count", "title_only_in_sections")`：SC-001 的四類，重播輸出的 `checks` 用這四個鍵計數。
- 單條檢查（`contracts/review-output.md` 的 `check_failed:<項目>`）就是用一組 `replacements` 呼叫 `check_report`，`<項目>` 是有命中的檢查名。

## 咬合對照（T006）

`tests/fixtures/report_review/` 是已發布的報告與重建的清單（來源與做法見那裡的 `SOURCES.md`）。用它們跑 `check_report` 至少要看到：

- 三份彙整的 `independence_claim` 都 > 0；10-26、11-02 的 `self_count` > 0。
- `title_only_in_sections` 命中數：10-19＝11、10-26＝6、11-02＝7（`title_only_ids` 給 T001 的結果）。
- 10-19 的 `date_unlabeled` 含 `2026 年 10 月 9 日`（s3h 的錨點：報導日寫成質詢日）。
- 09-07 三軸的 `interweave_sum` 是 `0+4+3=7≠8`。
