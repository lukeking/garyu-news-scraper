# Tasks: 週報發布前審核——修生成指令，加一步審稿＋修稿

**Input**: `specs/018-prepublish-review/` 的 spec.md、plan.md、research.md、data-model.md、contracts/、quickstart.md
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
- [ ] T037 [P] [US1] [FR-004] 在 `tests/unit/test_report_review.py` 加測試（先紅；`contracts/check-report.md` 的 `is_title_only` 第 0、1 步）：Google News RSS 的 HTML 錨點摘要（完整的 `<a href="https://news.google.com/rss/articles/…">標題</a>&nbsp;&nbsp;<font color="#6f6f6f">媒體名</font>`，research R4「11-08 補」）判成只有標題；fclnews 推廣文字（前面有 `-`，字串照契約）判成只有標題；`<p>` 包著真導言（去掉標籤後扣掉標題仍至少 20 字）判成有摘要；既有的 LINE TODAY、台視案例照舊
- [ ] T038 [US1] [FR-004] 在 `src/report_review.py` 的 `is_title_only()` 判定前去掉 HTML 標籤、還原 HTML 實體，`BOILERPLATE` 加 fclnews 那一段，讓 T037 轉綠；`build_*_input()` 與重播都經過它，不另改呼叫點
- [ ] T039 [P] [US1] [FR-003, FR-005b] 在 `tests/unit/test_digest_prompt.py` 加測試（先紅）：`HOT_TOPIC_PROMPT_TEMPLATE` 的交織度分布有五類（含 `[工程資料未載]`、`[非事故]`），並寫明各類加總等於清單篇數；交織說明有「來源未載」的出口與「待查證：…？」的寫法；「評估工程缺陷必須對照具體標準」後面限定只評估來源寫到的道路條件；B 軸審查結果不再要求「分析制度慣性」，改成只列來源明文的制度做法並附 Article ID；A 軸有「傷亡人數、傷勢與行向照來源寫」一句；`HOT_TOPIC_SYSTEM_PROMPT` 有「質疑寫成待查的問題，不寫成機關的動機」。另在 `tests/unit/test_report_review.py` 加一例：五類的交織度分布加總等於篇數時 `interweave_sum` 不命中、不等時命中
- [ ] T040 [US1] [FR-005b] 在 `src/analyzer.py` 照 research R3 的 FR-005b 五列改 `HOT_TOPIC_PROMPT_TEMPLATE` 與 `HOT_TOPIC_SYSTEM_PROMPT`，讓 T039 轉綠；`analyze_hot_topic`、`build_hot_topic_input` 的回傳值不變
- [ ] T041 [US1] [SC-007] （verification-only）用 T012 的 `--regenerate` 重跑 `evaluation.md` GNS-011 節的同樣 7 份（命令列明示生成模型），照同一套判準逐句核對，寫進 GNS-011 節的新小節「FR-005b 之後」，說明 SC-007 爬到哪一階；06-22、07-20、08-03、08-24 的清單會因 T038 多標「（僅標題）」，輸入與 FR-005a 版不同，比較時分開說。BACKLOG `GNS-011` 節補一段結論

**Checkpoint**: US1 可以單獨驗收。

---

## Phase 4: User Story 2 - 發布前審一次、修一次 (Priority: P1)

**Goal**: 每份報告生成後由 argon（或 T005 選定的模型）審一次，程式套用中、高嚴重度的替換。
**Independent Test**: 重播已發布的報告（留一），SC-002 的 Gate 與 SC-003 全過。

