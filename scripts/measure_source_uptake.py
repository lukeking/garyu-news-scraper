#!/usr/bin/env python3
"""Measure per-source report-uptake for the buffer-list noise signal (spec 011).

Uptake = the share of a source's articles that reached a weekly hot-topic
report. It is a real downstream outcome and, unlike `initial_quality_score`,
it discriminates: measured spread is roughly 8x across sources.

What this is NOT: uptake is not "share worth reading". Only about a fifth of
all articles reach a report, because each week publishes ~3 hot topics. The
configured value is therefore a MULTIPLE relative to the overall baseline, not
an absolute quality ratio (spec FR-005).

Read-only. Never writes to the database.

Usage:
    python scripts/measure_source_uptake.py            # table for humans
    python scripts/measure_source_uptake.py --json     # config JSON
"""
import argparse
import json
import logging
import os
import re
import sys
from collections import defaultdict

from dotenv import load_dotenv

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# load_dotenv() with no argument searches upward from the *caller's* directory,
# which misses the project .env when this script is invoked from elsewhere.
load_dotenv(os.path.join(_REPO_ROOT, ".env"))
sys.path.insert(0, _REPO_ROOT)

logger = logging.getLogger("measure_source_uptake")

MIN_SAMPLE = 15          # FR-005d: below this a source gets no configured value
PAGE_SIZE = 1000         # Supabase caps rows per response
DEFAULT_THRESHOLD = 0.5  # FR-005a: multiple below this reads as noise

# Only real ISO week ids are measurable. The integration suite writes rows like
# "2025-W01-test" straight into the articles table whenever .env credentials are
# present, and those rows shifted the baseline and every multiple when they were
# picked up. Config values must not be at the mercy of whoever last ran pytest.
ISO_WEEK = re.compile(r"^\d{4}-W\d{2}$")


def fetch_traffic_articles():
    """Page through every traffic article, analysed and un-analysed alike.

    Deliberately does NOT use storage.get_traffic_buffer(): that helper filters
    hot_topic_analyzed=False, which would leave this measurement's numerator
    permanently zero.
    """
    from src.storage import _get_client

    client = _get_client()
    rows, page = [], 0
    while True:
        resp = (
            client.table("articles")
            .select("source,week_id,hot_topic_analyzed")
            .eq("content_type", "traffic")
            .range(page * PAGE_SIZE, (page + 1) * PAGE_SIZE - 1)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        page += 1


def select_window(rows):
    """Return the set of week_ids that can be compared fairly.

    Two contamination sources are excluded (FR-005c). The window is derived
    from the data every run — never a hardcoded week list — because both
    exclusions move forward with time.

    1. Pruned weeks. expire_buffer_articles() deletes rows that are expired AND
       un-analysed; analysed rows are kept forever. Once a week has been pruned
       only its analysed rows survive, so its uptake reads as 100%. Detect it as
       "no un-analysed rows left".

    2. The latest week, always. Its articles are still waiting for the next
       Monday report, so their uptake means "not yet eligible", not "noise".
       Note this holds even when the week already contains analysed rows: the
       weekly job runs on the Monday, i.e. inside the week it is closing out,
       so a partially-analysed latest week is still in flight. Excluding it
       only when it looked untouched let a freshly added source be measured at
       0% and written into config as maximum noise.
    """
    by_week = defaultdict(list)
    for r in rows:
        week = r.get("week_id") or ""
        if ISO_WEEK.match(week):        # drop test fixtures and malformed ids
            by_week[week].append(r)
    if not by_week:
        return set()

    latest = max(by_week)
    window = set()
    for week, items in by_week.items():
        if week == latest:
            continue                      # in flight: report has not covered it
        analysed = sum(1 for i in items if i.get("hot_topic_analyzed"))
        if analysed == len(items):
            continue                      # pruned: un-analysed rows are gone
        window.add(week)
    return window


def measure(rows, window):
    """Return (baseline_uptake, {source: {uptake, multiple, n}})."""
    win = [r for r in rows if r.get("week_id") in window]
    if not win:
        return 0.0, {}

    baseline = sum(1 for r in win if r.get("hot_topic_analyzed")) / len(win)

    by_source = defaultdict(list)
    for r in win:
        by_source[r.get("source") or "(none)"].append(r)

    out = {}
    for source, items in by_source.items():
        analysed = sum(1 for i in items if i.get("hot_topic_analyzed"))
        uptake = analysed / len(items)
        out[source] = {
            "uptake": uptake,
            "multiple": (uptake / baseline) if baseline else 0.0,
            "n": len(items),
        }
    return baseline, out


def build_config(baseline, stats, window, threshold=DEFAULT_THRESHOLD, exclude=()):
    """Shape the measurement into the Worker's SOURCE_UPTAKE_JSON (data-model.md).

    Sources below MIN_SAMPLE are omitted entirely rather than given a shaky
    number — omission routes them to the FR-006 default of "not noise".

    `exclude` omits named sources on purpose. Hand-picked sources (a followed
    YouTube channel, say) can score low simply because video does not cluster
    into hot topics, and the operator may prefer to keep controlling those at
    the source config instead of having them auto-downgraded.
    """
    excluded = set(exclude)
    weeks = sorted(window)
    return {
        "threshold": threshold,
        "window": f"{weeks[0]}..{weeks[-1]}" if weeks else "",
        "measured_at": __import__("datetime").date.today().isoformat(),
        "baseline_uptake": round(baseline, 4),
        "sources": {
            src: {"multiple": round(v["multiple"], 2), "n": v["n"]}
            for src, v in sorted(stats.items(), key=lambda kv: kv[1]["multiple"])
            if v["n"] >= MIN_SAMPLE and src not in excluded
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true",
                    help="emit the Worker config JSON instead of a table")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help=f"noise cutoff as a multiple of baseline (default {DEFAULT_THRESHOLD})")
    ap.add_argument("--exclude", action="append", default=[], metavar="SOURCE",
                    help="omit a source from the config on purpose; repeatable")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING)
    rows = fetch_traffic_articles()
    window = select_window(rows)
    baseline, stats = measure(rows, window)

    if args.json:
        print(json.dumps(
            build_config(baseline, stats, window, args.threshold, args.exclude),
            ensure_ascii=False, indent=2))
        return

    all_weeks = sorted({r.get("week_id") for r in rows if r.get("week_id")})
    excluded = [w for w in all_weeks if w not in window]
    print(f"articles: {len(rows)}   weeks seen: {len(all_weeks)}")
    print(f"window:   {len(window)} weeks — excluded {excluded or '(none)'}")
    print(f"baseline uptake: {baseline:.1%}\n")

    print(f"{'source':<28}{'n':>5}{'uptake':>9}{'multiple':>10}  evidence")
    print("-" * 68)
    for src, v in sorted(stats.items(), key=lambda kv: kv[1]["multiple"]):
        ev = "E1" if v["n"] >= MIN_SAMPLE else f"E3 (n<{MIN_SAMPLE})"
        print(f"{src[:28]:<28}{v['n']:>5}{v['uptake']:>8.0%}{v['multiple']:>9.2f}x  {ev}")

    kept = sum(1 for v in stats.values() if v["n"] >= MIN_SAMPLE)
    covered = sum(v["n"] for v in stats.values() if v["n"] >= MIN_SAMPLE)
    total = sum(v["n"] for v in stats.values())
    print(f"\nconfigurable: {kept}/{len(stats)} sources, "
          f"covering {covered}/{total} articles ({covered/total:.0%})"
          if total else "\nno data in window")


if __name__ == "__main__":
    main()
