# Implementation Plan: FFXIV 週報取樣修正

**Branch**: `015-ffxiv-sampling-fix` | **Date**: 2026-10-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/015-ffxiv-sampling-fix/spec.md`

## Summary

讓 FFXIV 週報的 20 篇不再全是 Reddit。做法分五段，前三段是程式、後兩段是上線：

1. **論壇項目改以回覆為單位**：新的 `vb_forum` 來源型別讀依最後回覆排序的 RSS，對窗口內有回覆的串去討論串頁面往前翻，
   收窗口內的回覆合成一篇（上限：3 頁、20 則、6,000 字）。窗口是固定的週邊界（R1），每週的 `link` 帶最新回覆 id，
   `freshness_filter` 對它略過標題指紋（R5）。
2. **純權重排序**：權重寫在每個來源上，去重前就排序（R0 的順序陷阱、R4）；log 印出候選池與入選的逐來源篇數（FR-010）。
3. **Lodestone 與「0 項出聲」**：html_patch 加發布時間、排除標題前綴、詳細頁內文三個選用設定（R6）；
   html_patch、html_forum、PTT 共用「回 200 但解析出 0 項」的判斷（R9）。
4. **上線**：程式先 merge（對舊設定向下相容），再改 prod 變數 `SOURCES_FFXIV_YML` 與它的鏡像 example。
5. **追蹤**：週驗收 routine 的 `FOCUS.md` 加 SC-001 與候選供應（SC-006）；約一週後依供應決定輸出形式（`3cq` 的新觸發點）。

研究結論見 [research.md](./research.md)。最關鍵的兩條：論壇頁面的時間是日本時間、最近兩天寫成相對時間（R2）；
537 的 0 是最近沒人發文，RSS 會吐出 PLL 的新串（R7）。

## Technical Context

**Language/Version**: Python 3.11（CI runner）
**Primary Dependencies**: requests、feedparser、BeautifulSoup（lxml）——都是既有依賴，不新增
**Storage**: Supabase PostgreSQL。不改 schema；FFXIV 仍以 `link` 為鍵 upsert，論壇項目的 `link` 每週不同（R5）。
**Testing**: `python -m pytest tests/unit`（CI required check `unit`）。頁面解析用存在 `tests/fixtures/` 的 HTML 片段離線測；
接線用真實入口（`FFXIVCategory().collect()` 與 `.filter()`）在本機跑一次，只換邊界、不寫庫（quickstart）。
**Target Platform**: GitHub Actions 週報（`weekly.yml`，每週一 00:00 UTC，`timeout-minutes: 30`）
**Project Type**: 單一專案的資料管線
**Performance Goals**: 不適用；runtime 增量估在 1 分鐘內（下方 Constraints）
**Constraints**: 憲章 IV——請求間隔 1 秒（既有 `collect_sources` 與新加的分頁請求都照這個）；週報 30 分 timeout，
10-19 是 10m15s。新增請求估計：論壇約 6～15 串 × 最多 3 頁 ＋ Lodestone 詳細頁 1～2 個，約 20～50 個請求、1 分鐘內（推論）。
**Scale/Scope**: 程式 3 個檔（`src/collector.py`、`src/filter.py`、`src/pipeline/ffxiv.py`）＋ 單元測試 ＋ fixtures；
設定 1 份鏡像（`config/sources_ffxiv.example.yml`）＋ prod 變數 `SOURCES_FFXIV_YML`；routine 的 `FOCUS.md`；BACKLOG closeout。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依據憲章 2.1.0。

| 原則 | 判定 | 依據 |
|---|---|---|
| **I. Pipeline Integrity** | ✅ 強化 | 「回 200 但解析出 0 項」從 INFO 變成來源失敗；討論串與 Lodestone 詳細頁的每一種退回各印一句原因；截斷警告。都不中止管線，與現行來源失敗的處理一致 |
| **II. Configuration over Code** | ✅ 通過 | 新型別 `vb_forum` 與 html_patch 的新選項是一次性的程式能力；之後增減論壇版、改權重與上限都只改 `SOURCES_FFXIV_YML`。鏡像 example 同一個 PR 更新，漂移檢查守 |
| **III. Idempotency & Deduplication** | ✅ 通過 | 固定週窗口：同一週重跑得到同一組回覆、同一個 `link`，upsert 覆寫同一列（R1）。去重仍在 `src/filter.py`：論壇項目略過標題指紋、改以 `dedup_key` 辨識，判斷寫在 `freshness_filter` |
| **IV. Explicit Budgets** | ✅ 通過 | robots.txt 兩個主機都 404（R8）；新請求間隔 1 秒；回覆數、頁數、字數上限都寫在設定；Gemini 篇數上限 20 不變，輸入變長的成本增量是分的量級（R3），上線後報數字（SC-005） |
| **V. Single Responsibility** | ✅ 通過 | 收集在 `collector.py`、排序與去重在 `filter.py`、FFXIV 的串接在 `pipeline/ffxiv.py`。不新增 `src/` 模組，也不在本 spec 做 `src/scrapers/ffxiv/` 的拆分（憲章要求那必須一次完整搬遷） |
| **VI. Knowledge Base Integrity** | ✅ 不受影響 | 分析流程不動，KB 照舊在分析前載入 |

**Post-design re-check（Phase 1 之後）**：仍全數通過。新增的 `source_weight`、`dedup_key` 是文章 dict 的記憶體欄位，
不進 schema；`summary` 變長只影響已存在的欄位內容。

## Project Structure

### Documentation (this feature)

```text
specs/015-ffxiv-sampling-fix/
├── spec.md
├── plan.md              # 本檔
├── research.md          # R0–R10
├── data-model.md        # 來源設定、論壇項目、文章欄位
├── quickstart.md        # 本機驗證與上線步驟
├── contracts/
│   ├── sources-ffxiv-config.md   # vb_forum 與 html_patch 新選項、weight
│   └── log-lines.md              # 新增與改動的 log 行（週驗收 routine 會讀）
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks 產生
```

### Source Code (repository root)

```text
src/
├── collector.py         # vb_forum 型別（RSS → 討論串分頁 → 窗口內回覆）；html_patch 新選項；
│                        # 共用的「解析出 0 項」判斷（html_patch／html_forum／PTT）；weight 蓋到文章上
├── filter.py            # FFXIV 排序鍵（權重 → 時間）；game_deduplicate 依排序鍵取前 20、印候選池與入選；
│                        # freshness_filter 對帶 dedup_key 的項目略過標題指紋
└── pipeline/ffxiv.py    # 去重前先依排序鍵排序

