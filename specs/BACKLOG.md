# Spec Backlog

未編號的 spec 候選。有餘裕時再挑一個開 `/speckit-specify`，屆時才配 `NNN-` 編號。

---

## 整合測試指向本機 Supabase

**提出**: 2026-07-21，在實際造成正式資料汙染之後
**優先度**: 高於下方的前端測試框架——那項是**缺乏保護**，這項是會**主動造成損害**

**問題**：`tests/integration` 在 `.env` 有憑證時直接寫進**正式** Supabase 的 `articles` 表。
沒有任何防護把它擋下來，也沒有任何提示告訴執行者這件事正在發生。

**已發生的實害**：2026-07-21 為驗證 spec 011 而跑整合測試，插進 16 列測試資料
（`2025-W01-test` 等 week_id、`example.com` 連結）。汙染不只停在資料表——
`scripts/measure_source_uptake.py` 把它們納入統計，baseline 由 0.1954 位移到 0.1914，
每個來源倍率跟著偏，依此設定的 prod 變數 `SOURCE_UPTAKE_JSON` 整份是錯的，必須重設。
16 列已刪除，量測腳本已加 ISO week_id 過濾作為第二道防線——**但那只擋統計汙染，
擋不住資料被寫進去**。

**已知可用資源**：本機 Docker 已常駐一套 Supabase（容器 `supabase_*_backend`），
API `http://localhost:54321`、Postgres `localhost:54322`，金鑰由 `supabase status` 取得。
所以不需要新建基礎設施，只需要讓測試指過去。

**範圍草稿**（開 spec 時再確認）：
- conftest fixture：整合測試啟動時強制覆寫連線設定指向本機，**並在指向正式環境時直接 fail**
  而非放行。預設要安全，不能靠執行者記得。
- schema 建立／清理：本機實例是跨專案共用的，需要確認 `articles` 等表的建立方式。
- 唯讀診斷腳本**不在此範圍**——那些指向正式環境是正確且必要的，本 session 大量使用未造成影響。
  界線在「寫入」，不在「連線」。
- 順帶處理 `test_traffic_buffer::test_filter_attaches_category_and_score`：
  它在有憑證環境會 fail，長期被 skip 蓋住，實質上是同一個根因的徵兆。

---

## 前端測試框架（Storybook / E2E）

**提出**: 2026-07-21，從 011-buffer-noise-triage 的 Constitution Check 帶出
**優先度**: 低——「沒事幹的時候可以來實作」

**問題**：repo 的測試基礎建設全在 Python 端（`pytest`，`tests/unit` + `tests/integration`）。
JS 端**零測試**——`pages/shared/app.js`（約 510 行，含全部列表渲染、分組收合、
dismiss 狀態）與 `workers/api/src/index.js`（約 363 行，含全部端點與篩選邏輯）
都只能靠手動點擊驗證。

**觸發此項的具體事件**：011 的主要改動落在 JS 端，plan 階段只能在 Complexity Tracking
誠實記下「這是測試缺口，不假裝已覆蓋」，驗收改依賴 `quickstart.md` 的手動清單。
當時**刻意不順手引入框架**——那是未被要求的基礎建設，違反 YAGNI，也會讓 011 的
改動範圍失焦。但缺口是真的，且會隨每個前端 feature 累積。

**範圍草稿**（開 spec 時再確認）：
- Storybook 或等價工具：讓列表的各種狀態（空週、零圖片舊週、全部降級、全部收起、
  無摘要）能獨立呈現而不必造真實資料。這幾個狀態目前只能靠找到「剛好長那樣」的週次來驗。
- E2E：涵蓋 quickstart 裡那份手動驗收清單，特別是跨週次切換後的狀態行為
  （降級展開不持久化、來源收起要持久化——兩者相反，正是容易寫錯的地方）。
- Worker 端：純函式的契約測試（`normalizeRow`、篩選、以及 011 新增的雜訊推導）。

**注意事項**：
- Cloudflare Pages 前端無建置步驟（`pages/` 是手寫 HTML/CSS/JS 直接部署）。
  引入需要 bundler 的工具會改變部署模型——這是這項的主要成本，不是寫測試本身。
- 憲章 IV（Free Tier Discipline）：CI 若跑 E2E 需計入 Actions 每月 2000 分鐘額度。
