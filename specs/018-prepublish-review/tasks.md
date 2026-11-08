# Tasks: 週報發布前審核——修生成指令，加一步審稿＋修稿

**Input**: `specs/018-prepublish-review/` 的 spec.md、plan.md、research.md、contracts/、quickstart.md
**2026-11-08 縮成 US1**：US2、US3 與上線量測（T014～T033）拿掉，理由見 spec Clarifications 最後一節；原文在 `06985f5`。
**Tests**: 要寫。本 repo 走 delegated-TDD（`CLAUDE.local.md`「Delegated-TDD 閘門接線」），每個實作 unit 測試先行。
**標記**：`[ ]` 未做 → `[-]` 實作完、待審 → `[X]` 審過且 main 複驗；verification-only 的 task 由 main 驗完直接 `[X]`。

## Format: `[ID] [P?] [Story] [Req] Description`

- 本機 `python` 不在 PATH：一律 `.venv/bin/python`。
- 會呼叫真的 Gemini 的步驟都照 prod key 計費（同一個 NT$300 月上限）；資料庫在這些步驟裡只讀。

---

## Phase 1: 現況量測與三條 Unchecked 假設（verification-only）

只產出紀錄（research.md、evaluation.md、spec 的 Assumptions），不改程式；scratch 腳本放 scratch 根目錄，不進 repo。

- [X] T001 [FR-004, SC-001] 重建 10-19、10-26、11-02 三份「道安政策 · 彙整」的生成輸入（唯讀查 `hot_topic_reports.source_article_links` 與 `articles`；清單**照 `source_article_links` 的順序**，它就是當時送給模型的順序、第 i 個對到 `[i]`，不重新排序，也不讀本機的 `max_articles`；摘要照 400 字截斷），用 research R4 的規則逐篇判「只有標題」，對照評論說的每份 6–11 篇，看邊界上的幾篇定案 20 字門檻；結果與逐篇判定寫進 `specs/018-prepublish-review/research.md` R4
- [X] T002 [FR-006, FR-016] 檢查 Unchecked 假設「已發布的三軸熱點報告也能重建生成輸入」：唯讀查全部已發布的三軸報告（`topic_label` 不是彙整的那些），逐份算 `source_article_links` 在 `articles` 找得回的比例；結果寫進 research.md 新節「三軸輸入可重建性」，spec 的 Assumptions 那條改成 `Checked:`（附數字）或維持 `Unchecked:` 並寫明缺口
- [X] T003 [FR-006, FR-009] 檢查 Unchecked 假設「三軸熱點報告的錯型與彙整不完全相同」：照 11-06 做法用 headless `claude -p`（不給工具）扮資深新聞編輯，評 T002 裡輸入重建完整的 3–4 份三軸報告；main 拿重建的清單與報告原文逐條核對，成立的寫進 research.md 新節「三軸錨點」（原句、錯在哪、嚴重度與判定理由、類別；嚴重度照 research R6 的定義由 main 判）；刻意找低嚴重度的例子，跟 T004 合起來至少 2 個（FR-009）；spec 的 Assumptions 那條依結果改寫
- [X] T004 [FR-009] 偏頗類錨點：main 從 `specs/BACKLOG.md` `GNS-20261031-s3h` 節「評論提出、main 沒有逐條對過的」挑偏頗類（刪掉論據、地方自評寫成成效、身分標示不一致等），拿 T001 重建的清單與報告原文核對，成立的至少 2 個寫進 research.md 新節「偏頗錨點」；同一張表補上 s3h 那五條的嚴重度與判定理由（research R6）；低嚴重度的例子跟 T003 合起來至少 2 個；偏頗類或低嚴重度不足 2 個時寫明，交給 Luke 決定 FR-009 怎麼辦
- [X] T005 [FR-007, SC-002] 檢查 Unchecked 假設「同廠商的審稿模型盲點可能與生成模型相近」：scratch 腳本用草擬的審稿 prompt（標準裡排除「毒駕 7 死」與「全國 154 萬」兩句）讓 `gemini-4-argon` 審 10-26 那份彙整，看有沒有點出這兩句；記 token 與秒數；沒點出就換 `gemini-2.5-pro` 再試一次。結果寫進 research.md R1，spec 的 Assumptions 那條依結果改寫