- [X] T036 [US2] [FR-007, SC-002] （verification-only，Unit 6 之前；Luke 2026-11-07 裁示）scratch 腳本用逐句核對的提示（先列出報告裡每一句含數字或因果動詞的句子、逐句對照清單，再判問題）讓 `gemini-4-argon` 審 10-26 那份彙整 3 次；標準照 research R1「T005 探針」那一版加上生成規則，排除毒駕「7 死」與「全國」154 萬兩個例子。記每次有沒有點出這兩句、token 與秒數，結果寫進 research R1；3 次都沒過 Gate 時交 Luke 決定 US2 的做法，再開始 Unit 6
- [ ] T014 [P] [US2] [FR-007] 在 `tests/unit/test_call_gemini_model.py` 寫測試（先紅）：`_call_gemini(model=…)` 打到該模型的網址；`response_mime_type="application/json"` 出現在 `generationConfig`；不帶這兩個參數時 payload 與現在逐位元組相同（固定的對照 payload）；回應的 `usageMetadata`（輸入、輸出 token 數）呼叫端拿得到，既有呼叫端不用改
- [ ] T015 [US2] [FR-007] 在 `src/analyzer.py` 的 `_call_gemini` 加 `model=None`、`response_mime_type=None` 兩個選填參數，並把回應的 `usageMetadata` 交給呼叫端（重播的 token 數與審核紀錄的 `usage` 用；Luke 2026-11-08 裁示），讓 T014 轉綠
- [ ] T016 [P] [US2] [FR-008, FR-009, FR-010, FR-011, FR-012] 在 `tests/unit/test_report_review.py` 加測試（先紅）：錨點資料（s3h 五條、T003 三軸、T004 偏頗）每個嚴重度至少 2 例；`build_review_standard(template, exclude=[…])` 排除後那句不在輸出裡；`parse_review(raw)` 照 `contracts/review-output.md` 驗欄位，壞 JSON／缺欄位丟 `InvalidReview`；`apply_findings()` 只套中、高且有替換的、`quote` 0 次與多次各記 `quote_not_found`／`quote_ambiguous`、兩條原句在原稿上位置重疊時兩條都記 `quote_overlap` 不套、全部原句先在原稿上定位再一次套用（前一條的替換不影響後一條的定位）、單條檢查沒過記 `check_failed:<項>`、未知值記 `invalid_field:<欄位>`；`decide_status()` 六種狀態各一例
- [ ] T017 [US2] [FR-009, FR-010, FR-011] 在 `src/report_review.py` 實作錨點資料、`build_review_standard()`、`parse_review()`、`apply_findings()`、`decide_status()`，讓 T016 轉綠
- [ ] T018 [US2] [FR-007, FR-008] 在 `src/analyzer.py` 加審稿 system prompt 與 `review_report(template, input_snapshot, report_text, model, exclude_anchors=())`：提示照 research R1「T036 逐句核對探針」的四步與 `checked_sentences`（`contracts/review-output.md`）；送出的清單就是 `input_snapshot`（同一個字串），JSON 模式呼叫 `_call_gemini(model=…)`，回 `parse_review()` 的結果；在 `tests/unit/test_report_review.py` 用 monkeypatch 的 `_call_gemini` 驗它送出的 prompt 含 `input_snapshot` 全文與報告全文、用的是指定的模型
- [ ] T019 [P] [US2] [FR-007, FR-012, FR-013] 在 `tests/unit/test_weekly_review_flow.py` 寫測試（先紅），monkeypatch `_call_gemini` 與 storage，跑 `scripts/traffic_weekly_analysis.py` 的真入口：沒設 `GEMINI_REVIEW_MODEL_NAME`、與 `GEMINI_MODEL_NAME` 相同、呼叫失敗、壞 JSON、沒發現、只有低、全套用、部分套用、整份退回，各自寫進 `hot_topic_reports` 的是哪一版、log 印的原因字串互不相同
- [ ] T020 [US2] [FR-007, FR-012, FR-013] 在 `scripts/traffic_weekly_analysis.py` 串起來：熱點與彙整各自生成後取 `build_*_input()` 的快照 → 照 `_GEMINI_DELAY` 間隔一次（憲章 IV：限流值寫在呼叫旁）→ `review_report()` → `apply_findings()` → `decide_status()` → 以發布版本 upsert 報告；每條放棄路徑印原因（負控 log），讓 T019 轉綠；T019 加一條：審稿呼叫之前有一次 `_GEMINI_DELAY` 的 sleep（monkeypatch `time.sleep` 記錄）
- [ ] T021 [P] [US2] [FR-015, SC-002] 在 `tests/unit/test_replay_report_review.py` 加測試（先紅）：`--exclude-anchor` 傳到 `review_report()`、`--review-model` 蓋過變數、輸出 JSON 有 findings、套用結果與狀態，`.md` 有修前修後並排
- [ ] T022 [US2] [FR-015, SC-002, SC-003] 在 `scripts/replay_report_review.py` 加審稿與套用，讓 T021 轉綠
- [ ] T023 [US2] [SC-002, SC-003, SC-005] （verification-only）對每個錨點跑留一重播（排除它、重播它所在的報告），記被點出與否；每份報告的發現由 main 拿來源逐條核對、算成立比例；SC-003 的四項檢查；Gate 沒過就換候選模型重跑並記錄；用重播實際的 token 數換算每月費用（照當時與 12-01 起的單價各算一次），加上現有用量比對 NT$300 上限（SC-005 的上線前估算）；用實際的刪除比例檢討 R2 的 30%。全部寫進 `evaluation.md` 的 SC-002、SC-003、SC-005 節與達成階數