tests/
├── fixtures/ffxiv/      # 討論串頁面（含 Today／Yesterday／絕對日期）、Lodestone 列表與詳細頁的 HTML 片段
└── unit/                # 新測試：見 tasks

config/sources_ffxiv.example.yml   # 鏡像：五個版改 vb_forum、Lodestone 改 category/3 與新選項、每個來源加 weight
routines/weekly-verify/FOCUS.md    # 上線後加 SC-001 與候選供應的檢查
```

**Structure Decision**: 沿用既有單一專案結構，改動集中在三個既有模組。

## 上線順序（承重）

1. **程式先 merge，設定後改**。新程式對舊設定向下相容：沒有 `weight` 的來源當 0（並印警告）、排序退化成依時間（等同現狀）；
   舊的 `type: rss` 五個版照舊。反過來先改設定，舊程式不認得 `vb_forum`，五個版會被當成未知型別略過。
2. **改 prod 變數**：`gh variable set SOURCES_FFXIV_YML --env production < config/sources_ffxiv.yml`，`gh variable get` 逐位元組比對；
   同一天把鏡像 example 改成一樣（同一個 PR 或緊接的 PR），漂移檢查才不會紅。不要選在週一 00:00 UTC 前後。
3. **SC-004 的實測要在改 Lodestone 設定之前**：程式 merge 後、prod 變數改之前，用現行設定（錯的 selector）在本機跑一次收集，
   `來源失敗` 名單要有 Lodestone。
4. **第一次週報**：10-26（若在那之前上線）。讀 log：候選池與入選的逐來源篇數、Lodestone 解析／收進、各串的回覆數與退回原因。

## Complexity Tracking

無違反，不需要。

## 實作中看到、刻意不做的

- **`src/scrapers/ffxiv/` 的拆分**：`collector.py` 加上 `vb_forum` 之後會再長約一百多行。憲章 V 允許拆，但要求一次完整搬遷；
  不在本 spec 做，closeout 時提出建議。
- **traffic 的 `source_weights`**：名稱鍵、可信度語意，與 FFXIV 的排序權重不同，不合併（R4）。