---

## Phase 2: 只有標題的判定與機械檢查（Foundational）

US1 的量測與 US2 的套用都用這兩樣。

- [X] T006 [P] [FR-004, FR-010, SC-001, SC-003] 在 `tests/unit/test_report_review.py` 寫測試（先紅；介面與檢查名照 `contracts/check-report.md`，fixture 在 `tests/fixtures/report_review/`）：`is_title_only()` 的四種形狀、兩種網站樣板（LINE TODAY 討論牆前綴加標題、台視影音簡介，research R4）與 T001 定案的門檻（邊界兩側各一例，門檻用字面值）；`check_report()` 每一項（各節標題、`[n]` 超出範圍、只有標題的 ID 出現在 `### 分節彙整`、概覽裡的「共 N 起／個事件」、「互相獨立／無直接因果／各自獨立」、日期沒標報導日、替換文字帶出原句與來源都沒有的數字、三軸「交織度分布」三類加總不等於清單篇數（A 軸寫「不適用」時沒有這一行，不算失敗）、刪掉的字數超過原稿 30%（29% 與 31% 各一例，門檻用字面值）；整份檢查只回報修稿新增的失敗（原稿已有的同一項不算）。咬合對照：用 T001 重建的已發布原稿當 fixture，至少「互相獨立」與「事件數」兩項要回報 > 0
- [X] T007 [FR-004, FR-010] 在新模組 `src/report_review.py` 照 `contracts/check-report.md` 實作 `is_title_only()` 與 `check_report()`（純函式，不碰網路與資料庫），讓 T006 轉綠

---

## Phase 3: User Story 1 - 指令不再製造已知錯型 (Priority: P1) 🎯 MVP

**Goal**: 彙整與三軸的生成指令與清單組裝改掉，指令造成的錯型不再出現。
**Independent Test**: 重播 `--regenerate` 三份彙整，`check_report()` 的四類在重生成版本合計 0、在原稿 > 0（SC-001）。

