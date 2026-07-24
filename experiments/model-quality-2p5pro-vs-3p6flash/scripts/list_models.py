"""
Read-only probe: list every model this GEMINI_API_KEY can call on the
generativelanguage (AI Studio / key-based) endpoint — the SAME endpoint the
pipeline uses (src/analyzer.py:20). Confirms whether gemini-3.6-flash exists
here and its exact id, WITHOUT printing the key or the key-bearing URL.
"""
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv("/home/luke/Projects/garyu-news-scraper/.env", override=True)
key = os.environ.get("GEMINI_API_KEY", "")
if not key:
    sys.exit("GEMINI_API_KEY 未設定（.env）")

base = "https://generativelanguage.googleapis.com/v1beta/models"
models = []
page_token = None
while True:
    params = {"key": key, "pageSize": 200}
    if page_token:
        params["pageToken"] = page_token
    r = requests.get(base, params=params, timeout=60)
    if r.status_code != 200:
        # print status + body but NOT the request URL (which carries the key)
        sys.exit(f"ListModels HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    models.extend(data.get("models", []))
    page_token = data.get("nextPageToken")
    if not page_token:
        break

def sid(m):
    return m.get("name", "").removeprefix("models/")

gen = [m for m in models if "generateContent" in m.get("supportedGenerationMethods", [])]

print(f"總模型數：{len(models)}；支援 generateContent：{len(gen)}\n")

print("=== 名稱含 '3' 或 'flash' 的（找 3.6-flash）===")
for m in sorted(gen, key=sid):
    s = sid(m)
    if "flash" in s or "-3" in s or "3." in s:
        print(f"  {s}")

print("\n=== 精確比對 gemini-3.6-flash 家族 ===")
targets = [s for s in (sid(m) for m in gen) if s.startswith("gemini-3.6-flash")]
if targets:
    for t in sorted(targets):
        print(f"  ✓ {t}")
else:
    print("  ✗ 此端點/金鑰下找不到任何 gemini-3.6-flash*（可能 Vertex-only 或 id 不同）")

print("\n=== 全部支援 generateContent 的 gemini-* 模型 ===")
for m in sorted(gen, key=sid):
    s = sid(m)
    if s.startswith("gemini"):
        print(f"  {s}")
