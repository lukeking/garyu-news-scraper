# Sign-off: accepted spec-wide gaps

spec-reviewer 對 `7191557` 的矩陣（2026-11-08，結果與 main 的重跑記在 PR 內文）。之後再跑 spec-reviewer 時，這幾列照抄進範本的 `{{ACCEPTED}}`。

| id | 類型 | 由哪個手臂負責 | 接受 | 依據 |
|---|---|---|---|---|
| `experiments/model-quality-2p5pro-vs-3p6flash/scripts/model_ab.py:main -> analyze_hot_topic` | UNCOVERED | 不補：凍結的模型評比紀錄，不在 prod 路徑；下一輪評比照 BACKLOG `GNS-20261019-1vk` 重驗 | Luke 2026-11-08 | PR `#202` 內文 |
| `experiments/model-quality-2p5pro-vs-3p6flash/scripts/quality_ab.py -> analyze_hot_topic` | UNCOVERED | 不補：同上 | Luke 2026-11-08 | PR `#202` 內文 |
| `experiments/model-quality-3p6flash-vs-3p7flash/scripts/quality_ab.py -> analyze_hot_topic` | UNCOVERED | 不補：同上 | Luke 2026-11-08 | PR `#202` 內文 |
| `experiments/model-quality-3p8flash-vs-argon/scripts/quality_ab.py -> analyze_hot_topic` | UNCOVERED | 不補：同上；腳本開頭寫的「`770ed2a` 的位元組相同指令」已不成立，是那次評比當時的紀錄 | Luke 2026-11-08 | PR `#202` 內文 |
| `tests/integration/test_weekly_analysis.py -> analyze_hot_topic` | UNCOVERED | 不補：要本機 Supabase、CI 不跑；週報 `main()` 的兩條邊由 `tests/unit/test_weekly_report_links.py` 咬到。tuple 沒解開那個 018 之前就有的錯另由 T052 修 | Luke 2026-11-08 | PR `#202` 內文 |
| `tests/integration/test_digest_weekly.py -> analyze_category_digest` | UNCOVERED | 不補：要本機 Supabase、CI 不跑；它把兩個 analyzer 都 patch 掉 | Luke 2026-11-08 | PR `#202` 內文 |
