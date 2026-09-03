#!/usr/bin/env python3
"""Measure how much genuine article body actually reaches the analyzer (BACKLOG #11).

analyzer.analyze_hot_topic() builds its prompt from `標題` plus
`(summary or content)[:600]`. The articles table has no `content` column — the
collector never produces that key and storage.py never inserts it — so the
effective body is `summary` alone. This script answers one question: of
everything fed to the model, what share is genuine article body?

What this is NOT: measure_body_fetch.py measures *fetchability* — re-fetch the
URL, did a lede come back — over a denominator that only contains articles with
a real (non Google-News) URL. It reported 84.8%. This script measures what is
actually *stored* and actually *fed to the prompt*, over the whole population,
Google-News-unresolved rows included. On an 8-article sample the two disagreed
84.8% vs 1/8. Dropping the GN rows is precisely how a metric that cannot fail
gets built, so they stay in the denominator.

Read-only. Never writes to the database.

Usage:
    python scripts/measure_input_quality.py            # table for humans
    python scripts/measure_input_quality.py --json     # same numbers, machine-readable
"""
import argparse
import html
import json
import logging
import os
import re
import sys
import unicodedata
from collections import defaultdict
from urllib.parse import urlparse

from dotenv import load_dotenv

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# load_dotenv() with no argument searches upward from the *caller's* directory,
# which misses the project .env when this script is invoked from elsewhere.
load_dotenv(os.path.join(_REPO_ROOT, ".env"))
sys.path.insert(0, _REPO_ROOT)

logger = logging.getLogger("measure_input_quality")

PAGE_SIZE = 1000         # Supabase caps rows per response
PREFIX_LEN = 30          # leading characters that key a site's template
MIN_BOILERPLATE = 3      # a prefix is a template once 3 distinct articles share it

# THIN_MAX_CHARS is not a guess. Three independent observations put 60 in an
# empty band between the synthetic/echo cluster and the genuine-lede cluster:
#   - collector.py writes placeholder summaries that are not article bodies at
#     all — f"PTT {board} 推文數：{push_count}" and f"{name} 官方公告",
#     measured at 8-16 characters;
#   - BACKLOG #11's hand-read 14-article sample found title-echo summaries at
#     22-58 characters, and genuine bodies at 85 and 186;
#   - in production the non-echo non-markup remainder has p10 = 73 characters
#     (p25 = 99, p50 = 107), and hand-reading the 80-120 band shows real ledes.
# So the synthetic/echo cluster tops out at 58 and the genuine cluster starts at
# 73; 60 sits in the gap and no observed value lands near it.
THIN_MAX_CHARS = 60

CLASSES = ("absent", "title_echo", "boilerplate", "thin", "substantive")

# Only real ISO week ids are measurable. The integration suite writes rows like
# "2025-W01-test" straight into the articles table whenever .env credentials are
# present, and those rows shifted the baseline and every multiple when they were
# picked up. Measurements must not be at the mercy of whoever last ran pytest.
ISO_WEEK = re.compile(r"^\d{4}-W\d{2}$")

# Tag-shaped run. Used both to strip markup and to flag it, so the two can never
# disagree about what counts as a tag. A plain regex rather than BeautifulSoup:
# nothing here traverses the DOM (only tag removal is needed), bs4 raises
# MarkupResemblesLocatorWarning on the bare-URL summaries this table contains,
# and keeping the pure functions dependency-free keeps the unit tests trivial.
TAG_RE = re.compile(r"<[a-zA-Z/!][^>]*>")


def norm(s: str) -> str:
    return "".join(c for c in (s or "") if unicodedata.category(c)[0] in "LN")


def is_echo(title: str, summary: str) -> bool:
    """摘要只是複讀標題 → 這一列在 UI 上等同只有標題（同 pages/shared/app.js 判準）。"""
    nt, ns = norm(title), norm(summary)
    return len(ns) <= len(nt) + 24 and (nt in ns or ns in nt)


# norm() and is_echo() above are copied verbatim from scripts/measure_body_fetch.py
# so that "is this only the title again" is decided the same way here, there, and
# in pages/shared/app.js. Re-declared rather than imported: measure_body_fetch
# pulls in requests and bs4 at module level, and this file's pure functions are
# meant to stay importable by the unit suite with no network dependencies.


