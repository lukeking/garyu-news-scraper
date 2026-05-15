# Contract: `type: youtube` Source Configuration

This document defines the YAML schema for `type: youtube` entries in `sources_traffic.yml`.
The file is stored as the GitHub Environment Variable `SOURCES_TRAFFIC_YML` and MUST NOT
be committed.

## Schema

```yaml
- name: <string>          # required — human-readable channel label; appears as "source" on articles
  type: youtube           # required — literal string "youtube"
  enabled: <bool>         # optional, default: true — set false to disable without deleting
  channel_id: <string>    # required — YouTube channel ID, starts with "UC" (24 chars)
  max_items: <int>        # optional, default: 5 — max videos fetched per run (before Shorts filter)
  lookback_days: <int>    # optional, default: 2 — only fetch videos published within this window
```

## Example Entries

```yaml
sources:

  # ── type: youtube ──────────────────────────────────────────────
  # 必要欄位：name, type, channel_id
  # 選用欄位：enabled（預設 true）、max_items（預設 5）、lookback_days（預設 2）
  # channel_id 可從頻道頁面 URL 取得，格式為 UC 開頭的 24 字元字串。

  - name: 台灣道路觀察                          # 顯示在 log 與文章 source 欄位
    type: youtube
    enabled: true
    channel_id: UCxxxxxxxxxxxxxxxxxxxxxxxx      # 替換為實際 channel_id
    max_items: 5
    lookback_days: 2

  - name: 外國交通比較頻道
    type: youtube
    enabled: true
    channel_id: UCyyyyyyyyyyyyyyyyyyyyyyyy
    max_items: 3                                # 更新頻率低的頻道可設低一點
    # lookback_days 省略時使用預設值 2

  - name: 停用的頻道範例
    type: youtube
    enabled: false                              # ← 暫停收集，不需刪除
    channel_id: UCzzzzzzzzzzzzzzzzzzzzzzzz
```

## Behaviour Contract

- Videos with duration ≤ 60 seconds (YouTube Shorts) are **excluded** at fetch time.
- Videos published outside the `lookback_days` window are **excluded**.
- If transcript extraction fails for any video, the pipeline falls back to
  `title + "\n" + description[:500]` as the article body — no exception raised.
- On YouTube Data API quota exhaustion (HTTP 403 quotaExceeded), the source is
  **skipped** for that run and a log warning is emitted; other sources continue.
- The `YOUTUBE_API_KEY` environment variable / GitHub Secret must be present;
  if absent, all YouTube sources are skipped with an error log.

## Environment Variable

| Variable | Location | Description |
|---|---|---|
| `YOUTUBE_API_KEY` | GitHub Secret | YouTube Data API v3 key (no OAuth required) |

## Finding a Channel ID

YouTube channel IDs start with `UC` and are 24 characters long. They can be found:
- In the channel's About page URL: `youtube.com/channel/UC...`
- Via the YouTube Data API: `channels.list?forHandle=@channelname&part=id`
- Via browser devtools on the channel page (look for `"channelId"` in the page source)
