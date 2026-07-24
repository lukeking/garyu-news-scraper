"""
Diagnose the 429: hit each model once with a trivial prompt on the same
key-based endpoint, print HTTP status and (on 429) the parsed quota details
(which quota metric, limit value, and RetryInfo.retryDelay). Never prints the
key or the key-bearing URL.
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv("/home/luke/Projects/garyu-news-scraper/.env", override=True)
key = os.environ.get("GEMINI_API_KEY", "")

MODELS = ["gemini-2.5-pro", "gemini-3.6-flash", "gemini-2.5-flash"]
payload = {"contents": [{"role": "user", "parts": [{"text": "ping"}]}],
           "generationConfig": {"maxOutputTokens": 8}}

for m in MODELS:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
    try:
        r = requests.post(url, json=payload, timeout=60)
    except Exception as e:
        print(f"{m:22s} EXC {e}")
        continue
    print(f"{m:22s} HTTP {r.status_code}")
    if r.status_code == 200:
        continue
    try:
        err = r.json().get("error", {})
    except Exception:
        print("   (non-json body)", r.text[:200]); continue
    print(f"   status={err.get('status')} message={err.get('message','')[:120]}")
    for d in err.get("details", []):
        t = d.get("@type", "").split("/")[-1]
        if t == "QuotaFailure":
            for v in d.get("violations", []):
                print(f"   QUOTA metric={v.get('quotaMetric')} "
                      f"id={v.get('quotaId')} value={v.get('quotaValue')} "
                      f"dims={v.get('quotaDimensions')}")
        elif t == "RetryInfo":
            print(f"   RETRY-AFTER {d.get('retryDelay')}")
        elif t == "Help":
            pass
        else:
            print(f"   detail[{t}] {json.dumps(d, ensure_ascii=False)[:160]}")
