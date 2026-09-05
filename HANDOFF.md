# Handoff — 2026-09-05 10:05 TW

> **取樣時間就是上面那個時戳。** 只在 handoff 當下取樣，之後不會自動重新取樣——
> 所以它**會**過期，那是設計不是缺陷。**不要為了對齊現況去更新它**；下一次 handoff
> 整份取代。與 repo 不一致時，**以 repo 為準**。

**Branch:** `test/comment-budget-gate`（PR #116 開著）
**Feature:** N/A — 無進行中的 spec
**Phase:** 兩個 PR 待 merge（#115 列模型 E、#116 註解預算閘），都是 MERGEABLE

## Recently shipped

- **#108–#114**（本 session 全部 merged）：`auto_kb` 測試、死碼清理、config 漂移執行者、
  近似重複成因量測、`embed_dedup` 純化、列模型 E 決策紀錄、**pages/ 的最小 JS harness**
- 測試：Python 127 → **250**；JS 0 → **9**（`npm test`）

## Decisions

- **09-07 是 #8 的決定局**（L1 三週兩敗＝開 spec 補來源）；trigger `trig_01MBBxMaMtxxbDKXov6TTeGF`
  已探測確認上膛（09-07 07:00Z）。**#7 的 reopen 條件 2 定案量測同日順手做。**
- **列模型 ＝ E 響應式**：窄形 40px 固定色塊＋兩行標題，寬形 76×30 列尾寬幅條（無圖不輸出）。
  用 `@container trlist (min-width:560px)`，**560 是推導不是實測**。
- **JS 層有 runner 了**：`npm test`（Node 內建 `node --test` ＋ jsdom 一個依賴），
  與 Python 同在 CI 的 `unit` job（＝ruleset 指名的必要檢查）。加 `package.json` 不影響部署。
- **註解／docstring 一段上限 3 行**，超過＝該 refactor 的訊號。`LEGACY` 是**精確**棘輪
  （變壞紅、變好也紅），目前債務 **54 檔／193 區塊／最長 45 行**。
- **散文腐朽的判準是時態**：現在式／未來式會過期，過去式不會。**能寫成測試名稱的就不要再寫一遍散文**
  ——超出的內容寫進 commit／PR 內文（不可變、有日期），**不要往 BACKLOG 搬**。
- **標記詞黑名單已量測否決**：中文無詞界，「出現在」含「現在」，假陽性太高。
- **近似重複的成因是比對窗不是門檻**：1685 對 ≥0.88 並存，**96.1% 是跨週**（比對範圍外）。
- **OQ1 的假設 (a) 已結案且方向相反**：`initial_quality_score` **有**正文長度項（權重 0.3）且選材
  依它排序 → 已分析那批應該更好才對。重量落在 (b) 消耗時序。
- **#4 後半（搬模組）待裁示**：95 處引用／~15 檔，純機械搬家，理由只剩憲章 V。
- **來源組成在 repo 無紀錄**（prod 33 vs example 24；ffxiv 9 vs 4）待選修法。與 #8 直接相關。
- **模型 A/B 第三輪（3.7 vs 3.8-flash）排在 09-07 判讀之後。**

## Open Questions

1. **OQ1 剩下的一半：消耗時序** — 下一步是**控制充實天數再比一次**，不是再查算式。[未指派]
2. **`embed_dedup` 的比對窗要不要放寬** — **卡著 #7 的 reopen 條件 3**。跨週相似有兩種而餘弦
   分不出：同一則新聞的改寫（該去重）vs 同一事件的後續進展（不該去重）。[待使用者決定]
3. **註解債務怎麼還** — 54 檔不可能一個 PR，要分批；`scripts/*.py` 的模組 docstring 最重。[未指派]
4. **E 的斷點 560px 未實測**，且 **CSS 的斷點行為沒有測試涵蓋**（jsdom 無 layout）——
   那是 **#6 的第 4 個用途，也是第一個由已上線功能產生的**。[未指派]

## Resume From

Read these files first:
- `specs/BACKLOG.md` — 權威清單。先看排序表，再看 #5／#7／#8／#11 各節末
- `tests/unit/test_comment_budget.py` — `LEGACY` 就是註解債務表（還債時改那一列）
- `CLAUDE.local.md` — prod 設定流程、測試 runner（已含 JS 那列）、delegated-TDD 接線
- 列模型比較台：<https://claude.ai/code/artifact/c03d8035-ee5e-4257-b56d-12a1db0d6beb>
- 注意：`python` 不在 PATH，用 `.venv/bin/python`；JS 用 `npm test`

## Next Action

**先 merge #116 與 #115**。⚠️ **#115 一 merge 就會直接部署正式站**（`deploy-pages-traffic.yml`
監看 `pages/**`），而它的斷點行為沒有自動化驗證——merge 後在桌機與手機各開一次確認，
順便把 560 這個數字量掉。**然後等 09-07 的 #8 決定局。**

---
*Sampled at handoff 2026-09-05 — single section, overwrites prior. Not re-sampled in between.*