**Checkpoint**: US1＋US2 合起來就是 Luke 選的兩件事；週報上線前要先過 T023。

---

## Phase 5: User Story 3 - 每份報告的審核紀錄查得到 (Priority: P2)

**Goal**: 審核紀錄進資料庫，週報 log 每份報告一行摘要，週驗收 routine 轉進 Linear。
**Independent Test**: 本機整合測試寫入讀回；單元測試鎖住摘要行格式；上線後連兩週量 SC-006。

- [ ] T024 [US3] [FR-014] 寫 `supabase_migrations/006_report_reviews.sql`（`data-model.md` 的欄位、唯一鍵、grant、RLS），`scripts/setup_test_db.sh` 的套用清單加上 006
- [ ] T025 [P] [US3] [FR-014] 在 `tests/integration/test_report_review_storage.py` 寫測試（先紅，本機 Supabase 54331）：同一把鍵 upsert 兩次只留一列且是第二次的內容；`findings`、`input_counts`、`usage` 的 JSON 原樣讀回
- [ ] T026 [US3] [FR-014] 在 `src/storage.py` 加 `upsert_report_review(record)`，讓 T025 轉綠
- [ ] T027 [US3] [FR-014] 在 `scripts/traffic_weekly_analysis.py` 於 upsert 報告之後寫審核紀錄；寫入失敗印 error、不擋發布；在 `tests/unit/test_weekly_review_flow.py` 加這兩條（寫入的紀錄 `published_text` 等於寫進報告的那一版；寫入丟例外時報告照發、log 有 error）
- [ ] T028 [P] [US3] [FR-014a] 在 `tests/unit/test_report_review.py` 加測試（先紅）：`format_summary_line()` 對六種狀態逐字等於 `contracts/summary-line.md` 的格式（`not_reviewed` 的三個 `-`、`-/-`），`format_total_line()` 的合計行
- [ ] T029 [US3] [FR-014a] 在 `src/report_review.py` 實作兩個格式函式，`scripts/traffic_weekly_analysis.py` 在寫紀錄之前印每份的摘要行、一週結束印合計行，讓 T028 轉綠；`tests/unit/test_weekly_review_flow.py` 加一條：紀錄寫入失敗時摘要行仍在 log
- [ ] T030 [US3] [FR-014a, SC-006] 在 `routines/weekly-verify/PROMPT.md` 加一節：從 Actions log 逐字取 `[審稿]` 行寫進報告，「未審」「修稿未採用」列原因，找不到任何 `[審稿]` 行時寫「找不到審稿摘要」（cold review 路徑，PR 要跑 cold review）
- [ ] T031 [US3] [FR-007] `docs/external-services.md` 的 Gemini 列補審稿模型、變數 `GEMINI_REVIEW_MODEL_NAME`、research R9 的估算與日期；`.github/workflows/weekly.yml` 的「週交通熱點分析」step env 加 `GEMINI_REVIEW_MODEL_NAME: ${{ vars.GEMINI_REVIEW_MODEL_NAME }}`（動到 `weekly.yml` 會觸發 `GNS-20261013-4g9` 的 pre-edit 提醒，照規則問 Luke 要不要併入）

---

## Phase 6: 上線與收尾

- [ ] T032 [FR-007, FR-014] （verification-only）上線：Luke 在 Supabase dashboard 貼 006，main 唯讀查表與 grant 讀回；`gh variable set GEMINI_REVIEW_MODEL_NAME --env production` 設成 T023 選定的模型並 `gh variable get` 讀回
- [ ] T033 [SC-004, SC-005, SC-006] （verification-only，merge 後）上線後連兩週：週報耗時與 timeout、各報告審稿秒數（`[審稿]` 行）、實際 token 換算月費用、紀錄的 `published_text` 與 `hot_topic_reports.report_text` 逐份相等、週驗收報告的摘要行與紀錄一致；寫進 `evaluation.md` 與 spec 的達成階數（另開 PR，同 017 的 T020）
- [ ] T034 收尾（feature PR 轉 ready 前）：`python3 ~/.agents/bin/backlog.py remove specs/BACKLOG.md GNS-011`（T041 量完 FR-005b 之後的杜撰比率、BACKLOG 該節寫明結論之後）；照 `~/.agents/skills/delegated-tdd/spec-reviewer-template.md` 派 `spec-reviewer` 跑一次，矩陣與 main 的裁示記在 PR 內文
  （Luke 2026-11-07 裁示，bare `GUB-025` 的第二個實際用例；那一列剩下的是三項通則裁示，不在 018 做）；`python3 ~/.agents/bin/backlog.py remove specs/BACKLOG.md GNS-20261031-s3h`，PR 內文貼 `backlog_trailers.py pr-line` 的 `Backlog:` 行；PR 內文記 bare 提醒的處置：`GUB-20261101-9qe` 未做、不適用（garyu 不在名單，bare `#324` 已記）、`GUB-20261024-rcf` 見 T035