- [X] T008 [P] [US1] [FR-001, FR-002, FR-003, FR-004, FR-005, FR-005a, FR-006] 在 `tests/unit/test_digest_prompt.py` 寫測試（先紅）：`DIGEST_SYSTEM_PROMPT`／`DIGEST_PROMPT_TEMPLATE` 不含「互相獨立」，含禁止自行推論關聯與數字範圍的規則；`build_digest_input()` 的清單用「報導日：」、只有標題的報導不在清單裡、編號接在有摘要的之後、`ordered_links` 依 `[1]..[N]`；報告組裝時 `### 本期概覽` 第一行是程式寫的「本期收錄 N 篇報導，其中 M 篇只有標題」，最後一節是 `### 僅標題`、逐行照抄原標題附 ID；`build_hot_topic_input()` 的清單把只有標題的那幾篇摘要寫成「（僅標題）」，`HOT_TOPIC_PROMPT_TEMPLATE` 含引用時標「僅標題」與數字範圍的規則，A 軸含「本批無事故報導，不適用」的寫法，人因與工程欄含「來源未載」的寫法（FR-005a）
- [X] T009 [US1] [FR-001, FR-002, FR-003, FR-004, FR-005] 在 `src/analyzer.py` 改 `DIGEST_SYSTEM_PROMPT`、`DIGEST_PROMPT_TEMPLATE`，抽出確定性的 `build_digest_input(pool_articles, max_articles)`（回傳清單文字、`ordered_links`、`{"articles": N, "title_only": M}`），`analyze_category_digest` 改用它並在生成後加上計數行與 `### 僅標題`；回傳值維持 `(report_text, ordered_links)`（實驗腳本依賴兩元組）
- [X] T010 [US1] [FR-004, FR-005, FR-005a, FR-006] 在 `src/analyzer.py` 改 `HOT_TOPIC_PROMPT_TEMPLATE`（C 軸數字範圍規則、引用只有標題的報導時標「僅標題」、A 軸「本批無事故報導，不適用」、人因與工程欄「來源未載」），抽出 `build_hot_topic_input(bucket_articles)`，`analyze_hot_topic` 改用它；回傳值不變
- [X] T011 [P] [US1] [FR-015, FR-016] 在 `tests/unit/test_replay_report_review.py` 寫測試（先紅）：腳本模組沒有引用任何 `upsert_*`（讀模組原始碼斷言）；用假 client 時，沒有審核紀錄的報告走重建並標 `"input": "reconstructed"`；`--regenerate` 走 `build_digest_input`／`build_hot_topic_input`；輸出 JSON 有 `checks.original` 與 `checks.regenerated`、同名 `.md` 存在；找不到報告時結束碼 1 並印原因
- [X] T012 [US1] [FR-015, FR-016, SC-001] 寫 `scripts/replay_report_review.py`（`contracts/replay-cli.md` 的 `--week`、`--topic`、`--out`、`--regenerate`）：唯讀重建輸入、可選重生成、兩份都跑 `check_report()`、寫 JSON 與修前修後的 `.md`、開始印估算費用、結束印 token 數（T015 之前印「token 數：未取得」與原因，Luke 2026-11-08 裁示）
- [X] T013 [US1] [SC-001] （verification-only）跑 T012 的 `--regenerate` 於三份彙整與兩份沒有事故的三軸報告（10-19「科技執法 · 新聞」、09-14「道安政策 · 交通安全」，research「三軸錨點」），原稿與重生成的四類計數、逐條命中，以及兩份三軸重生成的 A 軸有沒有寫「不適用」，寫進新檔 `specs/018-prepublish-review/evaluation.md` 的 SC-001 節；重生成仍有命中的，逐條判是規則還是檢查誤判。另外照 `GNS-011` 的完成標準量杜撰比率（Luke 2026-11-07 裁示併進 018）：取至少 6 份不同週、不同桶、輸入全找回的三軸報告（06-14 模板之後），原稿與重生成各自由 main 逐句核對「報告本文出現來源查無的具體事實」的處數，比率與逐條判定寫進 evaluation.md 的 GNS-011 節，並在 BACKLOG `GNS-011` 節寫明 prompt 改到哪裡、還要不要再改
- [X] T037 [P] [US1] [FR-004] 在 `tests/unit/test_report_review.py` 加測試（先紅；`contracts/check-report.md` 的 `is_title_only` 第 0、1 步）：Google News RSS 的 HTML 錨點摘要（完整的 `<a href="https://news.google.com/rss/articles/…">標題</a>&nbsp;&nbsp;<font color="#6f6f6f">媒體名</font>`，research R4「11-08 補」）判成只有標題；fclnews 推廣文字（前面有 `-`，字串照契約）判成只有標題；`<p>` 包著真導言（去掉標籤後扣掉標題仍至少 20 字）判成有摘要；既有的 LINE TODAY、台視案例照舊
- [X] T038 [US1] [FR-004] 在 `src/report_review.py` 的 `is_title_only()` 判定前去掉 HTML 標籤、還原 HTML 實體，`BOILERPLATE` 加 fclnews 那一段，讓 T037 轉綠；`build_*_input()` 與重播都經過它，不另改呼叫點
- [X] T039 [P] [US1] [FR-003, FR-005b] 在 `tests/unit/test_digest_prompt.py` 加測試（先紅）：`HOT_TOPIC_PROMPT_TEMPLATE` 的交織度分布有五類（含 `[工程資料未載]`、`[非事故]`），並寫明各類加總等於清單篇數；交織說明有「來源未載」的出口與「待查證：…？」的寫法；「評估工程缺陷必須對照具體標準」後面限定只評估來源寫到的道路條件；B 軸審查結果不再要求「分析制度慣性」，改成只列來源明文的制度做法並附 Article ID；A 軸有「傷亡人數、傷勢與行向照來源寫」一句；`HOT_TOPIC_SYSTEM_PROMPT` 有「質疑寫成待查的問題，不寫成機關的動機」。另在 `tests/unit/test_report_review.py` 加一例：五類的交織度分布加總等於篇數時 `interweave_sum` 不命中、不等時命中
- [X] T040 [US1] [FR-005b] 在 `src/analyzer.py` 照 research R3 的 FR-005b 五列改 `HOT_TOPIC_PROMPT_TEMPLATE` 與 `HOT_TOPIC_SYSTEM_PROMPT`，讓 T039 轉綠；`analyze_hot_topic`、`build_hot_topic_input` 的回傳值不變
- [X] T041 [US1] [SC-007] （verification-only）用 T012 的 `--regenerate` 重跑 `evaluation.md` GNS-011 節的同樣 7 份（命令列明示生成模型），照同一套判準逐句核對，寫進 GNS-011 節的新小節「FR-005b 之後」，說明 SC-007 爬到哪一階；06-22、07-20、08-03、08-24 的清單會因 T038 多標「（僅標題）」，輸入與 FR-005a 版不同，比較時分開說。BACKLOG `GNS-011` 節補一段結論
- [X] T042 [US1] [FR-015, FR-016] 截斷長度只留一份（Luke 2026-11-08 裁示，原本排在 Unit 6）：`src/analyzer.py` 的 `build_digest_input()`／`build_hot_topic_input()` 寫死的 `[:400]`／`[:600]` 改成模組常數 `DIGEST_SUMMARY_CHARS`、`HOT_SUMMARY_CHARS`；`scripts/replay_report_review.py` 重生成那一份的 sources 與檢查呼叫當下讀 analyzer 的常數，重建 018 之前舊報告的清單與原稿的 sources 改讀 `OLD_SUMMARY_CHARS`（生成當時的長度，FR-008 的原意，不跟著現行 analyzer 改）。測試先紅（`tests/unit/test_replay_report_review.py`）：把 analyzer 的常數改成小值，`build_*_input()` 的摘要、重生成的 sources 與交給 `check_report()` 的 sources 都跟著截短，原稿那一份不變；常數本身用字面值 400、600 釘住
- [X] T043 [US1] [FR-003, FR-004] 週報 `main()` 與 analyzer 的接點補測試（Luke 2026-11-08 裁示；spec-reviewer 對 `9aed012` 找到 `scripts/traffic_weekly_analysis.py` 呼叫 `analyze_hot_topic`／`analyze_category_digest` 的兩條邊沒有測試，把存進資料庫的 `source_article_links` 改成空清單單元測試照樣全綠）：`tests/unit/test_weekly_report_links.py` 讓真的 `analyze_*` 跑過 `main()`（只換 `_call_gemini` 與 `src.*` 的 I/O），斷言存下的連結與 prompt 裡的 `[i]`、彙整文末「僅標題」的 `[i]` 一一對得上。只補測試、行為不變，所以「先紅」改用突變證明：存成空清單、反轉、改回 buffer 順序、analyzer 把只有標題的排前面，各自要紅
- [-] T044 [P] [US1] [FR-005c] 在 `tests/unit/test_digest_prompt.py` 加測試（先紅）：`HOT_TOPIC_PROMPT_TEMPLATE` 的交織度分布有六類（五類加 `[工程未見放大]`），輸出格式那一行也是六類；A 軸寫明歸 [工程主導]／[雙因交織] 要說出來源寫到的哪一個工程條件、怎麼放大這件事的人因動作；寫明車種間質量落差這類每件混合車種事故都有的條件不能單獨當放大機制；`[工程未見放大]` 的定義是有工程資料、說不出放大機制、且不符 [人因主導]；寫明兩者都成立時歸 [人因主導]；[人因主導] 那一列與普遍化追問一字不改（用字面值釘住）。既有的五類測試（`FIVE_CLASS_LINE` 等）改成六類。另在 `tests/unit/test_report_review.py` 加一例：六類的交織度分布加總等於篇數時 `interweave_sum` 不命中、不等時命中
- [-] T045 [US1] [FR-005c] 在 `src/analyzer.py` 改 `HOT_TOPIC_PROMPT_TEMPLATE` 的 A 軸（五類定義、判定規則、輸出格式的交織度分布），讓 T044 轉綠；`analyze_hot_topic`、`build_hot_topic_input` 的回傳值不變；`contracts/check-report.md` 的 `interweave_sum` 那列跟著寫六類
- [ ] T046 [US1] [SC-008] （verification-only）用 `research/2026-11-08-intersection-data-probe/scripts/probe_prompt_ablation.py`（消融填 `none`、預期模型 `gemini-3.8-flash`）對 `evaluation.md`「GNS-20261108-5xf」節的六組輸入各重生成 2 次，[1][2] 與 [3][4] 的分類、交織說明有沒有把保護性條件寫成成因，寫進該節的新小節「FR-005c 之後」，說明 SC-008 爬到哪一階
- [ ] T047 [US1] [SC-007, SC-008] （verification-only）用 T012 的 `--regenerate` 重跑 `evaluation.md` GNS-011 節的同樣 7 份（命令列明示生成模型），照同一套判準逐句核對，寫進 GNS-011 節的新小節「FR-005c 之後」：SC-007 的 Gate 照不照過（SC-008 的門檻要它），五類處數與 FR-005b 版比；交織度分布各類篇數與 FR-005b 版比

