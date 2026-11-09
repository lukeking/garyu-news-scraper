# Contract: 重播腳本 `scripts/replay_report_review.py`

FR-015、FR-016。拿已發布的報告跑一次審稿＋套用，只寫到本機目錄，不寫資料庫、不發布。

```text
.venv/bin/python scripts/replay_report_review.py --week 2026-11-02 --topic "道安政策 · 彙整" --out <目錄>
    [--regenerate]              用新的生成指令從同一份輸入重生成，再審重生成的那份（SC-001 的量測）
    [--exclude-anchor <id> ...] 組審稿標準時排除這些錨點（SC-002 留一測試）
    [--review-model <名稱>]     蓋過 GEMINI_REVIEW_MODEL_NAME（比較候選模型用）
```

- 輸入：先找 `hot_topic_report_reviews` 有沒有那份報告的 `input_snapshot`；沒有（018 上線前發布的都沒有），就用 `source_article_links`
  從 `articles` 唯讀查回各篇，照當時的規則重建清單，輸出標 `"input": "reconstructed"`（FR-016）。
- 輸出：`<目錄>/<週次>-<報告 id>.json`（原稿、輸入、發現、套用結果、狀態、各項檢查、token 與秒數）與同名 `.md`（修前修後並排，給人看）。
  `<報告 id>` 是 `hot_topic_reports.id`：主題標籤是中文、檔名不轉拼音，主題標籤寫在 JSON 的 `topic` 與 `.md` 開頭。
- 資料庫只讀：腳本不 import 任何寫入函式。單元測試斷言它的模組沒有引用 `upsert_*`。
- 會呼叫真的 API、照 prod key 計費。每次開始時印一行估算費用，結束時印實際 token 數。T015 讓 `_call_gemini` 交出 usage 之前，
  結束時印一行「token 數：未取得」並寫明原因（spec Clarifications 2026-11-08）。
- 結束碼：0＝跑完（不管審出什麼）；1＝找不到報告、重建失敗或呼叫失敗，印出原因。
