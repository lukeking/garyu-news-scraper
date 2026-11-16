#!/usr/bin/env python3
"""不發布執行前後的五個計數（spec 020 SC-001，共七項）：take 只發 GET、取數寫成 JSON，compare 比對兩份。
取不到的項目寫「未取得：原因」，不補值。各項的定義與讀法見 docs/dry-run.md。"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

TIMEOUT = 15
CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"
POSTGREST_OK = (200, 206)  # count=exact 的回應是 206（PostgREST 文件），沒有 Range 時也可能是 200
BUFFER = {"content_type": "eq.traffic", "hot_topic_analyzed": "eq.false"}
ITEMS = [
    ("hot_topic_reports", "報告數（hot_topic_reports）"),
    ("articles", "報告數（articles）"),
    ("buffer", "buffer 筆數"),
    ("digest_pool", "彙整池未分析筆數"),
    ("knowledge_base", "術語庫條目數"),
    ("deploy_traffic", "最後部署時間（garyu-traffic-news）"),
    ("deploy_ffxiv", "最後部署時間（garyu-ffxiv-news）"),
]
NAMES = dict(ITEMS)


class Unavailable(Exception):
    pass


class CountsFileError(Exception):
    pass


def _error_note(resp) -> str:
    try:
        body = resp.json()
    except ValueError:
        return ""
    if isinstance(body, dict) and isinstance(body.get("errors"), list) and body["errors"]:
        body = body["errors"][0]
    if not isinstance(body, dict) or not (body.get("code") or body.get("message")):
        return ""
    return "：" + " ".join(str(body[k]) for k in ("code", "message") if body.get(k))[:200]


def _get(url, params=None, headers=None):
    try:
        return requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise Unavailable(f"請求失敗（{type(e).__name__}）") from None


def _count(base, key, table, params):
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Prefer": "count=exact"}
    resp = _get(f"{base}/rest/v1/{table}", params={"limit": "1", **params}, headers=headers)
    if resp.status_code not in POSTGREST_OK:
        raise Unavailable(f"HTTP {resp.status_code}{_error_note(resp)}")
    header = resp.headers.get("Content-Range")
    total = (header or "").rpartition("/")[2]
    if not total.isdigit():
        raise Unavailable(f"Content-Range 沒有總數（{header!r}）")
    return int(total)


def _digest_categories():
    from src.pipeline_config import load_pipeline_config

    try:
        digests = load_pipeline_config().get("category_digest") or {}
    except Exception as e:
        raise Unavailable(f"讀不了 pipeline_config（{type(e).__name__}: {e}）") from None
    cats = set(digests)
    for cfg in digests.values():
        cats |= set((cfg or {}).get("include_categories") or [])
    if not cats:
        raise Unavailable("pipeline_config 的 category_digest 是空的（設定檔不存在或沒有彙整類別），彙整池沒有定義")
    return sorted(cats)


def _deploy_time(account, token, project):
    resp = _get(f"{CLOUDFLARE_API}/accounts/{account}/pages/projects/{project}",
                headers={"Authorization": f"Bearer {token}"})
    if resp.status_code != 200:
        raise Unavailable(f"HTTP {resp.status_code}{_error_note(resp)}")
    body = resp.json()
    result = body.get("result") if isinstance(body, dict) else None
    latest = result.get("latest_deployment") if isinstance(result, dict) else None
    created = latest.get("created_on") if isinstance(latest, dict) else None
    if not isinstance(created, str) or not created:
        raise Unavailable("回應沒有 result.latest_deployment.created_on")
    return created


def _fetchers():
    from src.storage import supabase_api_key

    base = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = supabase_api_key()
    token = (os.environ.get("CLOUDFLARE_API_TOKEN") or "").strip()
    account = (os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()

    def supabase(table, params):
        if not base or not key:
            raise Unavailable("未設 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY／SUPABASE_KEY")
        return _count(base, key, table, params)

    def digest():
        if not base or not key:
            raise Unavailable("未設 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY／SUPABASE_KEY")
        quoted = ",".join(f'"{c}"' for c in _digest_categories())
        return _count(base, key, "articles", {"select": "id", **BUFFER, "major_category": f"in.({quoted})"})

    def deploy(project):
        if not token or not account:
            raise Unavailable("未設 CLOUDFLARE_API_TOKEN 或 CLOUDFLARE_ACCOUNT_ID")
        return _deploy_time(account, token, project)

    return {
        "hot_topic_reports": lambda: supabase("hot_topic_reports", {"select": "id"}),
        "articles": lambda: supabase("articles", {"select": "id"}),
        "buffer": lambda: supabase("articles", {"select": "id", **BUFFER}),
        "digest_pool": digest,
        "knowledge_base": lambda: supabase("knowledge_base", {"select": "jp_term"}),
        "deploy_traffic": lambda: deploy("garyu-traffic-news"),
        "deploy_ffxiv": lambda: deploy("garyu-ffxiv-news"),
    }


def take_counts() -> dict:
    from src import run_mode

    data = {"run_mode": run_mode.current(), "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "items": {}}
    fetchers = _fetchers()
    for key, name in ITEMS:
        try:
            entry = {"name": name, "value": fetchers[key]()}
            print(f"[計數] {name}：{entry['value']}", flush=True)
        except Exception as e:
            reason = str(e) if isinstance(e, Unavailable) else f"{type(e).__name__}: {e}"
            entry = {"name": name, "unavailable": reason}
            print(f"[計數] {name}：未取得：{reason}", flush=True)
        data["items"][key] = entry
    return data


def run_take(out: str) -> int:
    try:
        data = take_counts()
    except Exception as e:
        print(f"[計數] 結果：沒有寫檔（{type(e).__name__}: {e}）", flush=True)
        return 2
    try:
        if os.path.dirname(out):
            os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except OSError as e:
        print(f"[計數] 結果：沒有寫檔（寫不進 {out}：{e}）", flush=True)
        return 2
    gaps = sum("unavailable" in v for v in data["items"].values())
    print(f"[計數] 結果：寫入 {out}（{len(data['items'])} 項，未取得 {gaps} 項）", flush=True)
    return 0


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise CountsFileError(f"找不到 {path}") from None
    except ValueError as e:
        raise CountsFileError(f"{path} 不是 JSON：{e}") from None
    except OSError as e:
        raise CountsFileError(f"讀不了 {path}：{e}") from None
    why = None
    if not isinstance(data, dict):
        why = "頂層不是物件"
    elif not isinstance(data.get("items"), dict):
        why = "items 不是物件"
    else:
        for key, entry in data["items"].items():
            if not isinstance(entry, dict):
                why = f"{key} 不是物件"
            elif ("value" in entry) == ("unavailable" in entry):
                why = f"{key} 要剛好有 value 或 unavailable 其中一個"
            if why:
                break
    if why:
        raise CountsFileError(f"{path} 的形狀不對：{why}")
    return data["items"]


def _compare_items(before: dict, after: dict) -> int:
    keys = [k for k, _ in ITEMS] + sorted((set(before) | set(after)) - set(NAMES))
    missing = {"unavailable": "檔裡沒有這一項"}
    differ, gaps = [], []
    for key in keys:
        b, a = before.get(key, missing), after.get(key, missing)
        name = NAMES.get(key) or b.get("name") or a.get("name") or key
        if "unavailable" in b or "unavailable" in a:
            gaps.append(key)
            print(f"[計數比對] {name}（{key}）：未取得（前：{b.get('unavailable', b.get('value'))}；"
                  f"後：{a.get('unavailable', a.get('value'))}）", flush=True)
        elif b["value"] == a["value"]:
            print(f"[計數比對] {name}（{key}）：前 {b['value']!r}、後 {a['value']!r}，相同", flush=True)
        else:
            differ.append(key)
            print(f"[計數比對] {name}（{key}）：前 {b['value']!r}、後 {a['value']!r}，不同", flush=True)
    if not differ and not gaps:
        print(f"[計數比對] 結果：{len(keys)} 項都相同", flush=True)
        return 0
    print(f"[計數比對] 結果：不同 {len(differ)} 項（{'、'.join(differ) or '無'}）；"
          f"未取得 {len(gaps)} 項（{'、'.join(gaps) or '無'}）", flush=True)
    return 1


def run_compare(before: str, after: str) -> int:
    try:
        return _compare_items(_load(before), _load(after))
    except CountsFileError as e:
        print(f"[計數比對] 結果：沒有比對（{e}）", flush=True)
    except Exception as e:
        print(f"[計數比對] 結果：沒有比對完（{type(e).__name__}: {e}）", flush=True)
    return 2


EPILOG = """呼叫方式（從 repo 根目錄）：
  python scripts/dry_run_counts.py take --out traffic-pool/counts_before.json
  python scripts/dry_run_counts.py compare traffic-pool/counts_before.json traffic-pool/counts_after.json

