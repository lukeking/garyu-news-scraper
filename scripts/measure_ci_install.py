"""列出最近幾次 tests.yml 的 unit job 裡「安裝 Chromium（版面測試用）」那一步花了幾秒（原 BACKLOG GNS-20261105-v4e 的量測層；unit job 逾時或裝得慢時先跑這支）。
用法：python scripts/measure_ci_install.py [--limit 30] [--slow 120]；經 gh 讀 Actions API 的步驟起訖時間，不下載 log。
超過 --slow 秒的 run 會印出撈 apt mirror 速度那一行的指令；一次都量不到時 exit 1。"""
import argparse
import json
import statistics
import subprocess
import sys
from datetime import datetime

WORKFLOW = "tests.yml"
JOB = "unit"
STEP = "安裝 Chromium（版面測試用）"


class MeasureError(Exception):
    pass


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def step_seconds(jobs_payload: dict, job: str = JOB, step: str = STEP):
    """回 (秒數, conclusion)；job 或那一步不在回 None。那一步在卻沒有起訖時間就丟 MeasureError，不補 0。"""
    for j in jobs_payload.get("jobs") or []:
        if j.get("name") != job:
            continue
        for s in j.get("steps") or []:
            if s.get("name") == step:
                if not s.get("started_at") or not s.get("completed_at"):
                    raise MeasureError(f"「{step}」沒有起訖時間（conclusion={s.get('conclusion')}）")
                return (_ts(s["completed_at"]) - _ts(s["started_at"])).total_seconds(), s.get("conclusion")
    return None


def summary_line(rows: list, slow: float) -> str:
    measured = [r["seconds"] for r in rows if r["seconds"] is not None]
    if not measured:
        raise MeasureError(f"{len(rows)} 次裡沒有一次量到「{STEP}」：步驟改名了，或這些 run 都還沒跑到")
    return (f"量到 {len(measured)} 次（另 {len(rows) - len(measured)} 次沒有那一步）：中位數 {statistics.median(measured):.0f} 秒、"
            f"最長 {max(measured):.0f} 秒、超過 {slow:g} 秒 {sum(1 for s in measured if s > slow)} 次")


def _gh(args: list):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise MeasureError(f"gh {' '.join(args[:3])} 失敗：{r.stderr.strip()[:200]}")
    return json.loads(r.stdout)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit", type=int, default=30, help="看最近幾次 run（預設 30）")
    p.add_argument("--slow", type=float, default=120, help="安裝超過幾秒算慢（預設 120）")
    args = p.parse_args(argv)
    try:
        runs = _gh(["run", "list", "--workflow", WORKFLOW, "--limit", str(args.limit),
                    "--json", "databaseId,createdAt,status,conclusion,headBranch"])
        rows = []
        for run in runs:
            row = {"run": run["databaseId"], "created": run["createdAt"], "branch": run["headBranch"], "seconds": None}
            if run["status"] != "completed":
                note = f"還沒跑完（{run['status']}）"
            else:
                got = step_seconds(_gh(["api", f"repos/{{owner}}/{{repo}}/actions/runs/{run['databaseId']}/jobs"]))
                row["seconds"], note = got if got is not None else (None, "沒有那一步")
            rows.append(row)
            sec = "—" if row["seconds"] is None else f"{row['seconds']:.0f}"
            print(f"{row['created']}  {row['run']}  {sec:>4} 秒  {note}  {row['branch']}")
        print(summary_line(rows, args.slow))
    except MeasureError as e:
        print(f"量不到：{e}", file=sys.stderr)
        return 1
    for row in rows:
        if row["seconds"] is not None and row["seconds"] > args.slow:
            print(f"慢的那次看 mirror 速度：gh run view {row['run']} --log | grep 'Fetched .* in '")
    return 0


if __name__ == "__main__":
    sys.exit(main())
