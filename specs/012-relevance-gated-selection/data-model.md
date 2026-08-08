# Phase 1 Data Model: 相關性選材閘

**無資料庫 schema 變更。** 不新增 `articles`/buffer 欄位、不動 migration。以下「實體」多為
**config 結構**與**記憶體中的中間值**，唯一落地的檔案是 config YAML 與（測試用）標記基準集。

---

## 1. Per-Category Relevance Rule（config，新增）

住 `config/categories_traffic.yml`，與既有 `categories:` / `source_defaults:` 並列。
per-category，只需為會離題的類別填（先填 `機車事故`）。

```yaml
# 相關性閘規則（feature 012）。key = major_category；缺 key 的類別 = 不套閘（全通過）。
relevance_rules:
  機車事故:
    require_any:            # 正面事故 token 白名單：命中任一才算 on-topic（本類別的整道閘）
      [撞, 追撞, 自撞, 擦撞, 車禍, 事故, 肇事, 送醫, 不治, 傷, 亡, 翻車, 失控, 死]
    # exclude_any 對「有 require_any 的類別」不生效（見下 whitelist-dominant），故 機車事故
    # 不填；市場／行銷噪音由 §2 的 blocked_content_keywords（filter 階段，Tier 1）攔。
```

**判定語意（whitelist-dominant；2026-08-06 定，取代原 AND-NOT 公式）**：
```
_hit(title, tokens) = any(tok.lower() in _clean_html(title).lower() for tok in tokens)   # 子字串比對

on_topic(article, rule) :=
    if require_any 存在:  _hit(title, require_any)          # 白名單主導：必須命中事故 token
    elif exclude_any 存在: not _hit(title, exclude_any)     # 純黑名單（無 require 的類別才走這支）
    else:                 True                              # 無規則 → 全通過
```
- **為何改掉原公式**：原 `hit(require) AND NOT(hit(exclude) AND NOT hit(require))` 代數化簡即等於
  `hit(require)`——exclude 在 require 存在時**恆不生效**（degenerate）。且「require 優先解邊界」與
  「兩名單都生效」數學上不相容：一旦 require 贏邊界，某一名單必然主導。**選 require 主導**
  （事故桶必須自證是事故，寧缺勿濫）。
- **為何用子字串不用 jieba token**：`normalise_title` 丟棄長度 <2 的 token 且 jieba 會把
  「撞死」「涉竊」「醫不治」黏成一詞——實測（2026-08-06 replay）token 交集會**誤殺真事故**
  （擦撞送醫不治→∅）並**漏抓刑案**（涉竊/通緝→∅）。子字串比對（與既有 `blocked_content_keywords`
  同法）逐案正確。過度命中風險（撞∈撞球）小且由 §4 基準集調校。
- 「肇事逃逸」：命中 `肇事`（require）→ on-topic，即使另含刑案性質。**邊界由 require 命中解掉。**
- 純竊盜：無事故 token → `_hit(require)=False` → off-topic（**不靠 exclude**）。
- 市場行銷稿（油耗/市佔/銷量，無事故 token）：同理 → off-topic。
- **欄位皆選填**：只給 `require_any` = 白名單（本 seed）；只給 `exclude_any` = 純黑名單（未來
  無法列舉正面 token 的類別用）；兩者都給 = require 主導、exclude 不生效（故不建議兩者都給）。

**驗證規則**：規則載入失敗（缺鍵／格式錯／非 list）時該類別**視為不套閘**（fail-open，寧可漏擋
不可誤殺整類），並記 log。token 為任意子字串，不受 jieba 切詞限制。

## 2. `blocked_content_keywords` 擴充（config，既有欄位）

住 `config/pipeline_config.yml`（既有）。Tier 1 只是**新增詞**，欄位與消費點皆已存在
（`src/pipeline/traffic.py:66`，filter 階段標題子字串比對）。

