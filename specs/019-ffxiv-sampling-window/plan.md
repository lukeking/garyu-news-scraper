# Implementation Plan: FFXIV 週報來源調整（拿掉 Reddit 與論壇列表頁、加收英文官方論壇）

**Branch**: `019-ffxiv-sampling-window` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/019-ffxiv-sampling-window/spec.md`

## Summary

FFXIV 週報拿掉 Reddit（robots.txt `Disallow: /`，內容只有收集前 8 小時的開串）與論壇列表頁（只有標題、三週 0 篇入選），
改加收英文官方論壇裡對應日文五個版的版，沿用 015 的 `vb_forum` 收集（依最後回覆排序、窗口內回覆合成一篇），權重與日文版同級。
分析篇數上限從程式裡的 20 搬到 `PIPELINE_CONFIG_YML`，新值等英文版的供給量到後由 Luke 核定。英文版的子版 id、時間格式與時區、每週供給還沒查到
（11-09 論壇對本機連續 429），是第一個 spike。

## Technical Context

**Language/Version**: Python 3.12（本機 `.venv` 綁 `/usr/bin/python3.12`；Actions 依 `weekly.yml`）  
**Primary Dependencies**: requests、BeautifulSoup（lxml）、feedparser（皆已在用）；不新增依賴  
**Storage**: 不變（Supabase `articles`；`ffxiv-pool` artifact）  
**Testing**: `pytest tests/unit`（CI 的 `unit` job）；註解閘 `tests/unit/test_comment_budget.py`（本機 pre-commit）  
**Target Platform**: GitHub Actions `weekly.yml`（`ubuntu-latest`，`timeout-minutes: 30`）；本機 WSL 只做開發與量測  
**Project Type**: 排程資料管線（Collect → Filter → Analyze → Store → Publish）  
**Performance Goals**: 週報 ≤ 20 分鐘（SC-005 L1）；FFXIV 每篇分析約 15～18 秒  
**Constraints**: 論壇限速（11-09 本機 10 次就 429）；30 分鐘逾時；Gemini 預算 NT$300／月（`docs/external-services.md`）  
**Scale/Scope**: FFXIV 來源從 9 項（含停用 1）變成 12 項（日文 5、英文 5、Lodestone、停用的 TW 修正說明）；每週候選約 7～11 篇＋英文版（未量）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*（依 `.specify/memory/constitution.md` 2.1.1 逐條）

| 原則 | 判定 | 依據 |
|---|---|---|
| I. Pipeline Integrity | ✅ | 階段順序不變；英文版走既有 `vb_forum`，失敗照 015 進 `來源失敗`；上限截掉論壇串時印一行（FR-003），不沉默 |
| II. Configuration over Code | ✅ | 加英文版、移除 Reddit 與列表頁只改 `SOURCES_FFXIV_YML`（＋example 鏡像，drift check 管）；上限從程式搬進 `PIPELINE_CONFIG_YML`，更符合本條。若 R4 要求時區可設定，是設定欄位，不是寫死 |
| III. Idempotency & Deduplication | ✅ | 去重仍在 `src/filter.py`；英文串沿用以回覆為單位的跨週邏輯（015 R5） |
| IV. Explicit Budgets | ✅（帶條件） | Gemini 呼叫上界改由設定的上限決定，改值時同步 `docs/external-services.md`（FR-003）；論壇是同一個主機，robots.txt 015 R8 查過（302→404，無限制）；請求間隔沿用 1 秒，第一、二週看 429（research R7）；`timeout-minutes: 30` 不變。Reddit 因 robots.txt `Disallow: /` 移除，正是本條的要求 |
| V. Single Responsibility | ✅ | 改動落在 `src/collector.py`（只在 R4 要求時：時區）與 `src/filter.py`（上限）；沒有新的跨模組依賴 |
| VI. Knowledge Base Integrity | ✅（觀察） | 分析 prompt 與 KB 不變；英文內容會帶進新的英文術語，auto-kb 的未知術語可能變多——那是 `GNS-20261026-fwz` 正在追的事，SC-005 記錄時一併看 |
| Operations & Deployment | ✅ | 來源改動照「edit `SOURCES_FFXIV_YML` → mirror PR」；上線後以排程週報（或手動 dispatch 成功）確認 |
| Compliance review | 要做 | 動到 `src/collector.py`、`src/filter.py` 的 PR 內文要寫 I–III 的符合說明 |

## Project Structure

### Documentation (this feature)

```text
specs/019-ffxiv-sampling-window/
├── spec.md
├── plan.md              # 本檔
├── research.md          # R0–R8（R3–R5 待 spike）
├── data-model.md
├── quickstart.md
├── contracts/
│   └── config-and-logs.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/
├── collector.py         # vb_forum：英文版若時區不同，_parse_vb_time 的時區改由來源設定（R4 決定要不要動）
├── filter.py            # game_deduplicate：上限讀設定、截掉論壇串時印一行
└── pipeline/ffxiv.py    # 不動（max_articles 有沒有用到，讀一次，結果寫回 docs/external-services.md）
config/
├── sources_ffxiv.example.yml    # 鏡像：加英文 5 版、刪 Reddit 與列表頁
└── pipeline_config.example.yml  # 鏡像：加上限的鍵
docs/external-services.md        # Gemini 那一列：每次篇數改指向新的鍵
tests/unit/
├── test_game_deduplicate.py     # 上限讀設定、截掉時印 log
├── test_ffxiv_ranking.py        # 「PLL 優先」照舊綠（SC-004）
└── test_vb_forum_parse.py       # 英文時間解析（R4 的實測格式，SC-003）
```

**Structure Decision**: 單一 repo、既有模組；不新增模組。

## Phases

- **Spike（R3–R5、R8 的未驗部分）**：英文子版 id、時間格式與時區、每週供給。論壇對本機限速，請求之間至少隔 30 秒、429 就停；查不到就請 Luke 用瀏覽器看版頁。
  結果寫回 research，並決定上限的提議值（R6）。
- **實作**：上限搬進設定（缺鍵 20，行為不變）＋截掉時的 log；英文時間解析（只有 R4 要求時）。
- **設定**：prod `SOURCES_FFXIV_YML`、`PIPELINE_CONFIG_YML` 的變更與鏡像同步（Luke 核定上限值之後）。
- **上線後**：第一、二週讀 log 與 `ffxiv-pool`，記 SC-001～SC-005；merge 後第一次 prod 讀回是 spec 裡的一個 task（018 T053 的做法）。

## Complexity Tracking

沒有違規需要記。