**Checkpoint**: US1 可以單獨驗收。

---

## Phase 4: User Story 2 - 發布前審一次、修一次 (Priority: P1)

**2026-11-08 拿掉**：T014～T023 不做（原文在 `06985f5`）。T036 是 Unit 6 之前的探針，已做完，結果留在 research R1、R9，是 BACKLOG `GNS-20261108-r2t` 的依據。

- [X] T036 [US2] [FR-007, SC-002] （verification-only，Unit 6 之前；Luke 2026-11-07 裁示）scratch 腳本用逐句核對的提示（先列出報告裡每一句含數字或因果動詞的句子、逐句對照清單，再判問題）讓 `gemini-4-argon` 審 10-26 那份彙整 3 次；標準照 research R1「T005 探針」那一版加上生成規則，排除毒駕「7 死」與「全國」154 萬兩個例子。記每次有沒有點出這兩句、token 與秒數，結果寫進 research R1；3 次都沒過 Gate 時交 Luke 決定 US2 的做法，再開始 Unit 6


---

## Phase 5: User Story 3 - 每份報告的審核紀錄查得到 (Priority: P2)

**2026-11-08 拿掉**：T024～T031 不做（原文在 `06985f5`）。

---

## Phase 6: 上線與收尾

- [ ] T034 收尾（feature PR 轉 ready 前）：`backlog.py remove` 移出 `GNS-011`（T041 已量完）、`GNS-20261031-s3h`（做法被 2026-11-08 的裁示取代），`backlog.py add` 開 `GNS-20261108-r2t`（彙整的模型杜撰沒有審核者）；`backlog.py remove` 移出 `GNS-20261108-5xf`（FR-005c、SC-008，Luke 2026-11-08 裁示在 018 實作），並改寫以它為前提的 `GNS-20261108-2zc` 的觸發點；merge 那一週的 `routines/weekly-verify/FOCUS.md` 寫明三軸改六類交織度（多了 [工程資料未載]、[非事故]、[工程未見放大]）、清單與報告出現「（僅標題）」、log 多出 `✗ 彙整 … 全部只有標題…不生成`，不判異常；照 `~/.agents/skills/delegated-tdd/spec-reviewer-template.md` 派 `spec-reviewer` 對 US1 的 FR、SC 跑一次，矩陣與 main 的裁示記在 PR 內文（Luke 2026-11-07 裁示，bare `GUB-025` 的第二個實際用例；那一列剩下的是三項通則裁示，不在 018 做）；PR 內文貼 `backlog_trailers.py pr-line` 的 `Backlog:` 行；PR 內文記 bare 提醒的處置：`GUB-20261101-9qe` 未做、不適用（garyu 不在名單，bare `#324` 已記）、`GUB-20261024-rcf` 見 T035
- [ ] T035 收尾（Luke 2026-11-07 裁示開成工項）：把 018 當 `GUB-20261024-rcf` 的第二個樣本寫進 bare `.agents/BACKLOG.md` 的 rcf 節（另開 bare PR）：`/speckit-tasks` 時 Assumptions 13 條、`Checked:` 11、`Unchecked:` 3（其中一條兩者都有）、step 2a 停點 0、Luke 劃掉或改寫的假設、Unit 1（T001–T005）推翻了什麼、`GUB-025` spec-reviewer 有沒有跑與它的缺口；附 018 的 PR 與 `evaluation.md` 位置

