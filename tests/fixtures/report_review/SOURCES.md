# tests/fixtures/report_review 的來源

取樣日：2026-11-07。spec 018 T001 從 prod 唯讀重建（`hot_topic_reports` 與 `articles`），做法與結果在
`specs/018-prepublish-review/research.md` R4「T001 校準」與「三軸輸入可重建性」。

| 檔案 | 報告 | 清單 |
|---|---|---|
| `digest_2026-10-19.json` | 10-19「道安政策 · 彙整」已發布原文 | 25 篇，摘要截 400 字 |
| `digest_2026-10-26.json` | 10-26「道安政策 · 彙整」已發布原文 | 25 篇，摘要截 400 字 |
| `digest_2026-11-02.json` | 11-02「道安政策 · 彙整」已發布原文 | 25 篇，摘要截 400 字 |
| `hot_2026-09-07.json` | 09-07「機車事故 · TVBS」三軸已發布原文 | 8 篇，摘要截 600 字 |

- `report_text` 是 `hot_topic_reports.report_text` 原樣。
- `sources` 照 `source_article_links` 的順序（第 i 個對到報告的 `[i]`）；`title`、`published`（取前 10 字）、`summary` 取自 `articles`，
  `summary` 照生成時截斷。每篇摘要的前 200 字與 `source_article_links` 生成當時存的 200 字逐字相同。
- `t001_title_only_ids` 是 T001 用 research R4 的規則判出的只有標題的編號。
- 11-02 的 `[9]` 摘要是亂碼，生成當時就是這樣，照留。
