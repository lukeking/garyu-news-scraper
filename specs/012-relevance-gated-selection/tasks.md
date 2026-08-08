---
description: "Task list for feature 012 相關性選材閘（Relevance-Gated Selection）"
---

# Tasks: 相關性選材閘（Relevance-Gated Selection）

**Input**: Design documents from `specs/012-relevance-gated-selection/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: INCLUDED — quickstart.md §4 specifies the required unit suite and the repo runs TDD
(delegated-TDD gate). Test tasks are written FIRST and must FAIL before implementation.

**Task markers are three-state** (delegated-TDD wiring): `[ ]` not started → `[-]` implemented,
awaiting review → `[X]` reviewed **and** main-verified. Never write `[X]` in the implementation commit.

> Markers: `[ ]` not started · `[-]` implemented, awaiting review · `[X]` reviewed + verified · `[~]` dropped

**Organization**: grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: different files, no dependency on an incomplete task → parallelizable
- **[Story]**: US1 / US2 (setup/foundational/polish carry no story label)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: put the new config structure in place (no rules yet)

- [X] T001 [P] Add a documented, empty `relevance_rules:` block (with a comment explaining
  `require_any` / `exclude_any`, per-category, fail-open) to `config/categories_traffic.yml`
  AND `config/categories_traffic.example.yml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: config loader the gate wiring depends on

**⚠️ Blocks the wiring task in every user story.**

- [X] T002 Add `load_relevance_rules()` to `src/pipeline_config.py` — read `relevance_rules`
  from `categories_traffic.yml`, return `{}` when the key is absent or malformed (fail-open,
  see data-model §1); mirror the shape of the existing `load_source_default_categories()`

**Checkpoint**: loader available → user-story work can begin.

---

## Phase 3: User Story 1 - 機車事故熱點只出現真正事故／道安內容 (Priority: P1) 🎯 MVP

**Goal**: crime／social-news pieces (竊盜、毒駕羈押…) that merely contain a `機車` token are
excluded from the 機車事故 hot-topic selection; relevance beats the title-form quality score.

**Independent Test**: feed a 機車事故 bucket mixing real accidents and crime stories → crime
excluded, accidents kept; a high-quality-score crime story does NOT outrank a plain accident story.

### Tests for User Story 1 ⚠️ (write first, must FAIL)

- [X] T003 [P] [US1] Write failing unit tests in `tests/unit/test_relevance_gate.py`
  （**substring `_hit` + whitelist-dominant**，2026-08-06 定，見 data-model §1）:
  (a) `require_any` pass — 真事故（擦撞送醫不治／自撞1死2傷）kept；
  (b) no-accident-token block — 純竊盜（涉竊機車遭通緝）／毒駕羈押（無撞死傷）excluded（靠 `require`=False，非 exclude）；
  (c) **boundary — 肇事逃逸／毒駕撞死（刑案∩事故）kept**（require 命中即 on-topic，回歸重災區）；
  (d) **whitelist-dominant** — 規則同時給 require＋exclude 且文章命中兩者 → kept（exclude 不生效）；
  (e) **exclude-only 純黑名單支** — 只給 `exclude_any` 的規則：命中即 excluded，未命中即 kept；
  (f) fail-open — 缺鍵／格式錯／非 list 的規則 → 該類別不套閘、不誤殺整類；
  (g) purity — 閘不呼叫外部服務、不改 `major_category`；
  (h) **C2 高分離題仍被擋** — 一則離題（毒駕羈押、無事故 token）即使 `initial_quality_score` 高，
      仍落 off_topic（相關性早於分數）

### Implementation for User Story 1

- [X] T004 [US1] Implement pure `is_topic_relevant(article, rule)` + `partition_by_relevance(articles, rules)`
  in `src/filter.py` — **substring `_hit(title, tokens)`**（`tok.lower() in _clean_html(title).lower()`，
  非 `normalise_title` token 交集，見 data-model §1 replay 佐證）；**whitelist-dominant**：
  `require_any` 存在時 `on = _hit(require_any)`，`exclude_any` 只在無 `require_any` 時走純黑名單支；
  回傳 (on_topic, off_topic)，每篇附 `_relevance_reason`（log 用）。Makes T003 pass.
- [X] T005 [P] [US1] Seed `relevance_rules.機車事故.require_any`（撞／追撞／自撞／擦撞／車禍／
  事故／肇事／送醫／不治／傷／亡／翻車／失控／死）in `config/categories_traffic.yml` +
  `config/categories_traffic.example.yml`（**require-only**；exclude_any 對本類別不生效故不填，
  市場詞由 T008 Tier 1 攔；**seed，非定案**，Phase 5 對基準集調）
- [X] T006 [US1] Wire `partition_by_relevance` into `scripts/traffic_weekly_analysis.py` immediately
  before `cluster_traffic_articles` — off_topic 排除於 scoring/selection，逐篇 log reason。
  依賴 T002（loader）、T004（函數）
