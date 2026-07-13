# Internal Contracts — 低頻類別聚合式深度分析（010）

內部管線契約（無對外 API）。簽章為承諾；實作細節（prompt 內文等）可調。

## 新增函式

### `src/analyzer.py`

```python
def select_digest_pool(articles: list, category: str, digest_cfg: dict,
                       excluded_links: set) -> tuple[list, list, int]:
    """純函數。從 buffer 文章中組出某類別的 digest 池。

    Args:
      articles: get_traffic_buffer() 的完整回傳。
      category: 啟用 digest 的 major_category。
      digest_cfg: category_digest[category]（已補預設值——補齊 owner 為 pipeline_config 層：
        `_validate_pipeline_config` 驗證時顯式填入預設 10／0.18／15，呼叫端不再補；
        `_deep_merge` 不會替 per-category 子鍵補值，勿依賴）。
      excluded_links: 本週已入選一般 bucket 的文章 link 集合（FR-006）。

    Returns:
      (selected, pool_all, effective_count)
      - selected: 選材，quality 降冪至多 max_articles 篇（皆 ≥ quality_floor）。
      - pool_all: 池內全部文章（含低品質、含未選材；排除 excluded_links）——消耗用。
      - effective_count: 有效篇數（觸發判斷用；呼叫端比對 trigger_count）。

    無副作用、不打網路。觸發與否由呼叫端判斷（effective_count ≥ trigger_count）。
    """

def analyze_category_digest(pool_articles: list, topic_label: str,
                            week_start_date: str, max_articles: int) -> tuple:
    """Gemini 彙整分析。與 analyze_hot_topic 相同的回傳契約：
    (report_text, ordered_links)；失敗回 ("", [])。
    使用 DIGEST_PROMPT_TEMPLATE（多事件動態總覽），沿用 _call_gemini 與
    既有 [n] 引用慣例。呼叫端負責 2.5s delay。"""
```

### `src/storage.py`

```python
def mark_articles_analyzed(links: list) -> int:
    """將指定 link 的 articles 標記 hot_topic_analyzed=TRUE。回傳標記筆數。
    失敗時 log ERROR 並回 0（不 raise —— fail-soft，見 research D3）。
    呼叫時機：digest upsert 成功後，標記池內未入選材的殘餘文章。"""
```

## 變更函式

### `scripts/traffic_weekly_analysis.py` — `main()` 串接順序契約

```text
1. cluster → score → select_hot_topics_with_novelty → gate_ids   # 既有，行為不變
2. 排除名單 = gate_ids（未扣 digest 席次的過閘入選名單）之 bucket 成員 links
   for 每個 category_digest 啟用類別：
     select_digest_pool(articles, cat, cfg, excluded_links=排除名單)
     log: "digest[<cat>] pool=<n> effective=<m> threshold=<t> → TRIGGER|accumulate"   # FR-009，無論觸發與否
3. 席次分配：regular_ids = gate_ids[:max_hot_topics - len(triggered_digests)]
   （多 digest 超額：依 effective_count 降冪取足，落選 digest 不消耗）
4. 發布迴圈（regular + digest 同迴圈，2.5s delay）：
   digest 分支：analyze_category_digest → upsert_hot_topic_report
                → mark_articles_analyzed(池殘餘)
                → log: "digest[<cat>] consumed=<k>"
   任一步失敗 → 該 digest 本週放棄、池不消耗（不影響其他報告）
```

註（analyze I1 定案）：排除名單以**未扣席次前**的 `gate_ids` 為準——決定性、單一 pass，無「觸發↔席次↔排除」循環。代價：digest 觸發擠掉的尾名 bucket，其文章本週既不發布也不入 digest 池，留在 buffer（未標 analyzed，零損失，下週再競爭）。同週同類過閘 bucket 機率趨近零（結構天花板即本 feature 動機），此代價可接受。

## 不變式（違反即 bug）

- `category_digest` 未設定或空 → 週跑輸出與 merge 前 bit-for-bit 等價（SC-004）。
- Gemini 呼叫總數 ≤ `max_hot_topics`/週（digest 佔額內名額）。
- digest 列 `topic_token_signature == []`；`select_hot_topics_with_novelty` 的行為與輸入不因 digest 存在而改變。
- 消耗只發生在 upsert 成功之後；兩份先後 digest 的 `source_article_links` 交集為空（SC-002）。
- `select_digest_pool` 為純函數（可單測、可重放）。

## 設定鍵契約（`PIPELINE_CONFIG_YML`）

| 鍵 | 型別 | 預設 | 驗證 |
|---|---|---|---|
| `category_digest` | map | `{}`（off） | — |
| `category_digest.<cat>.trigger_count` | int | 10 | 正整數，否則 raise |
| `category_digest.<cat>.quality_floor` | float | 0.18 | ∈ [0,1]，否則 raise |
| `category_digest.<cat>.max_articles` | int | 15 | 正整數，否則 raise |

## Log 契約（FR-009／SC-005 驗收面）

| 時機 | 格式（樣式承諾，欄位順序可調） |
|---|---|
| 每個啟用類別、每次週跑 | `digest[<cat>] pool=<n> effective=<m> threshold=<t> → TRIGGER` 或 `→ accumulate` |
| 消耗完成 | `digest[<cat>] consumed=<k>` |
| 殘餘標記失敗 | ERROR 級：`digest[<cat>] 消耗標記失敗：...` |
