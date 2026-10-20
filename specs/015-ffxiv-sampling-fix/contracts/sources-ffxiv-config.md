# Contract: `sources_ffxiv.yml` 的新型別與選項

讀者：`src/collector.py`。真身是 prod 變數 `SOURCES_FFXIV_YML`；`config/sources_ffxiv.example.yml` 是它的鏡像（漂移檢查守）。

## `type: vb_forum`

```yaml
  - name: "FFXIV JP Forum - DPS"
    type: vb_forum
    url: "https://forum.square-enix.com/ffxiv/external.php?type=RSS2&forumids=551&lastpost=1"
    enabled: true
    content_type: "ffxiv"
    weight: 80
    max_pages: 3
    max_replies: 20
    max_chars: 6000
```

- `url` MUST 帶 `lastpost=1`（依最後回覆排序）。少了它，舊串有新回覆不會出現；程式不補，照設定抓。
- 三個上限都可省略，省略時用上面的初值。

## `type: html_patch` 的新選項（都可省略，省略＝現行行為）

```yaml
  - name: "FFXIV Lodestone JP 更新資訊"
    type: html_patch
    url: "https://jp.finalfantasyxiv.com/lodestone/news/category/3"
    enabled: true
    content_type: "ffxiv"
    weight: 60
    selector: "li.news__list"
    title_selector: "p.news__list--title"
    max_items: 10
    date_pattern: 'ldst_strftime\((\d{10})'
    exclude_title_prefixes: ["Lodestone", "コンパニオンアプリ"]
    detail_selector: "div.news__detail__wrapper"
    max_chars: 2000
```

## `weight`（所有 FFXIV 來源）

| 來源 | 初值 |
|---|---|
| FFXIV JP Forum - プロデューサーレターLIVE | 100 |
| FFXIV JP Forum - TANK／DPS／HEALER／その他バトルシステム | 80 |
| FFXIV Lodestone JP 更新資訊 | 60 |
| FFXIV TW 修正說明 | 50 |
| Reddit r/ffxiv | 20 |
| FFXIV JP Forum（列表頁） | 10 |

## 向下相容

新程式讀舊設定：沒有 `weight` 全部當 0 → 排序退化成依時間（等同現狀），每個來源印一行警告；`type: rss` 的五個版照舊。
舊程式讀新設定：不認得 `vb_forum`，五個版被當成未知型別略過——所以設定必須在程式 merge 之後才改（plan「上線順序」）。