---

## Dependencies & Execution Order

- Phase 1（Unit 1）先做：T001 是 T004、T006 的 fixture 來源；T002 是 T003 的輸入；T005 決定 US2 的模型。
- Phase 2（Unit 2）在 Phase 1 之後：門檻與 fixture 來自 T001。
- US1：Unit 3 → Unit 4 → Unit 5（量測）→ Unit 15（樣板與三軸指令第二次修正）→ Unit 16（量測）。
- T042（Unit 17）在 Unit 4 之後，跟 Unit 15、16 不相依。
- Unit 19（三軸指令第三次修正，`5xf`）在 Unit 15、16 之後 → Unit 20（SC-008、SC-007 量測）。
- Unit 13（收尾）在其餘 unit 都 `[X]` 之後。US2、US3 的 unit（6～12）2026-11-08 拿掉。

## Parallel Opportunities

- Phase 1：T002 → T003 一條線，T001 → T004 一條線，T005 獨立，三條可以同時進行。
- 各 unit 內的測試 task 標 `[P]` 的可以跟同 unit 以外的實作並行起草，但同一個 unit 的測試要先紅。

## Implementation Strategy

- MVP＝US1：只改指令，就能把三類錯型從源頭拿掉，T013 量得到。
- 一個 spec 一個 PR（`branch-protection`）。2026-11-08 起只出貨 US1；merge 時點等 CI 的版本策略定了再說（Luke 11-08：暫停一週，不為下一週的產出倉促決定）。