def effective_text(raw) -> str:
    """What the prompt really carries: markup stripped, entities resolved.

    Order matters. 7.5% of production rows arrive as an <a> blob whose anchor
    text is the article title plus the source name; the stripped-to-raw length
    ratio is min 0.07, median 0.15. Classified before stripping they read as
    "has content" when they are really title echoes — so normalise first,
    classify second. Tags go first and entities second: unescaping first would
    turn an escaped &lt;b&gt; into a tag and then delete it.
    """
    text = TAG_RE.sub(" ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def has_html_markup(raw) -> bool:
    """Diagnostic flag: the stored summary was markup, not text."""
    return bool(TAG_RE.search(raw or ""))


def link_domain(link) -> str:
    return urlparse(link or "").netloc


def is_gn_unresolved(link) -> bool:
    """Diagnostic flag: the link is still a Google News redirect, never resolved."""
    return "news.google.com" in (link or "")


def select_rows(rows):
    """The denominator: every traffic article in a real ISO week.

    Deliberately NOT filtered by link shape. Google-News-unresolved rows are
    454/1233 (36.8%) of the population and they are exactly the rows most likely
    to carry a title echo instead of a body, so excluding them would build the
    reassuring number this script exists to replace.
    """
    return [
        r for r in rows
        if (r.get("content_type") or "") == "traffic"
        and ISO_WEEK.match(r.get("week_id") or "")
    ]


def boilerplate_keys(rows):
    """Derive the (domain, prefix) pairs that are a site's template, not news.

    Counting, never a hardcoded domain or string: a site that starts publishing
    a new boilerplate lead is caught without a code change. Identity is the
    link, so one duplicated row cannot manufacture a template on its own.

    Only texts of at least PREFIX_LEN participate. A shorter text has no
    30-character prefix, and treating the whole short string as one would let
    the synthetic placeholder cluster (8-16 characters) be relabelled
    boilerplate and stolen from `thin`, where the THIN_MAX_CHARS derivation
    deliberately puts it. A domain is likewise required — "the same link domain"
    has no meaning for a row with no link.
    """
    seen = defaultdict(set)
    for r in rows:
        text = effective_text(r.get("summary"))
        if len(text) < PREFIX_LEN:
            continue
        domain = link_domain(r.get("link"))
        if not domain:
            continue
        seen[(domain, text[:PREFIX_LEN])].add(r.get("link"))
    return {key for key, links in seen.items() if len(links) >= MIN_BOILERPLATE}


def classify_row(row, keys) -> str:
    """Put a row in exactly one class; first match wins, in this order.

    The order is load-bearing. An HTML blob that strips down to the title is a
    title echo, not content — which is only visible because effective_text()
    ran first.
    """
    text = effective_text(row.get("summary"))
    if not text:
        return "absent"
    if is_echo(row.get("title") or "", text):
        return "title_echo"
    if (link_domain(row.get("link")), text[:PREFIX_LEN]) in keys:
        return "boilerplate"
    if len(text) < THIN_MAX_CHARS:
        return "thin"
    return "substantive"


def measure(rows):
    """Classify the whole population and roll it up.

    The two flags are counted independently of the class: a row can be both a
    title_echo and arrived_as_html, and both counters see it. The classes
    measure the effect on the prompt, the flags point at the cause — mixing them
    would hide whichever one lost.
    """
    win = select_rows(rows)
    keys = boilerplate_keys(win)

    counts = {c: 0 for c in CLASSES}
    flags = {"arrived_as_html": 0, "gn_unresolved_link": 0}
    by_week = defaultdict(lambda: {"n": 0, "non_substantive": 0})
    by_source = defaultdict(lambda: {"n": 0, "non_substantive": 0})
    # major_category 這一維是 BACKLOG #11 真正要問的東西：digest 匯流的政策四類
    # （道安政策／路權政策／科技執法／交通工程）入料品質是否系統性差於其他類別。
    # 首次量到 W32-W36：政策四類 58.9% vs 非政策 84.2%，差 25 個百分點。
    by_category = defaultdict(lambda: {"n": 0, "non_substantive": 0})

    for r in win:
        cls = classify_row(r, keys)
        counts[cls] += 1
        if has_html_markup(r.get("summary")):
            flags["arrived_as_html"] += 1
        if is_gn_unresolved(r.get("link")):
            flags["gn_unresolved_link"] += 1

        for bucket, key in ((by_week, r.get("week_id") or "(none)"),
                            (by_source, r.get("source") or "(none)"),
                            (by_category, r.get("major_category") or "(none)")):
            bucket[key]["n"] += 1
            if cls != "substantive":
                bucket[key]["non_substantive"] += 1

    total = len(win)

    def share(n):
        return (n / total) if total else 0.0

    for bucket in (by_week, by_source, by_category):
        for stat in bucket.values():
            stat["share"] = stat["non_substantive"] / stat["n"]

    prefixes = sorted(
        ({"domain": d, "prefix": p} for d, p in keys),
        key=lambda x: (x["domain"], x["prefix"]),
    )

    return {
        "total": total,
        "weeks": sorted(by_week),
        "classes": counts,
        "class_share": {c: share(counts[c]) for c in CLASSES},
        "flags": flags,
        "flag_share": {k: share(v) for k, v in flags.items()},
        "by_week": dict(by_week),
        "by_source": dict(by_source),
        "by_category": dict(by_category),
        "boilerplate_prefixes": prefixes,
    }


def fetch_traffic_articles():
    """Page through every traffic article, analysed and un-analysed alike.

    Deliberately does NOT use storage.get_traffic_buffer(): that helper filters
    hot_topic_analyzed=False and buffer_expires_at > NOW(), which would measure
    only the rows still waiting rather than everything the analyzer has ever
    been fed. Read-only — SELECT alone.
    """
    from src.storage import _get_client

    client = _get_client()
    rows, page = [], 0
    while True:
        resp = (
            client.table("articles")
            .select("title,summary,link,source,week_id,content_type,major_category")
            .eq("content_type", "traffic")
            .range(page * PAGE_SIZE, (page + 1) * PAGE_SIZE - 1)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        page += 1


def print_report(rep):
    total = rep["total"]
    if not total:
        print("no measurable rows (traffic + real ISO week)")
        return

    print(f"articles measured: {total}   weeks: {len(rep['weeks'])}"
          f"   ({rep['weeks'][0]}..{rep['weeks'][-1]})")
    print("denominator INCLUDES Google-News-unresolved rows "
          f"({rep['flags']['gn_unresolved_link']}, "
          f"{rep['flag_share']['gn_unresolved_link']:.1%}) — excluding them is how a "
          "fetchability number that cannot fail gets built.\n")

    print(f"{'class':<16}{'n':>6}{'share':>9}")
    print("-" * 31)
    for c in CLASSES:
        print(f"{c:<16}{rep['classes'][c]:>6}{rep['class_share'][c]:>9.1%}")
    print("-" * 31)
    print(f"{'genuine body':<16}{rep['classes']['substantive']:>6}"
          f"{rep['class_share']['substantive']:>9.1%}\n")

    print("flags (counted independently of the class, not mutually exclusive)")
    for k, v in rep["flags"].items():
        print(f"  {k:<22}{v:>6}{rep['flag_share'][k]:>9.1%}")

    print(f"\n{'week':<12}{'n':>6}{'non-substantive':>18}")
    print("-" * 36)
    for week in rep["weeks"]:
        s = rep["by_week"][week]
        print(f"{week:<12}{s['n']:>6}{s['non_substantive']:>10}{s['share']:>8.0%}")

    print(f"\n{'source':<28}{'n':>6}{'non-substantive':>18}")
    print("-" * 52)
    for src, s in sorted(rep["by_source"].items(),
                         key=lambda kv: (-kv[1]["share"], -kv[1]["n"])):
        print(f"{src[:28]:<28}{s['n']:>6}{s['non_substantive']:>10}{s['share']:>8.0%}")

    print(f"\n{'major_category':<16}{'n':>6}{'non-substantive':>18}")
    print("-" * 40)
    for cat, s_ in sorted(rep["by_category"].items(),
                          key=lambda kv: (-kv[1]["share"], -kv[1]["n"])):
        print(f"{cat[:16]:<16}{s_['n']:>6}{s_['non_substantive']:>10}{s_['share']:>8.0%}")

    print("\nboilerplate prefixes found (derived by counting, not hardcoded)")
    for p in rep["boilerplate_prefixes"] or []:
        print(f"  {p['domain']:<24}{p['prefix']}")
    if not rep["boilerplate_prefixes"]:
        print("  (none)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true",
                    help="emit the same numbers as JSON instead of a table")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING)
    rep = measure(fetch_traffic_articles())

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return
    print_report(rep)


if __name__ == "__main__":
    main()