- [X] T006a [US1] **FR-008 regression**：對一份 fixture 走已接線的每週路徑
  （`partition_by_relevance` → `cluster_traffic_articles` → `score_topic_buckets` →
  `select_hot_topics_with_novelty`），assert 既有行為不變——**≤3 席上限維持**、novelty 閘對未被
  gate 動到的桶**仍照常 suppress/pass**、gate **不改** `major_category`（FR-008）。
  In `tests/unit/test_weekly_selection.py`。依賴 T004、T006（測整合路徑，故在 wiring 之後）

**Checkpoint**: US1 fully functional — crime excluded, relevance > quality score, **既有選材管線
（novelty／≤3 席／分類）經 T006a 證實不受破壞（FR-008）**. **This is the MVP.**

---

## Phase 4: User Story 2 - 系統性離題來源不得整席佔據一個熱點 (Priority: P2)

**Goal**: 車媒行銷稿（油耗／市佔／銷量戰報…）不得填滿某熱點的整個發布名單；整桶離題 → 不發布
（FR-003）；但車媒的真實事故報導不被連坐（FR-007）。**Depends on US1's gate as the shared machinery.**

**Independent Test**: 金線式全行銷桶 → 不發布；一則來自車媒但含事故 token 的真事故 → 保留。

### Tests for User Story 2 ⚠️ (write first, must FAIL)

- [X] T007 [P] [US2] Add failing unit tests in `tests/unit/test_relevance_gate.py`:
  (a) whole-bucket all-off-topic → `partition_by_relevance` yields empty on_topic → 該類別不成桶
  （feed → partition → `cluster_traffic_articles` → assert no bucket），FR-003；
  (b) **FR-007** — 車媒來源＋事故 token 的文章 survives（來源不參與判定，只看內容 token）

### Implementation for User Story 2

- [X] T008 [P] [US2] Tier 1（config-only）：extend `blocked_content_keywords` with market tokens
  （油耗／市佔／市占／銷量／戰報／掛牌數）in `config/pipeline_config.yml` +
  `config/pipeline_config.example.yml`（既有 filter 機制，`src/pipeline/traffic.py:66`）
- [~] T009 [US2] **DROPPED（2026-08-06）** — 原案「把市場詞加入 `relevance_rules.機車事故.exclude_any`
  作 backstop」在 **whitelist-dominant** 語意下是**死配置**：機車事故 有 `require_any`，`exclude_any`
  對它恆不生效（見 data-model §1）。市場行銷稿本就因**無事故 token**（`require`=False）被 T004 擋下，
  無事故 token 的漏網由 T008（Tier 1 `blocked_content_keywords`，filter 階段）攔。故本任務取消，不新增死配置。

**Checkpoint**: US1 + US2 both independently testable — all-marketing slate not published, genuine
car-media accident survives.

---

## Phase 5: Polish & Cross-Cutting — SC 量測與上線

**Purpose**: 量 SC 階梯、對基準集調規則、上 prod。**沒有基準集就只有主觀印象，不算達標（承 011 之戒）。**

- [ ] T010 Build the human-labeled relevance baseline at `tests/fixtures/relevance_baseline_012.jsonl`
  — 取樣數週（含 08-03 `機車事故·中時` 刑案混雜、`機車事故·金線` 行銷整席兩錨案）；逐篇人工標
  `on`/`off`（data-model §4 欄位）；去識別化（title／source／label）。**禁止用閘輸出回填 label。**
  **骨架已由 T011 `--emit-labels` 產出（87 列、label 全空，涵蓋 16 個 `機車事故 ·` 桶、
  2026-05-18→08-03；兩錨案都在內）；本任務剩下的就是逐列填 label。**
  ⚠️ 順序：T011 先跑，因為要先知道「前閘 ∪ 後閘」名單才知道要標哪些（見 T011 的 promotion 限制）。
- [-] T011 [P] Add read-only `scripts/measure_relevance.py` — 對基準集重播「套閘前 vs 套閘後」發布名單，
  輸出 SC 階梯：SC-001（任一熱點多數離題？）／SC-002（≤20%？）／SC-004（on-topic 數不降？）
  **重播是精確的而非估計**：發布名單不是 LLM 選的，`analyze_hot_topic()` 取
  `sorted(bucket, initial_quality_score desc)[:10]`，純函數、可重算。三個已載明的限制：
  (a) 桶 >10 篇時補位者不可知（歷史 pool 無法還原——`articles` 只有 `hot_topic_analyzed` 布林值、
  無消耗時間戳；重建已嘗試並被不變式證偽：08-03 中時 候選桶 n=107 vs 28、score 187.5 vs 24.69）；
  (b) novelty／≤3 席的跨桶效應未建模；(c) `initial_quality_score` 會被 og 充實事後改寫
  （實測漂移 4.9%），故貼近 `min_threshold` 的發布判定印為「未定」。內建 `replay 保真度` 自檢
  （現況 11/12 個精確名單重算出報告紀錄的 `cumulative_score`）。
  驗證＝重播實跑＋保真度自檢，**無 unit RED**（tasks.md Lane C：measurement 不走 unit RED）。