## Review units

### Unit 1: 現況量測與三條 Unchecked 假設 (verification-only)

- Tasks: T001, T002, T003, T004, T005
- Outcome: 「只有標題」的門檻定案；三軸輸入可重建的比例、三軸錨點、偏頗錨點、審稿模型的初步結果都寫進 research.md；三條 Unchecked 假設依結果改寫。
- Prerequisites: plan 已定；資料庫唯讀；`claude -p` 與 Gemini key 可用。
- Verification: research.md 新增的各節與逐篇判定；T005 的模型輸出存在 scratch，結論附 token 與秒數；main 讀回錨點的原句與重建清單一致。
- Review: main 本人核對（錨點是事實核對，不是程式審查）；Luke 看 T004 不足 2 個、T005 兩個模型都沒過時的處置。
- Merge or split: 五個都在寫程式之前回答「標準與門檻是什麼」，後面每個 unit 都依賴它們；只改紀錄，屬 verification-only。
- Unchecked assumptions: 「同廠商盲點」由 T005；「三軸錯型不同」由 T003；「三軸輸入可重建」由 T002。

### Unit 2: 只有標題的判定與機械檢查

- Tasks: T006, T007
- Outcome: `src/report_review.py` 的 `is_title_only()` 與 `check_report()`，對已發布原稿咬得到。
- Prerequisites: Unit 1 的 T001（門檻、fixture）。
- Verification: `pytest tests/unit/test_report_review.py`，T006 在 T007 之前紅、之後綠；對照 fixture 的命中數 > 0。
- Review: `tests/unit/test_report_review.py`、`src/report_review.py`、research R4、R5。
- Merge or split: 判定與檢查是同一個純函式模組的第一批產出，US1、US2 共用；不帶任何呼叫或寫入，所以跟 Unit 3 分開。

### Unit 3: 新的生成指令與清單組裝

- Tasks: T008, T009, T010
- Outcome: 彙整與三軸的指令、清單組裝、計數行與 `### 僅標題` 都照 FR-001～FR-006（含 FR-005a）改好，`analyze_*` 回傳值不變。
- Prerequisites: Unit 2（`is_title_only()`）。
- Verification: `pytest tests/unit/test_digest_prompt.py`（先紅後綠）；既有 `pytest tests/unit` 全綠（實驗腳本與既有測試不受回傳值影響）。
- Review: `tests/unit/test_digest_prompt.py`、`src/analyzer.py`（兩組 prompt、`build_digest_input`、`build_hot_topic_input`、兩個 `analyze_*`）。
- Merge or split: 兩個模板的改法是同一個產出（指令修正）的兩面，共用同一套清單組裝的測試。