- [ ] T035 收尾（Luke 2026-11-07 裁示開成工項）：把 018 當 `GUB-20261024-rcf` 的第二個樣本寫進 bare `.agents/BACKLOG.md` 的 rcf 節（另開 bare PR）：`/speckit-tasks` 時 Assumptions 13 條、`Checked:` 11、`Unchecked:` 3（其中一條兩者都有）、step 2a 停點 0、Luke 劃掉或改寫的假設、Unit 1（T001–T005）推翻了什麼、`GUB-025` spec-reviewer 有沒有跑與它的缺口；附 018 的 PR 與 `evaluation.md` 位置

---

## Dependencies & Execution Order

- Phase 1（Unit 1）先做：T001 是 T004、T006 的 fixture 來源；T002 是 T003 的輸入；T005 決定 US2 的模型。
- Phase 2（Unit 2）在 Phase 1 之後：門檻與 fixture 來自 T001。
- US1：Unit 3 → Unit 4 → Unit 5（量測）→ Unit 15（樣板與三軸指令第二次修正）→ Unit 16（量測）。
- US2：Unit 14（T036 提示探針）在 Unit 6 之前；Unit 6 要 Unit 1（錨點、模型）、Unit 2（檢查）、Unit 14 與 Unit 15（審稿標準收生成規則，要收 FR-005b 的）；Unit 7 要 Unit 6 與 Unit 3（`build_*_input()`）；Unit 8 要 Unit 4 與 Unit 6；Unit 9 在 Unit 8 之後。
- US3：Unit 10、Unit 11 要 Unit 7；Unit 12 要 Unit 11。
- Unit 13（上線、收尾）在 Unit 9 過 Gate、其餘 unit 都 `[X]` 之後；T033 在 merge 之後另開 PR。

## Parallel Opportunities

- Phase 1：T002 → T003 一條線，T001 → T004 一條線，T005 獨立，三條可以同時進行。
- 各 unit 內的測試 task 標 `[P]` 的可以跟同 unit 以外的實作並行起草，但同一個 unit 的測試要先紅。
- Unit 10（資料庫）與 Unit 11（摘要行）都只依賴 Unit 7，彼此獨立。

## Implementation Strategy

- MVP＝US1：只改指令，就能把三類錯型從源頭拿掉，T013 量得到。
- 一個 spec 一個 PR（`branch-protection`）：US1 不單獨出貨，等 US2、US3 一起；但 US1 的 unit 先做完、先審，讓 US2 建在穩定的清單組裝上。
- 上線前一定要過 T023 的 Gate：審稿抓不到「7 死」與「全國」，就是在每週多花錢與時間換一份雜訊。

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

### Unit 6: 審稿呼叫與套用

- Tasks: T014, T015, T016, T017, T018
- Outcome: `review_report()` 送出與生成相同的清單、拿回驗過形狀的發現；`apply_findings()`、`decide_status()` 照契約套用與判狀態。
- Prerequisites: Unit 1（錨點、模型）、Unit 2（檢查）、Unit 14（審稿提示探針）。
- Verification: `pytest tests/unit/test_call_gemini_model.py tests/unit/test_report_review.py`（各自先紅後綠）；不帶新參數時 `_call_gemini` 的 payload 與對照逐位元組相同。
- Review: 上述兩個測試檔、`src/analyzer.py`（`_call_gemini`、審稿 prompt、`review_report`）、`src/report_review.py`（錨點、標準、解析、套用、狀態）、`contracts/review-output.md`。
- Merge or split: 審與修在 research R2 合成一次呼叫，呼叫、解析、套用是同一個產出；`_call_gemini` 的參數只為它而加。

### Unit 7: 週報串接

- Tasks: T019, T020
- Outcome: 週報對每份報告跑審稿與套用，寫進 `hot_topic_reports` 的是決定後的版本，每條放棄路徑的原因印得出來。
- Prerequisites: Unit 3、Unit 6。
- Verification: `pytest tests/unit/test_weekly_review_flow.py`（真入口、monkeypatch 邊界，先紅後綠）；`pytest tests/unit` 全綠。
- Review: `tests/unit/test_weekly_review_flow.py`、`scripts/traffic_weekly_analysis.py`。
- Merge or split: 串接是獨立可驗的行為（發布哪一版），與審稿本身分開審，範圍才看得清楚。

