# Contract: `/api/hot-topics` 回應裡的焦點事件

Worker（`workers/api/src/index.js` 的 `handleHotTopics`）不改：它原樣轉送 `hot_topic_reports.source_article_links`。
這份合約描述上線後前端能拿到的形狀，以及前端必須容忍的舊形狀。

```json
{
  "reports": [
    {
      "week_start_date": "2026-11-02",
      "topic_label": "道安政策 · 彙整",
      "source_article_links": [
        { "title": "…", "link": "https://…", "summary": "…", "published": "2026-10-30T08:12:00+00:00" },
        { "link": "https://…", "published": "2026-05-12T02:00:00+00:00" },
        { "title": "…", "link": "https://…", "summary": "…" },
        "https://…"
      ]
    }
  ]
}
```

- 第 1 種：新報告與回填後的 dict 項目。
- 第 2 種：回填時由純字串轉來的項目（沒有 `title`、`summary`）。
- 第 3、4 種：找不到來源文章而沒補到日期的 dict，以及萬一還存在的純字串——前端照樣顯示，不計入區間；它們的 link 照樣進 ★ 對照。

不變式：`week_start_date`、`topic_label` 的值與上線前相同（分享連結的錨點）。
