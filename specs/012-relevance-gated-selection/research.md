# Phase 0 Research: 相關性選材閘

四個設計決策。全部以 08-03 實測（E1）與現行程式碼結構為據，非臆測。

---

## D1. 相關性閘的作用點：每週選材期（邏輯放 filter.py），不在每日 filter 落地

**Decision**: 閘的**純函數邏輯**寫在 `src/filter.py`；**呼叫時機**在
`scripts/traffic_weekly_analysis.py`，於 `cluster_traffic_articles` 之前，對 buffer 讀出的候選
做 on/off-topic 分割。**不**在每日 `TrafficCategory.filter`（`src/pipeline/traffic.py`）改動
`major_category` 或丟棄文章。

**Rationale**:
- **無 schema 變更、buffer 保持完整**：每週選材期即時判定既有欄位（title／summary／major_category），
  不新增 stored 欄位。off-topic 文章仍留在 buffer（可逆、可稽核、可量測），只是不進熱點報告——
  正對齊 spec 範圍（US1/US2 講的是**發布報告**，非每日 buffer 列表；後者是 BACKLOG #5，已出局）。
- **誤殺可逆**：若規則過嚴誤判一則真事故，文章沒消失（仍在 buffer），僅該週報少收一篇——比
  filter 階段直接丟棄（永久離開 buffer）安全，呼應 SC-004（不回歸）與 spec 的誤殺邊界。
- **憲章歸位**：相關性是 filter 職責（憲章 I 明訂 dedup 屬 `src/filter.py`），故**邏輯**放 filter.py；
  但**作用**在報告生成，故由每週 orchestrator **呼叫**。邏輯與時機分離，兩個憲章面都顧到。

**Alternatives considered**:
- **每日 filter 階段丟棄／改 `major_category`**：會一併清乾淨每日列表，但（a）誤殺永久（文章離開
  buffer，不可逆）；（b）超出 spec 範圍（每日列表＝#5）；（c）demote 到 `uncategorised` 反而可能
  聚成「uncategorised 熱點」。否決。
- **選材後才過濾（scoring/selection 之後）**：桶已成形、分數已算，還要回頭剔除，順序彆扭且
  FR-003（整桶離題→不發布）要另外處理。在 cluster **之前**分割最乾淨——空桶自然不 score、不 select。

---

## D2. 規則模型：AND-NOT（有事故 token 且無刑案/市場 token），per-category、config 驅動

**Decision**: 一篇文章對某事故類別為 **on-topic** 的條件＝
`(命中該類別的正面 token 白名單) AND NOT (命中刑案／市場 token 黑名單)`。
白/黑名單按類別寫在 config，可各自增刪、免改碼。

**Rationale**:
- **AND-NOT 自然解掉 spec 的核心邊界**：肇事逃逸／公共危險致死同時是刑案也是事故——因帶
  事故 token（肇事／致死／撞）→ 命中白名單、通過；純竊盜（有刑案 token、無事故 token）→ 擋下。
  單靠黑名單會誤擋肇事逃逸，單靠白名單會漏掉「無明顯事故詞的離題」，兩者合議最穩。
- **對症兩種離題**：刑案（竊/羈押/求償/毒駕/通緝）與市場（油耗/市佔/銷量/戰報/規格）用同一組
  黑名單 token 表達；白名單（撞/追撞/自撞/車禍/送醫/不治/傷/翻車/失控）確認正題。
- **config 驅動（憲章 II）**：token 表放 `categories_traffic.yml` 的 per-category 區塊，調參免改碼，
  與現行 taxonomy 同檔同風格。**初始 token 表是 seed，不是定案**——由 D4 的基準集實測調整。
- **沿用既有分詞**：判定用 `normalise_title` 產的 jieba token（與 `assign_category` 同源），
  行為一致、零新依賴。

**Alternatives considered**:
- **只用白名單**（要求必含事故 token）：漏接「無事故詞的行銷稿」以外的離題，且真事故若標題
  用字冷僻會誤殺（false exclusion 風險最高）。
- **只用黑名單**（命中即擋）：誤擋肇事逃逸這類「刑案 ∩ 事故」，且黑名單詞彙開放無窮、追不完。
- **LLM 判相關性**：把選材推過「零 AI」成本線（FR-006／憲章 IV），且 memory 明示「先試純規則，
  LLM 留給真的難判的」。純規則能解掉 08-03 兩案的大部分，故本期不引入。**重開條件**：若基準集顯示
  純規則在 SC-002（≤20%）撞牆且殘餘皆為語意型離題，再評估「僅對殘餘小集合」的輕量判斷。