### Unit 4: 重播腳本（重生成模式）

- Tasks: T011, T012
- Outcome: `scripts/replay_report_review.py` 能唯讀重建輸入、重生成、跑檢查、寫 JSON 與 `.md`。
- Prerequisites: Unit 2、Unit 3。
- Verification: `pytest tests/unit/test_replay_report_review.py`（先紅後綠）；「不引用 `upsert_*`」的斷言。
- Review: `tests/unit/test_replay_report_review.py`、`scripts/replay_report_review.py`、`contracts/replay-cli.md`。
- Merge or split: 腳本是獨立的工具產出，有自己的介面契約；審稿模式在 Unit 8 加，因為它依賴 Unit 6。

### Unit 5: SC-001 量測 (verification-only)

- Tasks: T013
- Outcome: evaluation.md 的 SC-001 節：原稿與重生成的四類計數；GNS-011 節：三軸杜撰比率（原稿與重生成）。
- Prerequisites: Unit 4。
- Verification: 腳本輸出的 JSON 留在 scratch，數字寫進 evaluation.md；main 抽查命中句。
- Review: main 複驗。
- Merge or split: 只跑既有入口、只改紀錄。

### Unit 6～12（2026-11-08 拿掉）

審稿呼叫、週報串接、重播加審稿、SC-002／003 量測、審核紀錄、摘要行、routine 與上線設定，原文在 `06985f5`。

### Unit 13: 收尾 (verification-only)

- Tasks: T034, T035
- Outcome: BACKLOG 移出與新增、FOCUS 寫明格式改了、spec-reviewer 矩陣、rcf 樣本寫進 bare。
- Prerequisites: Unit 1～5、14～17 都 `[X]`。
- Verification: `backlog.py` 的輸出與 diff；`backlog_trailers.py pr-line`；spec-reviewer 的矩陣由 main 逐條重跑；bare PR。
- Review: main 複驗。
- Merge or split: 只改紀錄、跑既有入口。

### Unit 14: 審稿提示探針 (verification-only)

- Tasks: T036
- Outcome: 逐句核對的提示能不能讓 argon 點出毒駕「7 死」，結果與 3 次之間的差異寫進 research R1；決定 US2「一次呼叫審加修」用 Gemini 可不可行。
- Prerequisites: Unit 1（標準的錨點與 T005 的結果）。在 Unit 6 之前做（Luke 2026-11-07 裁示）。
- Verification: 每次的 request 與 response 存在 scratch，結論附 token 與秒數；main 讀回被點出的原句與報告一致。
- Review: main 複驗；3 次都沒過 Gate 時 Luke 看結果決定做法。
- Merge or split: 只跑 scratch 探針、只改紀錄，不併進 Unit 6，因為它的結果決定 Unit 6 要不要照現在的設計做。

### Unit 15: 只有標題的樣板補齊與三軸指令第二次修正

- Tasks: T037, T038, T039, T040
- Outcome: `is_title_only()` 認得 Google News 的 HTML 錨點與 fclnews 推廣文字；三軸指令照 FR-005b 改好，`analyze_hot_topic` 回傳值不變。
- Prerequisites: Unit 2、Unit 3、Unit 5（FR-005b 的改法與兩種樣板都來自 T013 的量測）。在 Unit 6 之前做。
- Verification: `pytest tests/unit/test_report_review.py tests/unit/test_digest_prompt.py`（先紅後綠）；既有 `pytest tests/unit` 全綠；
  `tests/unit/test_comment_budget.py`（`src/analyzer.py` 的 LEGACY 是精確值，既有長註解不改行數）。