take 只發 GET：Supabase 的 REST（Prefer: count=exact，列數從 Content-Range 取，不抓列）與 Cloudflare 的
GET /accounts/{account}/pages/projects/{project}（latest_deployment.created_on）。
環境變數：SUPABASE_URL、SUPABASE_SERVICE_ROLE_KEY（沒有就用 SUPABASE_KEY）、CLOUDFLARE_API_TOKEN、
CLOUDFLARE_ACCOUNT_ID；彙整類別讀 PIPELINE_CONFIG_YML_PATH（預設 config/pipeline_config.yml）。本機會載入 .env，已設的環境變數優先。
結束碼：take 寫出檔是 0（有未取得的項目也是 0，比對時算沒通過），沒寫檔是 2；
compare 全部相同是 0，有不同或未取得是 1，檔案找不到、不是 JSON 或形狀不對是 2。最後一行一定是「結果：」那一行。"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="scripts/dry_run_counts.py", description=__doc__.splitlines()[0],
                                     epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_take = sub.add_parser("take", help="取一次七項計數，印出並寫成 JSON")
    p_take.add_argument("--out", required=True, help="寫出的 JSON 路徑；上層目錄不存在就建")
    p_cmp = sub.add_parser("compare", help="比對兩份計數檔，逐項印出，最後一行是結果")
    p_cmp.add_argument("before", help="開頭取的那一份")
    p_cmp.add_argument("after", help="結尾取的那一份")
    args = parser.parse_args(argv)

    if args.command == "compare":
        return run_compare(args.before, args.after)
    load_dotenv(os.path.join(_REPO_ROOT, ".env"))
    return run_take(args.out)


if __name__ == "__main__":
    sys.exit(main())