---

## D3. 市場/行銷側（Tier 1）：擴充既有 `blocked_content_keywords`，用內容 token 不用來源名

**Decision**: 金線類行銷稿優先用**既有**機制——`src/pipeline/traffic.py:66` 的
`blocked_content_keywords`（filter 階段標題關鍵字封鎖）——**補上缺的市場詞**（油耗／市佔／市占／
銷量／掛牌數／戰報／領牌…）。純 config，零程式碼。剩下黑名單未涵蓋的，交由 D2 的相關性閘兜底。

**Rationale**:
- **機制已存在、只是不全**：現行 list 有「售價／試駕／銷售排行／車展／優惠」等，但**缺** 08-03 金線
  那批的「油耗排名／市佔率／銷量戰報」用詞——所以整席漏過去。補詞即補洞，是全案最便宜的一格。
- **以內容 token 封鎖，滿足 FR-007**：封鎖「油耗/市佔」這類**市場語彙**而非「地球黃金線」這個
  **來源名**——車媒若真的報導一則事故（無市場語彙）不會被連坐擋掉。這是 FR-007 的落地方式。
- **兩段式對齊 SC 階梯**：Tier 1（config）先量能吃掉多少金線案 → 多半直接讓該桶清空、達 SC-001；
  Tier 2（閘）再處理中時的刑案混雜，攻 SC-002。符合決策風格「階梯、Gate 設最寬鬆那階」。

**Alternatives considered**:
- **用來源名封鎖車媒**（blocked_sources 加「地球黃金線」）：違反 FR-007（真事故報導被連坐），
  且經 Google News feed 進來的 `source`＝feed 名、抓不到出版商名（現行 code 註解已載此坑）。否決。
- **只靠 D2 相關性閘、不碰 Tier 1**：可行但放棄了一個零程式碼的既有槓桿，且行銷詞用「NOT 市場 token」
  表達本就與 blocked_content_keywords 重疊——不如讓最便宜的 config 層先收割。

---

## D4. SC 量測：人工標記基準集 + `measure_relevance.py` 重播，禁止主觀印象

**Decision**: 建一份**人工相關性標記基準集**（取樣數週，對每篇候選標 on/off-topic），寫一支唯讀
診斷腳本 `scripts/measure_relevance.py`，對基準集重播「套閘前 vs 套閘後」的發布名單，輸出 SC 階梯
（SC-001 多數離題？SC-002 ≤20%？SC-004 正題數不降？）。硬門檻只認這個實測數字。

**Rationale**:
- **承 011 之戒**：spec 011 的 SC-001/002/003 因無基準集而長期「未量測」，STATE 明令「禁止以主觀
  印象填」。本功能的 SC 從一開始就綁一份可重播的標記集，否則階梯是空的。
- **反事實要被建構、不能被模擬**（review-loop-bounds）：「套閘後會不會變好」不能靠想像，要真的把
  閘套上去、對同一批標記資料重跑，比較前後——腳本就是那個反事實的物證。
- **基準取自後果、可推翻預期**（decision-style）：以 08-03 兩案為錨（金線 100%、中時 ~50%），
  但標記集要涵蓋多週，讓「純規則其實不夠」這個相反結論有機會浮現（→ D2 的 LLM 重開條件）。

**Alternatives considered**:
- **只看 08-03 單點**：樣本太小、且是挑出來的極端案，容易過擬合 token 表。需多週基準。
- **用品質分數當 proxy**：已證無效——`initial_quality_score` 把毒駕刑案排全桶第一，它量的就不是
  相關性（FR-005 的由來）。

---

## 未決／交棒 Phase 2（/speckit-tasks）

- 初始 token 白/黑名單的具體詞表＝**seed**，由基準集調整（D2/D4）；tasks 要含「標記基準集」與
  「調 token 表至 SC 階梯」兩條可驗任務。
- 事故類作用域：先鎖 `機車事故`（acute）；其他事故類（行人事故／路口安全／大型車安全）是否套同一
  組規則，待基準集顯示它們是否也有離題再定——config 結構預留 per-category，但不預先填（YAGNI）。
