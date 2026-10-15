# Implementation Plan: 補政策 digest 的來源

**Branch**: `014-policy-source-expansion` | **Date**: 2026-10-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/014-policy-source-expansion/spec.md`

## Summary

讓 `道安政策` digest 池裡「最大來源以外」的內容每週撐得過 `trigger_count`。做法分四段，順序是承重的：

1. **來源清單進 git**（`crb`，前置）：兩份 `sources_*.example.yml` 改成 prod 鏡像，交給既有的 daily 漂移檢查守。
2. **看得見每個來源掉在哪一關**：`TrafficCategory.filter()` 記下逐來源漏斗並每天印出；評估工具拿一份提案中的
   來源清單跑同一個 `filter()`，報出漏斗與會進池的標題。週報加印池內逐來源篇數。
3. **評估候選**：調整既有來源（`報導者交通`、`天下交通` 等）與新增 query，逐個過 Gate（進池且人工判讀為正題 > 0）。
4. **上線**：改 prod 變數與鏡像（同一個 PR），週驗收 routine 接手追 L1／L2 與每個來源的進池篇數。

研究結論見 [research.md](./research.md)。最關鍵的一條：「加了 ≠ 會進池」有三種形狀（被相關性檢查擋、分到事故類、
query 本身不準），所以評估要分關報數字，還要列出標題讓人判讀正題。

## Technical Context

**Language/Version**: Python 3.11（CI runner）
**Primary Dependencies**: PyYAML、feedparser（收集）、supabase-py（只讀）、Gemini embedding（評估時的向量去重會呼叫）
**Storage**: Supabase PostgreSQL。不改 schema、不改寫入語意；評估工具不寫庫（R3 的寫入保險）。
**Testing**: `python -m pytest tests/unit`（CI required check `unit`）。漏斗記帳、池來源 log、評估工具的純函數部分都可離線單元測試；
`filter()` 的接線用評估工具在真實資料上跑一次驗證（真實入口，只換邊界）。
**Target Platform**: GitHub Actions（daily buffer、週報）；評估在本機跑（需要 Supabase 讀取與 Gemini key）。
**Project Type**: 單一專案的資料管線。
**Performance Goals**: 不適用；runtime 預算見 research R5（每個來源約 1.5 秒／run）。
**Constraints**: 憲章 IV 1.3.0（PR #161）：週報 job timeout 30 分、其餘 20 分、每月 ≤ 2,000 分鐘。
**Scale/Scope**: 程式 3 處（`src/pipeline/traffic.py` 漏斗、`src/topic_scoring.py` 池來源 log、`scripts/check_config_drift.py` 鏡像清單）
＋ 1 支新腳本（`scripts/evaluate_sources.py`）＋ 2 份 example 改鏡像 ＋ prod 變數（`SOURCES_TRAFFIC_YML`，視候選而定 `CATEGORIES_TRAFFIC_YML`）。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依據憲章 2.0.0（PR #163）：IV 改名 Explicit Budgets，timeout 與預算的值在 workflow 檔與 `docs/external-services.md`。

| 原則 | 判定 | 依據 |
|---|---|---|
| **I. Pipeline Integrity** | ✅ 強化 | 漏斗 log 讓「某來源整批掉在某一關」從沉默變成每天一行；評估工具唯讀，Supabase client 在執行前換成唯讀代理，任何寫入方法一呼叫就報錯（C3-1） |
| **II. Configuration over Code** | ⚠️ 需要修文字（見下） | 加減來源仍只改設定。鏡像 example 不是 `config/sources_traffic.yml` 本身、變數仍是唯一真身，字面不衝突；但 Operations 寫改來源「不需要 PR」，鏡像加漂移檢查後實際上需要 |
| **III. Idempotency & Deduplication** | ✅ 通過 | 不改去重、不改 upsert 鍵；漏斗只是對既有 list 數 `source` |
| **IV. Free Tier Discipline** | ✅ 通過（1.3.0） | runtime 增量估計不到 1 分鐘（R5），遠低於 timeout；Gemini embedding 呼叫隨新增篇數小幅增加，FR-008 要求印出數量 |
| **V. Single Responsibility** | ✅ 通過 | 漏斗記帳在 traffic 管線自己的 `filter()`；池來源 log 放在既有 digest log 函式旁；評估工具在 `scripts/`。不新增 `src/` 模組 |
| **VI. Knowledge Base Integrity** | N/A | FFXIV 專屬，本功能只把 FFXIV 的 example 改成鏡像，不動其來源內容 |

### 原則 II／Operations 的文字修正——已由憲章 2.0.0 處理（PR #163）

鏡像加漂移檢查之後，「只改 GitHub 變數」會讓隔天的 daily 變紅，與舊 Operations「Neither sources update requires a PR」矛盾。
原本規劃在本 spec 做 PATCH 1.3.1；10-13 Luke 裁示另開 PR 把憲章改成「只寫意圖」（2.0.0），這段措辭併進去：
II 寫明有鏡像的 example 進 git、鏡像清單以 `scripts/check_config_drift.py` 為準；Operations 改成有鏡像就在 PR 同步。
本 spec 在 T007 把兩份 sources 加進清單，條文自動涵蓋。

### ⚠️ 刻意翻案：`test_only_declared_mirrors_are_checked`

`tests/unit/test_check_config_drift.py` 有一條守門員，守的正是「`sources_*` 的 example 是範本、不得列進 `MIRRORED`」，
`scripts/check_config_drift.py` 檔頭也寫著「不要順手補完」。當時的前提是 example 與 prod 不同步（33 vs 24），加進來會天天紅。
本 spec 先把 example 同步成鏡像，再改清單——前提換了，守門員要跟著改寫，而且要記下為什麼（`crb` 的決定、日期）。
**順序**：先同步 example、在本機跑漂移檢查確認綠，再改 `MIRRORED` 與測試。順序反過來，CI 會紅在一個還沒同步的檔上。

## Project Structure

### Documentation (this feature)

```text
specs/014-policy-source-expansion/
├── spec.md
├── plan.md              # 本檔
├── research.md          # R0–R7
├── data-model.md        # 漏斗、提案設定檔、評估輸出
├── quickstart.md        # 評估與上線的操作步驟
├── contracts/
│   └── source-funnel.md # 三行 log 與評估工具的介面
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks 產生
```

### Source Code (repository root)

```text
src/
├── pipeline/traffic.py      # filter()：逐來源漏斗記帳＋每日一行一來源（C1）
└── topic_scoring.py         # log_digest_pool_sources（C2）
scripts/
├── evaluate_sources.py      # 新增：提案來源清單的上線前評估（C3）
├── check_config_drift.py    # MIRRORED 加入兩份 sources；檔頭改寫
└── traffic_weekly_analysis.py  # 呼叫 log_digest_pool_sources
config/
├── sources_traffic.example.yml  # 改成 prod 鏡像（保留檔頭欄位說明）
└── sources_ffxiv.example.yml    # 同上
tests/unit/
├── test_source_funnel.py        # 新增：漏斗記帳（純函數）
├── test_digest_pool.py          # 加：池來源 log
├── test_evaluate_sources.py     # 新增：暫存 categories 合併、寫入保險
└── test_check_config_drift.py   # 改寫守門員
routines/weekly-verify/          # PROMPT (A) 改指新列；FOCUS 加追蹤名單
specs/BACKLOG.md                 # closeout：移出 GNS-008、crb；新增追 L1／L2 的列
```

**Structure Decision**：沿用既有單一專案結構。漏斗放在 `filter()` 而非評估工具，是 R3 的決定：評估只是薄包裝，
而每日 log 從此看得見每個來源掉在哪一關。

## 執行順序與檢查點

| 段 | 內容 | 檢查 |
|---|---|---|
| A | ~~憲章 PATCH 1.3.1~~ 已併入 #163（憲章 2.0.0） | #163 merge 後才開始 B |
| B | `crb`：example 同步成鏡像 → 本機漂移檢查綠 → 改 `MIRRORED` 與守門員 | `check_config_drift.py` 本機綠；改壞 example 一個值會紅 |
| C | 漏斗記帳（C1）＋池來源 log（C2）＋評估工具（C3） | 單元測試；評估工具在現行清單上跑一次，`天下交通` 的漏斗要顯示整批掉在過濾那關 |
| D | 評估候選（人工判讀標題） | 每個採用的候選：正題進池 > 0（SC-001 Gate）；runtime 估算 |
| E | 上線：改 prod 變數＋同步鏡像（同一個 PR） | `gh variable get` 解析後與鏡像相同；隔天 daily 的漏斗行出現新來源、漂移檢查綠 |
| F | closeout | Gate、SC-003 過；BACKLOG 與 routine 換手（spec「驗收時點」） |

C 段的 `filter()` 是管線模組，PR 內文要寫原則 I–III 的符合性（憲章 Governance）。

## Complexity Tracking

無違反需要辯護。原則 II 的張力用措辭 PATCH 解，不是例外。
