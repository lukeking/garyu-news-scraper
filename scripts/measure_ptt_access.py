"""GNS-016 診斷（唯讀、不需憑證）：PTT 在 Actions 上的 403 是擋 IP 還是擋請求形狀（標頭、cookie、TLS 指紋）。
`prod` 變體的標頭直接 import 自 collector，跟 `_fetch_ptt` 相同；其餘各只改一項，執行時印出。最後一行是判讀，robots.txt 只當對照。
用法：python scripts/measure_ptt_access.py [board ...]（預設 biker SuperBike）"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.collector import PTT_HEADERS  # noqa: E402

DEFAULT_BOARDS = ["biker", "SuperBike"]
TIMEOUT = 15
PAUSE = 1.5
BODY_PREVIEW = 200
UA = PTT_HEADERS["User-Agent"]
CONTROL = "robots.txt"

VARIANTS = [
    ("prod", "與 _fetch_ptt 相同", dict(PTT_HEADERS), True),
    ("no-br", "Accept-Encoding 拿掉 br", {**PTT_HEADERS, "Accept-Encoding": "gzip, deflate"}, True),
    ("no-cookie", "不帶 over18 cookie", dict(PTT_HEADERS), False),
    ("ua-only", "只留 User-Agent", {"User-Agent": UA}, True),
    ("requests-default", "不帶任何自訂標頭（python-requests 的 UA）", {}, True),
    ("curl", "改用 curl（TLS 指紋不同於 Python），只帶 User-Agent 與 over18 cookie", None, True),
]


def _result(status: int, elapsed: float, headers: dict, cookies: list, text: str, url: str) -> dict:
    entries = None
    if status == 200 and "/bbs/" in url:
        entries = len(BeautifulSoup(text, "lxml").select("div.r-ent"))
    return {"status": status, "elapsed": elapsed, "headers": headers, "cookies": cookies,
            "body": text[:BODY_PREVIEW], "entries": entries}


def fetch_requests(url: str, headers: dict, over18: bool) -> dict:
    session = requests.Session()
    if over18:
        session.cookies.set("over18", "1", domain="www.ptt.cc")
    start = time.monotonic()
    try:
        resp = session.get(url, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        return {"status": None, "error": f"{type(e).__name__}: {e}"}
    return _result(resp.status_code, time.monotonic() - start, dict(resp.headers),
                   [c.name for c in resp.cookies], resp.text, url)


def fetch_curl(url: str) -> dict:
    with tempfile.NamedTemporaryFile() as body:
        cmd = ["curl", "-sS", "--compressed", "--max-time", str(TIMEOUT), "-A", UA, "-b", "over18=1",
               "-D", "-", "-o", body.name, "-w", "\n%{http_code}", url]
        start = time.monotonic()
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 5)
        except (OSError, subprocess.TimeoutExpired) as e:
            return {"status": None, "error": f"{type(e).__name__}: {e}"}
        if p.returncode != 0:
            return {"status": None, "error": f"curl exit {p.returncode}: {p.stderr.strip()}"}
        raw_headers, _, code = p.stdout.rpartition("\n")
        headers, cookies = {}, []
        for line in raw_headers.splitlines()[1:]:
            k, sep, v = line.partition(":")
            if not sep:
                continue
            if k.strip().lower() == "set-cookie":
                cookies.append(v.strip().split("=", 1)[0])
            else:
                headers[k.strip()] = v.strip()
        text = Path(body.name).read_bytes().decode("utf-8", errors="replace")
    return _result(int(code), time.monotonic() - start, headers, cookies, text, url)


def fetch(url: str, headers, over18: bool) -> dict:
    return fetch_curl(url) if headers is None else fetch_requests(url, headers, over18)


def print_result(label: str, url: str, r: dict) -> None:
    print(f"\n=== {label}  {url}")
    if r["status"] is None:
        print(f"  錯誤：{r['error']}")
        return
    print(f"  狀態：{r['status']}（{r['elapsed']:.2f}s）")
    for k, v in r["headers"].items():
        if k.lower() != "set-cookie":
            print(f"  {k}: {v}")
    # 公開 repo 的 log 誰都讀得到：Set-Cookie 只印名稱，不印值
    if r["cookies"]:
        print(f"  Set-Cookie 名稱：{'、'.join(r['cookies'])}")
    if r["entries"] is not None:
        print(f"  div.r-ent：{r['entries']} 列")
    print(f"  內文開頭：{r['body']!r}")


def _mitigated(r: dict):
    return next((v for k, v in r.get("headers", {}).items() if k.lower() == "cf-mitigated"), None)


def verdict(rows: list) -> str:
    boards = [(f"{b}/{n}", r) for b, n, r in rows if b != CONTROL and r["status"] is not None]
    control = next((r for b, _, r in rows if b == CONTROL), None)
    note = "" if not control or control["status"] is None else f"（對照：{CONTROL} {control['status']}）"
    if not boards:
        return "判讀：看板的請求都沒拿到 HTTP 回應，這次沒有量到東西"
    codes = {r["status"] for _, r in boards}
    if codes == {200}:
        return f"判讀：看板的 {len(boards)} 個請求全部 200，這個出口沒有被擋{note}"
    if codes == {403}:
        how = "，全部是 Cloudflare challenge（cf-mitigated: challenge）" if all(
            _mitigated(r) == "challenge" for _, r in boards) else ""
        if not any(k.endswith("/curl") for k, _ in boards):
            return f"判讀：看板的 {len(boards)} 個請求全部 403{how}，但 curl 沒拿到回應，分不出擋 IP 還是擋 TLS 指紋{note}"
        return f"判讀：看板的 {len(boards)} 個請求全部 403（含 curl）{how}，跟標頭、cookie、TLS 指紋都無關，指向 IP 層{note}"
    ok = [k for k, r in boards if r["status"] == 200]
    if ok:
        return f"判讀：看板的請求有的 200、有的不是，跟請求形狀有關；200 的是 {'、'.join(ok)}{note}"
    return f"判讀：看板的請求沒有 200 也不全是 403，看上面的狀態碼逐條判斷{note}"


def main() -> int:
    boards = sys.argv[1:] or DEFAULT_BOARDS
    print("變體：")
    for name, desc, _, over18 in VARIANTS:
        print(f"  {name}：{desc}（over18 cookie：{'有' if over18 else '無'}）")

    rows = []
    for board in boards:
        url = f"https://www.ptt.cc/bbs/{board}/index.html"
        for name, _, headers, over18 in VARIANTS:
            r = fetch(url, headers, over18)
            print_result(f"{board} / {name}", url, r)
            rows.append((board, name, r))
            time.sleep(PAUSE)
    robots = f"https://www.ptt.cc/{CONTROL}"
    r = fetch_requests(robots, {"User-Agent": UA}, False)
    print_result(f"{CONTROL} / ua-only", robots, r)
    rows.append((CONTROL, "ua-only", r))

    print("\n=== 摘要")
    for board, name, r in rows:
        status = r["status"] if r["status"] is not None else "錯誤"
        entries = "" if r.get("entries") is None else f"，div.r-ent {r['entries']} 列"
        print(f"  {board:<12} {name:<17} {status}{entries}")
    line = verdict(rows)
    print(line)
    return 1 if "沒有量到東西" in line else 0


if __name__ == "__main__":
    sys.exit(main())
