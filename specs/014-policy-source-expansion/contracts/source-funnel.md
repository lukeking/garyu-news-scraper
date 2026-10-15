# Contracts: 來源漏斗、池來源與評估工具

這三樣都有讀者（週驗收 routine、人工判讀），格式是契約，用測試鎖住。

## C1 每日漏斗行（`src/pipeline/traffic.py`）

每次 `filter()` 執行，每個交進來的來源一行（收集為 0 也印）：

```
[來源漏斗] <source>：收集 a → 新鮮度 b → 過濾 c → 封鎖 d → 同批去重 e → 向量去重 f → 寫入上限 g（匯流四類 h）
```

- C1-1：每個在 `raw` 裡出現過的來源都有一行；另外 `collect_sources` 嘗試過但 0 篇的來源也要有一行（由呼叫端傳入來源名單）。
- C1-2：a ≥ b ≥ c ≥ d ≥ e ≥ f ≥ g ≥ h。
- C1-3：向量去重沒跑（未設定 Supabase、或嵌入去重失敗而略過）時，`f` 照 `e` 印，並在該次 run 另有一行既有的
  `嵌入去重複失敗，略過` warning——不另印成 0，以免誤讀成「全被擋」。
- C1-4：行首 `[來源漏斗] ` 與箭頭分隔是 grep 的錨，改了要同步 routine。

## C2 週報池來源行（`src/topic_scoring.py`）

緊接在 `digest[<cat>] 最大來源：…` 之後：

```
digest[<cat>] 池來源：<source1> n1、<source2> n2、…（共 k 個來源）
```

- C2-1：依篇數降冪、同數依名稱排序（輸出穩定，兩週可比）。
- C2-2：篇數總和等於 `pool_all` 的篇數。
- C2-3：池為空時不印（與「最大來源」行相同）。

## C3 評估工具（`scripts/evaluate_sources.py`）

```
.venv/bin/python scripts/evaluate_sources.py <提案設定檔.yml>
```

- C3-1：只讀。執行前把 `src.storage._get_client` 換成唯讀代理：`table()` 回傳的查詢物件一呼叫 `upsert`／`insert`／
  `update`／`delete` 就 raise，任何寫入嘗試都讓評估以非零結束。放在 client 這層而不是逐一換寫入函式，是因為
  `storage.py` 現有 5 個寫入函式（`upsert_articles`、`upsert_traffic_buffer`、`expire_buffer_articles`、
  `mark_articles_analyzed`、`upsert_hot_topic_report`），逐一列名字會漏掉日後新增的那個。
- C3-2：收集與過濾呼叫真實的 `collect_sources()` 與 `TrafficCategory().filter()`，不重寫任何一關。
- C3-3：提案檔有 `source_defaults` 時，合併進現行 categories 檔的暫存副本，以 `CATEGORIES_TRAFFIC_YML_PATH` 指過去；
  評估結束後不改動 `config/` 下任何檔案。
- C3-4：輸出 C1 格式的逐來源漏斗、每個來源的匯流四類標題、embedding 呼叫篇數、逐來源收集耗時。
- C3-5：提案檔格式錯誤（不是 `sources:` list、或缺 `name`／`type`）時以非零結束並說明，不得靜默略過。