- Review: `tests/unit/test_report_review.py`、`tests/unit/test_digest_prompt.py`、`src/report_review.py`（`is_title_only`、`BOILERPLATE`）、
  `src/analyzer.py`（`HOT_TOPIC_SYSTEM_PROMPT`、`HOT_TOPIC_PROMPT_TEMPLATE`）、`contracts/check-report.md`。
- Merge or split: 兩件都是 T013 量測的直接產出、都改「模型拿到的清單與指令」，Unit 16 一次量到兩者；檔案不重疊，測試各自先紅。

### Unit 16: SC-007 量測 (verification-only)

- Tasks: T041
- Outcome: evaluation.md GNS-011 節「FR-005b 之後」：同樣 7 份的五類處數與逐條判定，SC-007 爬到哪一階；BACKLOG `GNS-011` 節的結論。
- Prerequisites: Unit 15。
- Verification: 腳本輸出的 JSON 留在 scratch，main 逐句核對，數字寫進 evaluation.md。
- Review: main 複驗。
- Merge or split: 只跑既有入口、只改紀錄。

### Unit 17: 截斷長度只留一份

- Tasks: T042
- Outcome: analyzer 的兩個截斷長度是具名常數，重播腳本讀同一份，analyzer 改長度時重播送給 `check_report()` 的 sources 跟著改。
- Prerequisites: Unit 3、Unit 4。
- Verification: `pytest tests/unit/test_replay_report_review.py tests/unit/test_digest_prompt.py`（新增的先紅後綠）；既有 `pytest tests/unit` 全綠；`tests/unit/test_comment_budget.py`。
- Review: `src/analyzer.py`（兩個常數與兩個 `build_*_input()`）、`scripts/replay_report_review.py`、`tests/unit/test_replay_report_review.py`。
- Merge or split: 一個產出（截斷長度只有一份），一個 checkpoint；inline 實作、tdd-reviewer 審。

### Unit 18: 週報接點的測試

- Tasks: T043
- Outcome: 週報存下的 `source_article_links` 跟報告編號對不上時，有單元測試會紅。
- Prerequisites: Unit 3（`build_*_input()` 的編號與連結順序）。
- Verification: `pytest tests/unit/test_weekly_report_links.py`；四個突變各自讓它紅；既有 `pytest tests/unit` 全綠；註解閘。
- Review: `tests/unit/test_weekly_report_links.py`、`scripts/traffic_weekly_analysis.py`（`main()` 的兩個呼叫點）。
- Merge or split: 一個產出（接點有測試），一個 checkpoint；inline 實作、tdd-reviewer 審。

### Unit 19: 三軸指令第三次修正（`GNS-20261108-5xf`）

- Tasks: T044, T045
- Outcome: A 軸有六類與判定規則（FR-005c），[人因主導] 那一列不變；`analyze_hot_topic` 回傳值不變。
- Prerequisites: Unit 15、Unit 16（FR-005b 的指令是這次改動的起點；改法來自 `evaluation.md`「GNS-20261108-5xf」節的診斷）。
- Verification: `pytest tests/unit/test_digest_prompt.py tests/unit/test_report_review.py`（新增的先紅後綠）；既有 `pytest tests/unit` 全綠；
  `tests/unit/test_comment_budget.py`（`src/analyzer.py` 的 LEGACY 是精確值）。
- Review: `tests/unit/test_digest_prompt.py`、`tests/unit/test_report_review.py`、`src/analyzer.py`（`HOT_TOPIC_PROMPT_TEMPLATE` 的 A 軸）、`contracts/check-report.md`。
- Merge or split: 一個產出（A 軸分得出工程有沒有放大），一個 checkpoint；inline 實作、tdd-reviewer 審。

### Unit 20: SC-008、SC-007 量測 (verification-only)

- Tasks: T046, T047
- Outcome: evaluation.md「GNS-20261108-5xf」節與 GNS-011 節各一個「FR-005c 之後」小節，SC-008 爬到哪一階、SC-007 的 Gate 照不照過。
- Prerequisites: Unit 19。
- Verification: 探針與重播的 JSON 留在本機，main 逐句核對，數字寫進 evaluation.md。
- Review: main 複驗。
- Merge or split: 只跑既有入口（探針只換讀資料的邊界）、只改紀錄。
