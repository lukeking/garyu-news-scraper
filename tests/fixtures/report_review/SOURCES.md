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

## 重生成輸出（spec 018 Unit 21，T048–T050）

取樣日：2026-11-08。main 用 `scripts/replay_report_review.py --regenerate`（`gemini-3.8-flash`，輸入都是 `reconstructed`）重生成、
逐條判過的輸出，判定在 `specs/018-prepublish-review/evaluation.md`。原檔只在本機 `research/`（gitignored），下表的來源路徑都在那底下。

| 檔案 | 報告 | 來源（`research/…`） | evaluation.md |
|---|---|---|---|
| `sc001_digest_2026-10-19.json` | 10-19「道安政策 · 彙整」，25 篇 | `2026-11-08-sc001-regen/2026-10-19-5c36e323-5ee2-487d-b91f-86d5e792ac57.json` | SC-001 節「第二批取樣」的取樣 2 |
| `sc001_digest_2026-10-26.json` | 10-26「道安政策 · 彙整」，25 篇 | `2026-11-08-sc001-regen/2026-10-26-8432740b-5efc-4998-9ae0-78ed4bfe661b.json` | 同上 |
| `sc001_digest_2026-11-02.json` | 11-02「道安政策 · 彙整」，25 篇 | `2026-11-08-sc001-regen/2026-11-02-961b1aba-e7a0-47ad-b456-fc0799f19bd7.json` | 同上 |
| `sc001_hot_2026-10-19.json` | 10-19「科技執法 · 新聞」三軸，4 篇 | `2026-11-08-sc001-regen/2026-10-19-1737ec8f-ac5f-4502-902e-624c4205e785.json` | 同上（與三份彙整同一批重跑） |
| `sc001_hot_2026-09-14.json` | 09-14「道安政策 · 交通安全」三軸，10 篇 | `2026-11-08-sc001-regen/2026-09-14-0c3bf9ca-d203-445a-ba09-9b035fc8314d.json` | 同上 |
| `sc007_hot_<週>.json`（7 份） | GNS-011 取樣的 7 份三軸 | `2026-11-08-intersection-data-probe/data/t047-gns011-fr005c/<週>-<報告 id>.json` | GNS-011 節「FR-005c 之後（T047）」 |
| `sc008_<組>_run1.json`（6 份） | 09-28「機車事故 · UDN」三軸，4 篇，[1][2] 前接各組紀錄 | `2026-11-08-intersection-data-probe/data/regen-fr005c/<組>/run1/2026-09-28-421d0bdf-5c3e-4a72-8bad-a422efc4df4f.json` | 「GNS-20261108-5xf」節「FR-005c 之後（T046）」 |

- 每個檔取自原檔的 `week`、`topic`（存成 `label`）、`template` 與 `regenerated` 的 `model`、`text`（存成 `report_text`）、`sources`、`title_only_ids`，值原樣。
  `sources` 與 `title_only_ids` 就是重播當時交給 `check_report()` 的那兩個參數，所以用它們重跑 `check_report()` 得到的命中與原檔的 `checks.regenerated.hits` 相同（2026-11-08 對過）。
  原稿、`input_text` 與 `checks` 沒有收。
- `sc008_` 的組名是 `research/` 的目錄名：`body-only`＝只有內文、`placebo`＝拿掉工程欄位、`unrelated`＝無關紀錄、`real`＝真實警方紀錄、
  `counterfactual`＝反事實、`positive`＝正向案例。每組兩次只收 run1；[1][2] 摘要開頭那段紀錄就是當時的輸入。
- `sc001_digest_2026-11-02.json` 的 `[8]` 摘要是亂碼，跟上面 `digest_2026-11-02.json` 的 `[9]` 是同一篇（重生成的清單順序不同），照留。