### Unit 8: 重播加審稿

- Tasks: T021, T022
- Outcome: 重播腳本支援審稿、留一排除與換模型。
- Prerequisites: Unit 4、Unit 6。
- Verification: `pytest tests/unit/test_replay_report_review.py`（新增的先紅後綠）。
- Review: `tests/unit/test_replay_report_review.py`、`scripts/replay_report_review.py`、`contracts/replay-cli.md`。
- Merge or split: 同一支腳本的第二個能力，依賴 Unit 6，所以不併進 Unit 4。

### Unit 9: SC-002、SC-003 量測 (verification-only)

- Tasks: T023
- Outcome: evaluation.md 的 SC-002（留一、成立比例）與 SC-003；審稿模型定案。
- Prerequisites: Unit 8。
- Verification: 每次重播的 JSON 留在 scratch，數字與逐條核對寫進 evaluation.md。
- Review: main 複驗；模型若換掉，Luke 看結果。
- Merge or split: 只跑既有入口、只改紀錄。

### Unit 10: 審核紀錄表與寫入

- Tasks: T024, T025, T026, T027
- Outcome: 新表、`upsert_report_review()`、週報寫紀錄；寫入失敗不擋發布。
- Prerequisites: Unit 7。
- Verification: `bash scripts/setup_test_db.sh` 套到 006；`pytest tests/integration/test_report_review_storage.py`（本機 Supabase，先紅後綠）；`pytest tests/unit/test_weekly_review_flow.py` 新增的兩條。
- Review: `supabase_migrations/006_report_reviews.sql`、`scripts/setup_test_db.sh`、`tests/integration/test_report_review_storage.py`、`src/storage.py`、`scripts/traffic_weekly_analysis.py`、`tests/unit/test_weekly_review_flow.py`、`data-model.md`。
- Merge or split: schema、寫入函式與呼叫點是同一個產出（紀錄存得進去）。

### Unit 11: `[審稿]` 摘要行

- Tasks: T028, T029
- Outcome: 每份報告一行摘要與一週合計，格式照契約、測試鎖住；紀錄寫入失敗時仍印得出來。
- Prerequisites: Unit 7。
- Verification: `pytest tests/unit/test_report_review.py tests/unit/test_weekly_review_flow.py`（新增的先紅後綠）。
- Review: `src/report_review.py`（兩個格式函式）、`scripts/traffic_weekly_analysis.py`、兩個測試檔、`contracts/summary-line.md`。
- Merge or split: log 格式有外部讀者（routine），獨立成一個可審的契約產出；跟 Unit 10 互不依賴。

### Unit 12: 週驗收 routine 與上線設定

- Tasks: T030, T031
- Outcome: routine 讀得到 `[審稿]` 行並寫進報告；預算文件與 workflow env 備好上線。
- Prerequisites: Unit 11。
- Verification: routine 指示用 Unit 11 測試裡的範例 log 逐句讀過一次（main 照 PROMPT 的步驟手動跑 grep）；`weekly.yml` 的 YAML 用 `.venv/bin/python -c "import yaml…"` 讀得回、env 有這個鍵；PR 的 cold review。
- Review: `routines/weekly-verify/PROMPT.md`、`docs/external-services.md`、`.github/workflows/weekly.yml`。
- Merge or split: 都是「讓上線後看得到、跑得起來」的程序與設定，沒有程式邏輯；routine 那段要 cold review，同一個 PR 一起審。

### Unit 13: 上線與收尾 (verification-only)

- Tasks: T032, T033, T034, T035
- Outcome: prod 設定讀回、上線兩週的量測、BACKLOG 移出、rcf 樣本寫進 bare。
- Prerequisites: Unit 1～12、15、16 都 `[X]`；T033 在 merge 之後。
- Verification: 讀回的查詢與 `gh variable get` 輸出；evaluation.md；`backlog_trailers.py pr-line`；bare PR。
- Review: main 複驗；T032 的 dashboard 那一步由 Luke 做。
- Merge or split: T033～T035 只改紀錄、跑既有入口。T032 改的是 prod 的設定（dashboard 套 schema、設變數），不是 repo 裡的程式：
  套用的 SQL 與變數值在 Unit 10、Unit 9 已審過，這一步的檢查是讀回，所以不另開實作審查。

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