```yaml
blocked_content_keywords:
  # …既有（售價/試駕/銷售排行/車展/優惠…）…
  - 油耗        # ← 08-03 金線案缺的市場詞（feature 012 Tier 1）
  - 市佔
  - 市占
  - 銷量
  - 戰報
  - 掛牌數
```
注意此為**全域 filter 封鎖**（該文從所有類別的 buffer 消失），故只放**確定是行銷噪音**的市場詞；
語意較模糊的離題留給 §1 的 per-category 閘（只影響該類別選材，不丟 buffer）。

## 3. Relevance Partition（記憶體中間值，不落地）

每週選材期，閘對候選集產出的分割——純函數回傳，不寫 DB：

| 欄 | 型別 | 說明 |
|---|---|---|
| `on_topic` | list[article] | 通過閘 → 進 `cluster_traffic_articles` |
| `off_topic` | list[article] | 未通過 → 排除於計分/選材（仍留 buffer） |
| 每篇附 `_relevance_reason` | str（僅 log/診斷）| 如 `excluded:竊` / `kept:肇事` / `no-rule` |

**FR-003 由此自動滿足**：某桶所有候選都落 `off_topic` → 該 major_category 無 on-topic 文章 →
不成桶、不 score、不 select → 不發布。無需額外「空桶」判斷碼。

## 4. Labeled Relevance Baseline（測試/量測資產，新增檔案）

供 `scripts/measure_relevance.py` 重播、量測 SC 階梯的**人工標記基準集**。落地為版控檔
（去識別化：只留 title／source／label，不含全文），置於 `tests/fixtures/` 或 `specs/012.../`。

| 欄 | 型別 | 說明 |
|---|---|---|
| `week_id` | str | 取樣週（如 `2026-W32`） |
| `major_category` | str | 該篇被指派的類別 |
| `title` | str | 標題（判定輸入） |
| `source` | str | 來源（feed 名） |
| `label` | enum `on`/`off`/`unclear` | **人工**標記的主題相關性（唯一的 ground truth） |
| `note` | str（選填）| 邊界案備註（如「肇事逃逸＝刑案∩事故」） |

**`label` 是三態，不是二元**（2026-08-08 使用者定的標記協定）：判定**只看標題**——
標題明顯是事故＝`on`，明顯不是＝`off`，**標題看不出來＝`unclear`**。第三態是必要的，
理由有二：(1) 台灣新聞標題殺人普遍，「擊落機車騎士」這種寫法無法確定是否真有摔車，
硬逼二選一會把猜測寫成 ground truth；(2) 若 skip 與「還沒走到」共用空字串，就無法
判斷 T010 何時算完成。`unclear` 的列**不計入 SC 比例的分母**——它們是量測的
**涵蓋範圍限制**，不是未完成的工作。⚠️ 已知偏差方向：被判 `unclear` 的正是最難的
案例，把它們排除會讓閘的分數**偏好看**；`measure_relevance.py` 因此一併印出
`unclear` 列數，讓這個限制隨數字一起被看到。

**紀律**：`label` 只能人工標，禁止用閘自己的輸出回填（那等於讓系統批改自己的考卷，
見 review-loop-bounds「校準用後果、不用被矯正的判斷史」）。基準集以 08-03 兩案為錨、涵蓋多週。

---

## 不變式（Invariants）

- 閘為**純函數**：同 (articles, rules) 必得同 partition（憲章 III；可重播）。
- 閘**零外部呼叫**：只讀 config 與 in-memory 子字串比對（憲章 IV / FR-006）。
- 閘**不改** `major_category`、不寫 DB、不丟 buffer（§1 路徑）；只有 §2 的全域市場詞封鎖會丟 buffer。
- **whitelist-dominant**：類別有 `require_any` 時，`on_topic = _hit(require_any)`，`exclude_any`
  不生效（邊界「肇事逃逸」由 require 命中解掉）。`exclude_any` 只在無 `require_any` 的類別走純黑名單支。
