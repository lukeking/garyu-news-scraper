#!/usr/bin/env python3
"""Replay a shipped weekly run's category-digest pool from its Actions log (spec 013).

Why this exists: after a weekly run publishes a digest it CONSUMES the pool
(`hot_topic_analyzed=True`), so the obvious replay — query the buffer and re-run
`select_digest_pool` — returns zero rows once the run has happened. The pool's
membership survives only in the run's own log, in the two
`PATCH .../articles?link=in.(...)` calls that marked it. This script reconstructs
the pool from those links, re-reads the rows from the database, and re-runs the
real selection function over them.

It reports the SC-001 numbers **with the pool as denominator** (`pool_all`), which
is the denominator the spec's anchor values use (08-10: distinct 3→9, largest
75.7%→60.9%, remainder-after-largest 9→18). The published report's source list is
a DIFFERENT denominator and is not comparable — on the 2026-08-17 run the pool gave
distinct 13 / largest 29.1% while the published 25 gave distinct 10 / largest 20.0%.

Self-check: the reconstructed per-category composition is printed so it can be
compared against the log's own `池組成` line. Only the `PATCH` calls between the
digest's `正在彙整：<category> · 彙整（` line and its `digest[<category>] consumed=`
line are read: regular hot topics publish earlier in the run with the same `PATCH`
shape and would inflate the pool. A missing anchor or an empty window exits — no pool to replay.

Effective config (quality_floor / max_articles / include_categories) is read from
the local pipeline config rather than hardcoded, so the replay follows config
changes instead of silently using stale constants. Verify it matches production
when the two may have drifted.

Read-only. Never writes to the database. Requires `gh` on PATH.

Usage:
    .venv/bin/python scripts/replay_digest_pool.py <RUN_ID>
    .venv/bin/python scripts/replay_digest_pool.py <RUN_ID> --category 道安政策
"""
import argparse
import os
import re
import subprocess
import sys
import urllib.parse
from collections import Counter

from dotenv import load_dotenv

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_REPO_ROOT, ".env"))
sys.path.insert(0, _REPO_ROOT)

DEFAULT_REPO = "lukeking/garyu-news-scraper"
BATCH = 10               # long Google News links make bigger `in.(...)` filters unwieldy
# The links live URL-encoded inside the PostgREST call the run made; nothing else
# in the log carries pool membership.
PATCH_LINKS = re.compile(r"/rest/v1/articles\?link=in\.%28(.*?)%29\s")


def links_from_log(run_id: str, repo: str, category: str) -> list:
    """Return the links marked inside `category`'s digest window of the log, deduplicated."""
    log = subprocess.run(
        ["gh", "run", "view", run_id, "--log", "--repo", repo],
        capture_output=True, text=True,
    ).stdout
    if not log:
        sys.exit(f"讀不到 run {run_id} 的 log（gh 失敗，或 log 已過期被清掉）")
    start = log.find(f"正在彙整：{category} · 彙整（")
    if start < 0:
        sys.exit(f"run {run_id} 的 log 沒有「正在彙整：{category} · 彙整（」起點錨"
                 f"——{category} 這週沒發 digest（或 log 格式變了），沒有被消耗的池可重播")
    end = log.find(f"digest[{category}] consumed=", start)
    if end < 0:
        sys.exit(f"run {run_id} 的 log 在彙整之後沒有「digest[{category}] consumed=」終點錨"
                 f"——{category} 的 digest 失敗、池沒被消耗，沒有池可重播")
    links = []
    for m in PATCH_LINKS.finditer(log, start, end):
        links += [s.strip('"') for s in urllib.parse.unquote(m.group(1)).split('","')]
    if not links:
        sys.exit(f"run {run_id} 的 {category} 彙整窗裡沒有任何 PATCH——池沒有被標記，沒有池可重播")
    return sorted({l.strip('"') for l in links})


def rows_for(links: list, categories: list) -> list:
    from src.storage import _get_client

    client = _get_client()
    rows = []
    for i in range(0, len(links), BATCH):
        rows += (
            client.table("articles")
            .select("link,title,source,major_category,initial_quality_score")
            .in_("link", links[i:i + BATCH])
            .execute()
        ).data or []
    return [r for r in rows if r.get("major_category") in categories]


def digest_config(category: str) -> dict:
    from src.pipeline_config import load_pipeline_config

    cfg = (load_pipeline_config().get("category_digest") or {}).get(category)
    if not cfg:
        sys.exit(f"本機設定的 category_digest 沒有 {category}——確認 config/pipeline_config.yml")
    return cfg


def report(rows: list, category: str, cfg: dict) -> None:
    from src.topic_scoring import select_digest_pool

    siblings = list(cfg.get("include_categories") or [])
    base = {k: cfg[k] for k in ("quality_floor", "max_articles") if k in cfg}
    merged = {**base, "include_categories": siblings}

    per = Counter(r["major_category"] for r in rows)
    composition = " ＋ ".join(f"{c} {per.get(c, 0)}" for c in [category] + siblings)
    print(f"重建池組成：{composition} = {len(rows)}")
    print("↑ 對照 log 的「池組成」行，逐項相同才算重建成功（不同時先確認本機 pipeline 設定與 prod 一致，見本檔 docstring）")

    for tag, conf in [("現行(不匯流)", base), ("匯流", merged)]:
        selected, pool, effective = select_digest_pool(rows, category, conf, set())
        if not pool:
            continue
        sources = Counter(a["source"] for a in pool)
        top, top_n = sources.most_common(1)[0]
        print(
            f"{tag}: pool={len(pool)} effective={effective} selected={len(selected)} "
            f"distinct={len(sources)} 最大={top} {top_n}({top_n / len(pool):.1%}) "
            f"抽掉最大剩={len(pool) - top_n}"
        )
    print(f"↑「抽掉最大剩」≥ trigger_count（{cfg.get('trigger_count', 10)}）＝ SC-001 L1 承重解除")

    current, _, _ = select_digest_pool(rows, category, base, set())
    merged_sel, _, _ = select_digest_pool(rows, category, merged, set())
    current_links = {a["link"] for a in current}
    quality = lambda a: float(a.get("initial_quality_score") or 0)
    new = sorted(
        [a for a in merged_sel if a["link"] not in current_links], key=quality, reverse=True
    )
    print(f"\n--- 匯流新進 {len(new)} 篇（SC-003 逐篇判讀用）---")
    for a in new:
        print(f"  {quality(a):.3f} [{a['major_category']}] {(a['title'] or '')[:60]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_id", help="週報的 GitHub Actions run id")
    parser.add_argument("--category", default="道安政策", help="digest 主類別")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    args = parser.parse_args()

    cfg = digest_config(args.category)
    siblings = list(cfg.get("include_categories") or [])
    print(f"套用設定：quality_floor={cfg.get('quality_floor')} "
          f"max_articles={cfg.get('max_articles')} include_categories={siblings}")

    links = links_from_log(args.run_id, args.repo, args.category)
    print(f"從 log 還原 {len(links)} 條被標記的連結")
    rows = rows_for(links, [args.category] + siblings)
    print(f"DB 取回 {len(rows)} 篇（已濾掉非本池類別）")
    report(rows, args.category, cfg)


if __name__ == "__main__":
    main()