- [ ] T012 Tune the token tables in `config/categories_traffic.yml` (+example) and
  `config/pipeline_config.yml` (+example) **against the baseline** until an SC rung is reached；
  record the achieved rung（SC-001 Gate 最低；目標 SC-002）。依賴 T010、T011
- [ ] T013 [P] Deploy config to prod GitHub env vars（`CATEGORIES_TRAFFIC_YML`／`PIPELINE_CONFIG_YML`）
  per `CLAUDE.local.md` — **使用者執行**（`gh variable set` 交給使用者），完成後 `gh variable get` 逐位元組比對。
  **payload 額外夾帶一項（使用者 2026-08-08 決定，與 012 無關）**：`buffer.daily_enrich: true`。
  行為上是 no-op（`scripts/traffic_buffer.py:53` 是 `.get("daily_enrich", True)`，預設開啟），
  目的是讓那個 kill-switch 在 prod 設定裡**看得見**——403 封鎖擴散到原生媒體時才需要它，
  屆時得先知道它存在。本機 `config/pipeline_config.yml`（＝部署 payload）已加。
  ⚠️ **尾端換行陷阱（已量測）**：prod 現存的值**沒有**尾端換行，`gh variable get` 自己會補一個 `\n`；
  本機檔以 `\r\n` 結尾。所以 `set < 檔案` 之後逐位元組比對會多出一個換行，那是假警報——
  用 YAML parse 後比物件（或容忍尾端單一 LF），不要看 byte 數。檔案是 CRLF，維持 CRLF。
- [ ] T014 Update spec.md Success Criteria with the achieved SC rung (E1 實測值)，並執行 quickstart.md 驗收流程
- [ ] T015 On merge (spec-closeout ritual): flip `specs/BACKLOG.md`「機車事故選材離題」→ done（PR ref），
  更新 `STATE.md`；#7 仍保留為獨立後續

---

## Dependencies & Execution Order

### Phase dependencies
- **Setup (P1: T001)** → no deps.
- **Foundational (P2: T002)** → after Setup; **blocks T006**.
- **US1 (P3)** → after Foundational. **MVP.**
- **US2 (P4)** → depends on US1's gate（T004）being present（shared machinery）；T008 (Tier 1 config) is
  independently shippable without the gate.
- **Polish (P5)** → after US1（+US2 if included）；T012 depends on T010+T011.

### Within US1
- T003（tests, RED）→ T004（impl, GREEN）→ T006（wire）→ T006a（FR-008 整合回歸，需 wiring 存在）.
  T005 [P] with T003（different file）.

### Parallel opportunities
- T001 [P] (config skeleton) alone in Setup.
- US1: T003 [P] ∥ T005 [P]（test file vs config file）; T004 after T003.
- US2: T007 [P]（tests）∥ T008 [P]（pipeline_config）; T009 extends T005's file.
- Polish: T011 [P], T013 [P] independent.

### Delegated-TDD lanes (for /speckit-implement)
- **Lane A — pure gate** (`src/filter.py` + `tests/unit/test_relevance_gate.py`): file-disjoint,
  has a `tests/unit` runner, real RED/GREEN → **TDD-able, likely a delegated rung**. This is US1 T003/T004
  and US2 T007. The FR-008 integration regression (T006a, `tests/unit/test_weekly_selection.py`) is also
  Lane A but runs **after** wiring (T006), not RED-first.
- **Lane B — config seeds** (`config/*.yml` + `.example`): no test runner of its own; verified through
  Lane A's tests and Phase 5 measurement → inline, degraded verification (say so).
- **Lane C — wiring** (`scripts/traffic_weekly_analysis.py`) and **measurement** (`scripts/measure_relevance.py`):
  integration glue; verified via measurement replay, not unit RED.
- Announce the gate rung at `/speckit-implement` per `~/.claude/rules/delegated-tdd-gate.md`.

---

## Implementation Strategy

### MVP (US1 only)
1. Setup (T001) → Foundational (T002) → US1 (T003–T006a).
2. **STOP & VALIDATE**: crime excluded, accidents kept, relevance > quality score, 既有管線不破（T006a）.
3. Measurable win: 中時 刑案混雜 cleaned; 金線 整席 also likely emptied by the gate even before Tier 1.

### Incremental
- +US2 (T007–T009): market tokens + whole-slate FR-003 + FR-007 survival.
- +Polish (T010–T015): baseline → measure → tune to SC rung → prod → closeout.

## Notes
- Zero AI / zero new deps / **zero DB schema change** throughout (FR-006, data-model invariants).
- Config changes MUST sync `*.example.yml`（憲章 II：example 是唯一進 git 的副本）。
- Commit after each task or logical group; `[-]` on the implementation commit, `[X]` only after review + main-verify.
