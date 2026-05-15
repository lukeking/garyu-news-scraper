# Quickstart: Testing YouTube Sources Locally

## Prerequisites

- Python 3.x with dependencies installed (`pip install -r requirements.txt`)
- `.env` file copied from `.env.example` with real values filled in
- A YouTube Data API v3 key (free, from Google Cloud Console)

## Step 1: Get a YouTube Data API v3 Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use an existing one)
3. Enable **YouTube Data API v3** under APIs & Services → Library
4. Create an **API key** under APIs & Services → Credentials
5. Copy the key value

## Step 2: Find a Channel ID

Channel IDs start with `UC` and are 24 characters long.

**Option A** — from the channel page URL:
```
https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxxxx
```
Copy the `UC...` part.

**Option B** — from page source:
Open the YouTube channel page → right-click → View Page Source → search for `"channelId"`.

**Option C** — for channels using a handle (`@channelname`):
```bash
# Replace YOUR_API_KEY and @channelname:
curl "https://www.googleapis.com/youtube/v3/channels?forHandle=@channelname&part=id&key=YOUR_API_KEY"
```

## Step 3: Configure Local Sources

Add a `type: youtube` entry to `config/sources_traffic.yml` (create from the example if it doesn't exist):

```yaml
sources:
  - name: 測試頻道
    type: youtube
    enabled: true
    channel_id: UCxxxxxxxxxxxxxxxxxxxxxxxx   # replace with real ID
    max_items: 3
    lookback_days: 7                         # extend to 7 days for easier local testing
```

## Step 4: Add the API Key to .env

```
YOUTUBE_API_KEY=AIza...your_key_here
```

## Step 5: Run the Traffic Buffer Pipeline

```bash
python scripts/traffic_buffer.py
```

Or run just the collection step in isolation:

```python
from src.collector import load_sources, collect_sources
sources = load_sources()
articles = collect_sources(sources)
yt_articles = [a for a in articles if a.get("source_type") == "youtube"]
print(f"YouTube articles collected: {len(yt_articles)}")
for a in yt_articles:
    print(f"  [{a['source']}] {a['title'][:60]}")
    print(f"  transcript_len={len(a.get('summary',''))} chars")
```

## Step 6: Verify Output

Check that:
- At least one article has `source_type == "youtube"`
- The `summary` field contains transcript text (long) or title+description (short fallback)
- Videos ≤ 60s are absent (Shorts filtered)
- Off-topic videos absent after keyword filter

## Common Issues

| Symptom | Likely cause | Fix |
|---|---|---|
| `YOUTUBE_API_KEY 未設定` | Key not in `.env` | Add `YOUTUBE_API_KEY=...` to `.env` |
| `0 筆` from YouTube source | No videos in `lookback_days` window | Increase `lookback_days: 7` for testing |
| `逐字稿取得失敗` on all videos | Cloud IP block (if running on a VM) | Expected — fallback to title+description works |
| `HttpError 403` | Quota exhausted or API not enabled | Check Google Cloud Console quota dashboard |
